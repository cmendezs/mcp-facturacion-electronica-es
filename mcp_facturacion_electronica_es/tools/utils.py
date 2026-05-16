"""MCP tools: utilidades — detección de régimen, estado de cumplimiento y análisis AEAT.

Province INE codes for regime routing:
    01 Álava (Araba)  → TicketBAI
    20 Gipuzkoa       → TicketBAI
    48 Bizkaia        → TicketBAI
    31 Navarra        → NaTicket
    All others        → VERIFACTU  (or VERIFACTU+SII if enrolled_in_sii=True)

Mutual exclusion (Royal Decree 254/2025):
    SII-enrolled taxpayers are exempt from VERI*FACTU.
    Basque and Navarrese taxpayers never fall under VERI*FACTU.
"""

from __future__ import annotations

import logging
from typing import Any

import mcp.types as types
from lxml import etree
from mcp_einvoicing_core.xml_utils import safe_fromstring

from mcp_facturacion_electronica_es._helpers import err, ok
from mcp_facturacion_electronica_es.models.es import (
    AEATResponseType,
    EntityType,
    SpanishRegime,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Province → regime mapping
# ---------------------------------------------------------------------------

_TICKETBAI_INE_CODES: frozenset[str] = frozenset({"01", "20", "48"})
_NATICKET_INE_CODE = "31"

# Mandate deadlines (RD-ley 15/2025, December 2025)
_MANDATE_DATES: dict[str, dict[str, str]] = {
    "VERIFACTU_IS": {
        "system": "VERI*FACTU",
        "deadline": "2027-01-01",
        "description": (
            "Obligatorio para contribuyentes del Impuesto sobre Sociedades (IS) "
            "desde el 1 de enero de 2027 (RD-ley 15/2025)."
        ),
    },
    "VERIFACTU_IRPF": {
        "system": "VERI*FACTU",
        "deadline": "2027-07-01",
        "description": (
            "Obligatorio para autónomos en régimen de IRPF y otros obligados no-SII "
            "desde el 1 de julio de 2027 (RD-ley 15/2025)."
        ),
    },
    "SII": {
        "system": "SII",
        "deadline": "already_mandatory",
        "description": (
            "Ya obligatorio para grandes empresas (facturación > €6M), "
            "grupos de IVA y REDEME (RD 596/2016). "
            "Excluye la obligación de VERI*FACTU (RD 254/2025)."
        ),
    },
    "FACTURAE_FACE": {
        "system": "Facturae / FACe",
        "deadline": "already_mandatory",
        "description": (
            "Ya obligatorio para todos los proveedores del sector público "
            "desde 2015 (Ley 25/2013)."
        ),
    },
    "TICKETBAI": {
        "system": "TicketBAI",
        "deadline": "already_mandatory",
        "description": (
            "Ya obligatorio en el País Vasco (Álava, Gipuzkoa, Bizkaia) "
            "con implantación sectorial escalonada entre 2022 y 2023."
        ),
    },
    "NATICKET": {
        "system": "NaTicket",
        "deadline": "rolling",
        "description": (
            "Mandato foral de la Hacienda Foral de Navarra con implantación escalonada. "
            "VERI*FACTU no aplica en Navarra."
        ),
    },
    "B2B_CREA_Y_CRECE": {
        "system": "Crea y Crece B2B",
        "deadline": "pending_decree",
        "description": (
            "Reglamento de desarrollo de la Ley 18/2022 pendiente de publicación. "
            "El umbral y el calendario definitivos están por determinar."
        ),
    },
}

_SII_TURNOVER_THRESHOLD_EUR = 6_000_000


def _detect_regime(
    province_code: str,
    enrolled_in_sii: bool,
    annual_turnover_eur: float | None = None,
) -> SpanishRegime:
    """Pure-logic regime detection from province code and SII enrolment."""
    code = str(province_code).strip().zfill(2)
    if code in _TICKETBAI_INE_CODES:
        return SpanishRegime.TICKETBAI
    if code == _NATICKET_INE_CODE:
        return SpanishRegime.NATICKET
    if enrolled_in_sii:
        return SpanishRegime.VERIFACTU_SII
    if annual_turnover_eur is not None and annual_turnover_eur > _SII_TURNOVER_THRESHOLD_EUR:
        # Large turnover may trigger voluntary SII; regime is still VERIFACTU
        # until formally enrolled (enrollment is what triggers the exclusion)
        pass
    return SpanishRegime.VERIFACTU


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOL_ES_DETECT_REGIONAL_REGIME = types.Tool(
    name="es__detect_regional_regime",
    description=(
        "Detecta el régimen de facturación electrónica aplicable a partir del código de provincia "
        "INE de dos dígitos. Devuelve VERIFACTU, TICKETBAI, NATICKET o VERIFACTU+SII. "
        "Usar siempre antes de llamar a cualquier otra herramienta de este servidor."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "province_code": {
                "type": "string",
                "description": "Código de provincia INE de dos dígitos (p. ej., '28', '01', '31').",
                "pattern": "^[0-9]{1,2}$",
            },
            "enrolled_in_sii": {
                "type": "boolean",
                "description": "Inscripción en el SII (por defecto: false).",
                "default": False,
            },
        },
        "required": ["province_code"],
    },
)

TOOL_ES_GET_COMPLIANCE_STATUS = types.Tool(
    name="es__get_compliance_status",
    description=(
        "Devuelve los plazos de mandato vigentes y el sistema operativo para un perfil de empresa. "
        "Refleja el RD-ley 15/2025 — sujeto a cambios por legislación posterior."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "entity_type": {
                "type": "string",
                "enum": ["IS", "IRPF"],
                "description": "Tipo de obligado tributario.",
            },
            "province_code": {
                "type": "string",
                "description": "Código de provincia INE de dos dígitos.",
                "pattern": "^[0-9]{1,2}$",
            },
            "annual_turnover_eur": {
                "type": "number",
                "description": "Volumen anual de operaciones IVA en EUR (para umbral SII > €6M).",
            },
            "enrolled_in_sii": {
                "type": "boolean",
                "description": "Inscripción en el SII.",
                "default": False,
            },
        },
        "required": ["entity_type", "province_code"],
    },
)

TOOL_ES_PARSE_AEAT_RESPONSE = types.Tool(
    name="es__parse_aeat_response",
    description=(
        "Analiza y normaliza una respuesta XML de la AEAT (VERI*FACTU o SII) a JSON estructurado. "
        "Extrae EstadoEnvio, CSV (código seguro de verificación) y detalle de errores."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "xml": {
                "type": "string",
                "description": "Respuesta XML de la AEAT en crudo.",
            },
            "response_type": {
                "type": "string",
                "enum": ["verifactu", "sii"],
                "description": "Tipo de respuesta a analizar (por defecto: 'verifactu').",
                "default": "verifactu",
            },
        },
        "required": ["xml"],
    },
)

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def handle_es_detect_regional_regime(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    """Detect the applicable e-invoicing regime from INE province code."""
    try:
        province_code = str(arguments.get("province_code", "")).strip()
        if not province_code:
            return err("province_code is required", "MISSING_PARAM")

        enrolled = bool(arguments.get("enrolled_in_sii", False))
        regime = _detect_regime(province_code, enrolled)

        descriptions: dict[SpanishRegime, str] = {
            SpanishRegime.VERIFACTU: (
                "VERI*FACTU (RD 1007/2023, Orden HAC/1177/2024). "
                "Registro en tiempo real en el servidor de la AEAT."
            ),
            SpanishRegime.VERIFACTU_SII: (
                "SII ya inscrito — exento de VERI*FACTU (RD 254/2025). "
                "Comunicación de facturas en 4 días hábiles."
            ),
            SpanishRegime.TICKETBAI: (
                "TicketBAI (País Vasco). Régimen foral independiente del nacional AEAT. "
                "Requiere certificación de software provincial."
            ),
            SpanishRegime.NATICKET: (
                "NaTicket (Navarra). Régimen foral de la Hacienda Foral de Navarra. "
                "VERI*FACTU no aplica."
            ),
        }

        province_note = ""
        code = str(province_code).strip().zfill(2)
        if code == "01":
            province_note = "Álava / Araba — TicketBAI (XSD v1.2)"
        elif code == "20":
            province_note = "Gipuzkoa — TicketBAI (XSD v1.2)"
        elif code == "48":
            province_note = "Bizkaia — TicketBAI (XSD v2.1)"
        elif code == "31":
            province_note = "Navarra — NaTicket (Hacienda Foral de Navarra)"

        result: dict[str, Any] = {
            "province_code": province_code,
            "enrolled_in_sii": enrolled,
            "regime": regime.value,
            "description": descriptions[regime],
        }
        if province_note:
            result["province_note"] = province_note

        logger.info(
            "Regime detected: province=%s enrolled_sii=%s → %s",
            province_code,
            enrolled,
            regime.value,
        )
        return ok(result)

    except Exception as exc:
        logger.exception("es__detect_regional_regime failed")
        return err(str(exc))


async def handle_es_get_compliance_status(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    """Return mandate deadlines and applicable systems for a company profile."""
    try:
        entity_type_str = arguments.get("entity_type", "IS")
        province_code = str(arguments.get("province_code", "28")).strip()
        turnover = arguments.get("annual_turnover_eur")
        enrolled = bool(arguments.get("enrolled_in_sii", False))

        try:
            entity_type = EntityType(entity_type_str)
        except ValueError:
            return err(f"Invalid entity_type: {entity_type_str!r}. Must be 'IS' or 'IRPF'.")

        regime = _detect_regime(province_code, enrolled, annual_turnover_eur=turnover)

        applicable_systems: list[dict[str, Any]] = []

        # Facturae/FACe always applies for B2G
        applicable_systems.append({
            "system": "Facturae / FACe",
            "scope": "B2G (facturas al sector público)",
            **_MANDATE_DATES["FACTURAE_FACE"],
        })

        # Crea y Crece B2B (pending decree)
        applicable_systems.append({
            "system": "Crea y Crece B2B",
            "scope": "B2B (todas las empresas)",
            **_MANDATE_DATES["B2B_CREA_Y_CRECE"],
        })

        # Regime-specific system
        if regime == SpanishRegime.TICKETBAI:
            applicable_systems.append({
                "scope": "Todas las facturas (sustituye a VERI*FACTU en el País Vasco)",
                **_MANDATE_DATES["TICKETBAI"],
            })
        elif regime == SpanishRegime.NATICKET:
            applicable_systems.append({
                "scope": "Todas las facturas en Navarra",
                **_MANDATE_DATES["NATICKET"],
            })
        elif regime == SpanishRegime.VERIFACTU_SII:
            applicable_systems.append({
                "scope": "Grandes empresas / grupos IVA / REDEME",
                **_MANDATE_DATES["SII"],
            })
        else:
            # VERIFACTU
            key = "VERIFACTU_IS" if entity_type == EntityType.IS else "VERIFACTU_IRPF"
            applicable_systems.append({
                "scope": (
                    "Impuesto sobre Sociedades"
                    if entity_type == EntityType.IS
                    else "IRPF / autónomos y otros no-SII"
                ),
                **_MANDATE_DATES[key],
            })

        result: dict[str, Any] = {
            "entity_type": entity_type.value,
            "province_code": province_code,
            "enrolled_in_sii": enrolled,
            "detected_regime": regime.value,
            "applicable_systems": applicable_systems,
            "disclaimer": (
                "Fechas de mandato según RD-ley 15/2025 (diciembre 2025). "
                "Sujetas a cambios por legislación posterior o instrucciones de la AEAT. "
                "Este software no constituye asesoramiento jurídico ni fiscal."
            ),
        }
        if turnover is not None:
            result["annual_turnover_eur"] = turnover
            if turnover > _SII_TURNOVER_THRESHOLD_EUR:
                result["sii_threshold_note"] = (
                    f"Facturación ({turnover:,.2f} EUR) supera el umbral SII (€6M). "
                    "Considere inscripción voluntaria en el SII."
                )

        return ok(result)

    except Exception as exc:
        logger.exception("es__get_compliance_status failed")
        return err(str(exc))


async def handle_es_parse_aeat_response(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    """Parse an AEAT XML response (VERI*FACTU or SII) into structured JSON."""
    try:
        xml_str = arguments.get("xml", "")
        if not xml_str:
            return err("xml is required", "MISSING_PARAM")

        response_type_str = arguments.get("response_type", "verifactu")
        try:
            response_type = AEATResponseType(response_type_str)
        except ValueError:
            return err(
                f"Invalid response_type: {response_type_str!r}. Must be 'verifactu' or 'sii'."
            )

        xml_bytes = xml_str.encode() if isinstance(xml_str, str) else xml_str
        try:
            root = safe_fromstring(xml_bytes)
        except etree.XMLSyntaxError as exc:
            return err(f"XML inválido: {exc}", "XML_PARSE_ERROR")

        # Strip namespaces for easier querying
        def _text(elem: etree._Element | None) -> str | None:
            if elem is None:
                return None
            return (elem.text or "").strip() or None

        def _find(parent: etree._Element, *local_names: str) -> etree._Element | None:
            for name in local_names:
                results = parent.xpath(f".//*[local-name()='{name}']")
                found = results[0] if results else None
                if found is not None:
                    return found
            return None

        result: dict[str, Any] = {
            "response_type": response_type.value,
            "raw_root_tag": root.tag,
        }

        if response_type == AEATResponseType.verifactu:
            # VERI*FACTU response fields (RespuestaRegFactuSistemaFacturacion)
            result["estado_envio"] = _text(_find(root, "EstadoEnvio"))
            result["csv"] = _text(_find(root, "CSV"))
            result["tiempo_espera_envio"] = _text(_find(root, "TiempoEsperaEnvio"))

            # Extract line-level errors / acknowledgements
            registros = root.xpath(".//*[local-name()='RespuestaLinea']")
            if registros:
                result["respuestas_linea"] = []
                for reg in registros:
                    linea: dict[str, Any] = {
                        "estado_registro": _text(_find(reg, "EstadoRegistro")),
                        "codigo_error_registro": _text(_find(reg, "CodigoErrorRegistro")),
                        "descripcion_error_registro": _text(
                            _find(reg, "DescripcionErrorRegistro")
                        ),
                    }
                    # IDFactura within this line
                    idf = _find(reg, "IDFactura")
                    if idf is not None:
                        linea["id_factura"] = {
                            "emisor_nif": _text(_find(idf, "IDEmisorFactura")),
                            "num_serie": _text(_find(idf, "NumSerieFactura")),
                            "fecha": _text(_find(idf, "FechaExpedicionFactura")),
                        }
                    result["respuestas_linea"].append(linea)

        else:
            # SII response fields (RespuestaSuministroLR)
            result["estado_envio"] = _text(_find(root, "EstadoEnvio"))
            result["csv"] = _text(_find(root, "CSV"))
            result["tiempo_espera_envio"] = _text(_find(root, "TiempoEsperaEnvio"))
            result["num_total"] = _text(_find(root, "NumTotal"))
            result["num_correctos"] = _text(_find(root, "NumCorrectos"))
            result["num_errores"] = _text(_find(root, "NumErrores"))

            lineas = root.xpath(".//*[local-name()='RespuestaLinea']")
            if lineas:
                result["respuestas_linea"] = []
                for linea_elem in lineas:
                    linea = {
                        "estado_registro": _text(_find(linea_elem, "EstadoRegistro")),
                        "codigo_error": _text(_find(linea_elem, "CodigoErrorRegistro")),
                        "descripcion_error": _text(
                            _find(linea_elem, "DescripcionErrorRegistro")
                        ),
                    }
                    result["respuestas_linea"].append(linea)

        # Derive overall success flag
        estado = result.get("estado_envio", "")
        result["success"] = estado == "Correcto"
        result["accepted_with_errors"] = estado == "AceptadoConErrores"

        return ok(result)

    except Exception as exc:
        logger.exception("es__parse_aeat_response failed")
        return err(str(exc))
