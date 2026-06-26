"""MCP tools: VERI*FACTU — registro, validacion, envio, QR y anulacion.

VERI*FACTU (Real Decreto 1007/2023, Orden HAC/1177/2024):
    XSD v1.0 (SuministroLR.xsd): specs/verifactu/xsd/
    Sandbox:    https://prewww2.aeat.es/...
    Production: https://www2.agenciatributaria.gob.es/...

Namespaces (confirmed from XSD targetNamespace):
    _VF_LR_NS: SuministroLR.xsd   — RegFactuSistemaFacturacion root element
    _VF_SF_NS: SuministroInformacion.xsd — RegistroAlta, RegistroAnulacion, Cabecera, all inner types

Huella (hash chain) — Annex III HAC/1177/2024:
    SHA-256(hex, uppercase) of:
    IDEmisorFactura & NumSerieFactura & FechaExpedicionFactura & TipoFactura &
    CuotaTotal & FechaHoraHusoGenRegistro [& HuellaAnterior if not first]

EncadenamientoFacturaAnteriorType (SuministroInformacion.xsd) — 4 required fields:
    IDEmisorFactura, NumSerieFactura, FechaExpedicionFactura, Huella

[NEED: verify sandbox endpoint URL once AEAT opens VERI*FACTU test environment]
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

import mcp.types as types
from lxml import etree
from mcp_einvoicing_core.base_server import assert_not_read_only
from mcp_einvoicing_core.confirmation import ConfirmationGate
from mcp_einvoicing_core.exceptions import EInvoicingError
from mcp_einvoicing_core.models import InvoiceDocument
from mcp_einvoicing_core.qr import generate_qr_png_base64
from mcp_einvoicing_core.signer_client import SignerClient
from mcp_einvoicing_core.xml_utils import safe_fromstring

from mcp_facturacion_electronica_es._helpers import (
    VERIFACTU_ENDPOINTS,
    aeat_env,
    err,
    fmt_amount,
    fmt_date_es,
    ok,
    parse_invoice,
)
from mcp_facturacion_electronica_es.config import aeat_settings
from mcp_facturacion_electronica_es.models.es import VerifactuInvoiceType

logger = logging.getLogger(__name__)

# ES-SC-7: Namespaces confirmed from specs/verifactu/xsd/ targetNamespace attributes
# SuministroLR.xsd: root envelope element RegFactuSistemaFacturacion
_VF_LR_NS = (
    "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones"
    "/es/aeat/tike/cont/ws/SuministroLR.xsd"
)
# SuministroInformacion.xsd: RegistroAlta, RegistroAnulacion, Cabecera, and all inner types
_VF_SF_NS = (
    "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones"
    "/es/aeat/tike/cont/ws/SuministroInformacion.xsd"
)

_VERIFACTU_VERSION = "1.0"
# IdSistemaInformatico is TextMax2Type in SuministroInformacion.xsd — max 2 characters
_SOFTWARE_ID_CODE = "ES"


# ---------------------------------------------------------------------------
# XML builder helpers
# ---------------------------------------------------------------------------


def _el(tag: str, text: str | None = None, **attribs: str) -> etree._Element:
    """Create a namespace-qualified VeriFactu element (SuministroInformacion namespace)."""
    elem = etree.Element(f"{{{_VF_SF_NS}}}{tag}")
    if text is not None:
        elem.text = text
    for k, v in attribs.items():
        elem.set(k, v)
    return elem


def _sub(parent: etree._Element, tag: str, text: str | None = None) -> etree._Element:
    """Append a namespace-qualified child element (SuministroInformacion namespace)."""
    child = etree.SubElement(parent, f"{{{_VF_SF_NS}}}{tag}")
    if text is not None:
        child.text = text
    return child


def _build_id_factura(
    num_serie: str,
    emisor_nif: str,
    fecha_es: str,
) -> etree._Element:
    idf = _el("IDFactura")
    _sub(idf, "IDEmisorFactura", emisor_nif)
    _sub(idf, "NumSerieFactura", num_serie)
    _sub(idf, "FechaExpedicionFactura", fecha_es)
    return idf


def _compute_huella(
    emisor_nif: str,
    num_serie: str,
    fecha_es: str,
    tipo_factura: str,
    cuota_total: str,
    fecha_hora_gen: str,
    huella_anterior: str | None,
) -> str:
    """Compute the VERI*FACTU Huella (hash chain link).

    Per HAC/1177/2024 Annex III:
    SHA-256 of the concatenation of the listed fields, separated by '&'.
    Returns uppercase hexadecimal (64 characters).
    """
    parts = [
        emisor_nif,
        num_serie,
        fecha_es,
        tipo_factura,
        cuota_total,
        fecha_hora_gen,
    ]
    if huella_anterior:
        parts.append(huella_anterior)

    raw = "&".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def _build_registro_alta(
    invoice: InvoiceDocument,
    invoice_type: str,
    software_id: str,
    software_nif: str,
    previous_hash: str | None,
    fecha_hora_gen: str,
    previous_emisor_nif: str | None = None,
    previous_num_serie: str | None = None,
    previous_fecha: str | None = None,
    clave_regimen: str = "01",
    impuesto: str = "01",
    calificacion_operacion: str = "S1",
    recargo_equivalencia_rate: Decimal | None = None,
    recargo_equivalencia_amount: Decimal | None = None,
) -> tuple[etree._Element, str]:
    """Build the RegistroAlta element and return (element, huella).

    Returns:
        (RegistroAlta element, Huella hex string)
    """
    seller_nif = invoice.seller.tax_id.identifier
    seller_name = invoice.seller.display_name
    buyer = invoice.buyer
    num_serie = invoice.number
    fecha_es = fmt_date_es(invoice.date)

    # Compute totals from vat_summary
    cuota_total = fmt_amount(sum((v.vat_amount for v in invoice.vat_summary), Decimal("0")))
    importe_total = fmt_amount(
        sum(
            (v.taxable_base + v.vat_amount for v in invoice.vat_summary),
            Decimal("0"),
        )
    )

    huella = _compute_huella(
        emisor_nif=seller_nif,
        num_serie=num_serie,
        fecha_es=fecha_es,
        tipo_factura=invoice_type,
        cuota_total=cuota_total,
        fecha_hora_gen=fecha_hora_gen,
        huella_anterior=previous_hash,
    )

    ra = _el("RegistroAlta")
    _sub(ra, "IDVersion", _VERIFACTU_VERSION)

    ra.append(_build_id_factura(num_serie, seller_nif, fecha_es))

    _sub(ra, "NombreRazonEmisor", seller_name)
    _sub(ra, "Subsanacion", "N")
    _sub(ra, "RechazoPrevio", "N")
    _sub(ra, "TipoFactura", invoice_type)

    # DescripcionOperacion
    desc = invoice.note or "Prestación de servicios / entrega de bienes"
    _sub(ra, "DescripcionOperacion", desc[:500])

    # Destinatarios
    dest_elem = _sub(ra, "Destinatarios")
    id_dest = _sub(dest_elem, "IDDestinatario")
    _sub(id_dest, "NombreRazon", buyer.display_name)
    if buyer.tax_id.country_code.upper() == "ES":
        _sub(id_dest, "NIF", buyer.tax_id.identifier)
    else:
        id_osp = _sub(id_dest, "IDOtro")
        _sub(id_osp, "CodigoPais", buyer.tax_id.country_code.upper())
        _sub(id_osp, "IDType", "07")  # passaporte/doc extranjero
        _sub(id_osp, "ID", buyer.tax_id.identifier)

    _sub(ra, "Cupon", "N")

    # Desglose IVA
    desglose = _sub(ra, "Desglose")
    desglose_iva = _sub(desglose, "DesgloseIVA")
    for vat in invoice.vat_summary:
        detail = _sub(desglose_iva, "DetalleIVA")
        _sub(detail, "Impuesto", impuesto)
        _sub(detail, "ClaveRegimen", clave_regimen)
        _sub(detail, "CalificacionOperacion", calificacion_operacion)
        _sub(detail, "TipoImpositivo", fmt_amount(vat.vat_rate))
        _sub(detail, "BaseImponibleOImporteNoSujeto", fmt_amount(vat.taxable_base))
        _sub(detail, "CuotaRepercutida", fmt_amount(vat.vat_amount))
        if recargo_equivalencia_rate is not None:
            _sub(detail, "TipoRecargoEquivalencia", fmt_amount(recargo_equivalencia_rate))
            re_amount = recargo_equivalencia_amount or (
                vat.taxable_base * recargo_equivalencia_rate / Decimal("100")
            )
            _sub(detail, "CuotaRecargoEquivalencia", fmt_amount(re_amount))

    _sub(ra, "CuotaTotal", cuota_total)
    _sub(ra, "ImporteTotal", importe_total)

    # Encadenamiento — ES-LC-4: EncadenamientoFacturaAnteriorType requires all 4 fields
    enc = _sub(ra, "Encadenamiento")
    if previous_hash:
        _sub(enc, "PrimerRegistro", "N")
        reg_ant = _sub(enc, "RegistroAnterior")
        # EncadenamientoFacturaAnteriorType (SuministroInformacion.xsd):
        # IDEmisorFactura + NumSerieFactura + FechaExpedicionFactura + Huella — all required
        _sub(reg_ant, "IDEmisorFactura", previous_emisor_nif or seller_nif)
        _sub(reg_ant, "NumSerieFactura", previous_num_serie or "")
        _sub(reg_ant, "FechaExpedicionFactura", previous_fecha or fecha_es)
        _sub(reg_ant, "Huella", previous_hash)
    else:
        _sub(enc, "PrimerRegistro", "S")

    # SistemaInformatico — IdSistemaInformatico is TextMax2Type (max 2 chars per XSD)
    si = _sub(ra, "SistemaInformatico")
    _sub(si, "NombreRazon", seller_name)
    _sub(si, "NIF", software_nif)
    _sub(si, "NombreSistemaInformatico", "mcp-facturacion-electronica-es")
    _sub(si, "IdSistemaInformatico", software_id[:2] if software_id else _SOFTWARE_ID_CODE)
    _sub(si, "Version", "0.1.0")
    _sub(si, "NumeroInstalacion", "001")
    _sub(si, "TipoUsoPosibleSoloVerifactu", "S")
    _sub(si, "TipoUsoPosibleMultiOT", "N")
    _sub(si, "IndicadorMultiplesOT", "N")

    _sub(ra, "FechaHoraHusoGenRegistro", fecha_hora_gen)
    # TipoHuella must be "01" (SHA-256) per TipoHuellaType enumeration in SuministroInformacion.xsd
    _sub(ra, "TipoHuella", "01")
    _sub(ra, "Huella", huella)

    # [NEED: AEAT XAdES profile clarification for VeriFactu record signing]
    # ES-SC-12: AEAT has not published a canonical XAdES signing profile for
    # the RegistroAlta XML itself (distinct from the SOAP envelope mTLS).
    # The record is submitted unsigned; XAdES signing deferred to v0.3.1
    # pending AEAT technical publication.

    return ra, huella


def _wrap_registro_facturacion(
    emisor_nif: str,
    emisor_name: str,
    inner: etree._Element,
) -> bytes:
    """Wrap a RegistroAlta or RegistroAnulacion in the RegFactuSistemaFacturacion envelope.

    ES-SC-7: RegFactuSistemaFacturacion is in SuministroLR namespace;
    Cabecera and inner record types are in SuministroInformacion namespace.
    """
    nsmap = {
        "sfLR": _VF_LR_NS,
        "sf": _VF_SF_NS,
    }
    root = etree.Element(f"{{{_VF_LR_NS}}}RegFactuSistemaFacturacion", nsmap=nsmap)
    # Cabecera and its children are in SuministroInformacion namespace
    cab = etree.SubElement(root, f"{{{_VF_SF_NS}}}Cabecera")
    oblig = etree.SubElement(cab, f"{{{_VF_SF_NS}}}ObligadoEmision")
    etree.SubElement(oblig, f"{{{_VF_SF_NS}}}NombreRazonSocial").text = emisor_name
    etree.SubElement(oblig, f"{{{_VF_SF_NS}}}NIF").text = emisor_nif
    # RegistroFactura wrapper (SuministroLR namespace), contains RegistroAlta/Anulacion
    reg_factura = etree.SubElement(root, f"{{{_VF_LR_NS}}}RegistroFactura")
    reg_factura.append(inner)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# ---------------------------------------------------------------------------
# Response parsing helper
# ---------------------------------------------------------------------------


def _parse_verifactu_response(raw: str) -> dict[str, Any]:
    """Parse an AEAT VERI*FACTU response, extract key fields without echoing raw XML.

    ES-SH-2: Raw AEAT responses must not be relayed to the LLM. Only structured
    key fields are returned: EstadoEnvio, CSV, CodigoErrorRegistro, DescripcionErrorRegistro.
    ES-LC-5: Detect TiempoEsperaEnvio deferral signal.
    """
    result: dict[str, Any] = {}
    if not raw:
        return result
    try:
        root = safe_fromstring(raw.encode())
        for field in [
            "EstadoEnvio",
            "CSV",
            "CodigoErrorRegistro",
            "DescripcionErrorRegistro",
            "EstadoRegistro",
        ]:
            elems = root.xpath(f".//*[local-name()='{field}']")
            if elems:
                result[field] = elems[0].text

        # ES-LC-5: detect TiempoEsperaEnvio deferral
        espera_elems = root.xpath(".//*[local-name()='TiempoEsperaEnvio']")
        if espera_elems and espera_elems[0].text:
            try:
                retry_seconds = int(espera_elems[0].text)
                result["status"] = "deferred"
                result["retry_after_seconds"] = retry_seconds
            except ValueError:
                pass
    except Exception as exc:
        result["parse_error"] = f"Could not parse AEAT response: {exc}"
    return result


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOL_ES_GENERATE_VERIFACTU_RECORD = types.Tool(
    name="es__generate_verifactu_record",
    description=(
        "Genera un registro de factura VERI*FACTU (Orden HAC/1177/2024) con cadena SHA-256 Huella. "
        "Devuelve el XML del registro y la Huella para encadenar con el siguiente registro. "
        "Llame a es__detect_regional_regime antes para confirmar que el régimen es VERIFACTU."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "invoice": {
                "type": "object",
                "description": "Datos de la factura (date, number, seller, buyer, vat_summary, note).",
            },
            "previous_hash": {
                "type": "string",
                "description": "Huella SHA-256 del registro precedente (omitir o null para el primero).",
            },
            "previous_emisor_nif": {
                "type": "string",
                "description": "NIF del emisor del registro anterior (requerido si previous_hash está presente).",
            },
            "previous_num_serie": {
                "type": "string",
                "description": "NumSerieFactura del registro anterior (requerido si previous_hash está presente).",
            },
            "previous_fecha": {
                "type": "string",
                "description": "FechaExpedicionFactura del registro anterior en DD-MM-YYYY (requerido si previous_hash está presente).",
            },
            "software_id": {
                "type": "string",
                "description": "IDSistemaInformatico del software certificado.",
            },
            "software_nif": {
                "type": "string",
                "description": "NIF del fabricante del software.",
            },
            "invoice_type": {
                "type": "string",
                "enum": ["F1", "F2", "F3", "R1", "R2", "R3", "R4", "R5"],
                "description": "TipoFactura según HAC/1177/2024 Annex I.",
            },
        },
        "required": ["invoice", "software_id", "software_nif", "invoice_type"],
    },
)

TOOL_ES_VALIDATE_VERIFACTU_RECORD = types.Tool(
    name="es__validate_verifactu_record",
    description=(
        "Valida un registro VERI*FACTU XML. Realiza validación estructural y, si el XSD v1.0 "
        "(HAC/1177/2024) está disponible en specs/verifactu/, también validación de esquema."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "xml": {"type": "string", "description": "Registro VERI*FACTU XML en crudo."},
            "schema_version": {
                "type": "string",
                "description": "Versión del esquema XSD (por defecto: '1.0').",
                "default": "1.0",
            },
        },
        "required": ["xml"],
    },
)

TOOL_ES_SUBMIT_VERIFACTU_TO_AEAT = types.Tool(
    name="es__submit_verifactu_to_aeat",
    description=(
        "Envía un registro VERI*FACTU firmado al endpoint en tiempo real de la AEAT mediante MTLS "
        "(certificado FNMT-RCM). Requiere AEAT_ENV, AEAT_CERTIFICATE_PATH y AEAT_CERTIFICATE_PASSWORD."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "xml": {"type": "string", "description": "Registro VERI*FACTU XML firmado."},
            "nif": {"type": "string", "description": "NIF del remitente."},
        },
        "required": ["xml", "nif"],
    },
)

TOOL_ES_GENERATE_QR_VERIFACTU = types.Tool(
    name="es__generate_qr_verifactu",
    description=(
        "Genera el código QR obligatorio VERI*FACTU (HAC/1177/2024 Art. 10) como PNG en base64. "
        "Encodes la URL de verificación de la AEAT: "
        "https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR?..."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "nif": {"type": "string", "description": "NIF del emisor."},
            "invoice_number": {"type": "string", "description": "NumSerieFactura."},
            "invoice_date": {
                "type": "string",
                "description": "FechaExpedicionFactura en YYYY-MM-DD.",
            },
            "total_amount": {
                "type": "number",
                "description": "ImporteTotal de la factura (con IVA incluido).",
            },
            "size_px": {
                "type": "integer",
                "description": "Tamaño del QR en píxeles (por defecto: 200).",
                "default": 200,
            },
        },
        "required": ["nif", "invoice_number", "invoice_date", "total_amount"],
    },
)

TOOL_ES_CANCEL_VERIFACTU_RECORD = types.Tool(
    name="es__cancel_verifactu_record",
    description=(
        "Genera un registro de anulacion VERI*FACTU (TipoHuella=01) "
        "encadenado a la secuencia de huellas actual."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "original_invoice_number": {
                "type": "string",
                "description": "NumSerieFactura a anular.",
            },
            "original_invoice_date": {
                "type": "string",
                "description": "FechaExpedicionFactura original (YYYY-MM-DD).",
            },
            "issuer_nif": {"type": "string", "description": "NIF del emisor."},
            "issuer_name": {"type": "string", "description": "Nombre/razon social del emisor."},
            "previous_hash": {
                "type": "string",
                "description": "Huella del ultimo registro en la cadena.",
            },
            "previous_emisor_nif": {
                "type": "string",
                "description": "NIF del emisor del registro anterior (IDEmisorFactura en EncadenamientoFacturaAnteriorType).",
            },
            "previous_num_serie": {
                "type": "string",
                "description": "NumSerieFactura del registro anterior.",
            },
            "previous_fecha": {
                "type": "string",
                "description": "FechaExpedicionFactura del registro anterior en DD-MM-YYYY.",
            },
        },
        "required": [
            "original_invoice_number",
            "original_invoice_date",
            "issuer_nif",
            "issuer_name",
            "previous_hash",
        ],
    },
)

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def handle_es_generate_verifactu_record(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        invoice_data = arguments.get("invoice")
        if not invoice_data:
            return err("invoice is required", "MISSING_PARAM")

        invoice = parse_invoice(invoice_data)
        invoice_type = arguments.get("invoice_type", "F1")
        software_id = arguments.get("software_id", "")
        software_nif = arguments.get("software_nif", "")
        previous_hash: str | None = arguments.get("previous_hash") or None
        previous_emisor_nif: str | None = arguments.get("previous_emisor_nif") or None
        previous_num_serie: str | None = arguments.get("previous_num_serie") or None
        previous_fecha: str | None = arguments.get("previous_fecha") or None
        clave_regimen: str = arguments.get("clave_regimen", "01")
        impuesto: str = arguments.get("impuesto", "01")
        calificacion_operacion: str = arguments.get("calificacion_operacion", "S1")

        try:
            VerifactuInvoiceType(invoice_type)
        except ValueError:
            return err(f"Invalid invoice_type: {invoice_type!r}")

        if not software_id:
            return err("software_id is required", "MISSING_PARAM")
        if not software_nif:
            return err("software_nif is required", "MISSING_PARAM")

        # ES-LC-4: EncadenamientoFacturaAnteriorType requires IDEmisorFactura,
        # NumSerieFactura, FechaExpedicionFactura + Huella — all 4 mandatory.
        chain_warnings: list[str] = []
        if previous_hash and not all([previous_emisor_nif, previous_num_serie, previous_fecha]):
            chain_warnings.append(
                "previous_hash provided without previous_emisor_nif / previous_num_serie / "
                "previous_fecha: EncadenamientoFacturaAnteriorType requires all 4 fields "
                "(IDEmisorFactura, NumSerieFactura, FechaExpedicionFactura, Huella). "
                "Falling back to current invoice identity for missing prior-record fields — "
                "provide the previous invoice identity for a fully conformant chain."
            )

        # Timestamp: ISO 8601 with local timezone (AEAT requires timezone offset)
        now = datetime.now().astimezone()
        fecha_hora_gen = now.strftime("%Y-%m-%dT%H:%M:%S%z")
        # Insert colon in timezone: +0100 → +01:00
        if len(fecha_hora_gen) > 19 and ":" not in fecha_hora_gen[-6:]:
            fecha_hora_gen = fecha_hora_gen[:-2] + ":" + fecha_hora_gen[-2:]

        ra, huella = _build_registro_alta(
            invoice=invoice,
            invoice_type=invoice_type,
            software_id=software_id,
            software_nif=software_nif,
            previous_hash=previous_hash,
            fecha_hora_gen=fecha_hora_gen,
            previous_emisor_nif=previous_emisor_nif,
            previous_num_serie=previous_num_serie,
            previous_fecha=previous_fecha,
            clave_regimen=clave_regimen,
            impuesto=impuesto,
            calificacion_operacion=calificacion_operacion,
        )

        xml_bytes = _wrap_registro_facturacion(
            emisor_nif=invoice.seller.tax_id.identifier,
            emisor_name=invoice.seller.display_name,
            inner=ra,
        )

        logger.info(
            "VERI*FACTU record generated: %s / %s → huella=%s...",
            invoice.seller.tax_id.identifier,
            invoice.number,
            huella[:16],
        )

        result: dict[str, Any] = {
            "xml": xml_bytes.decode("utf-8"),
            "huella": huella,
            "fecha_hora_gen": fecha_hora_gen,
            "invoice_id": {
                "emisor_nif": invoice.seller.tax_id.identifier,
                "num_serie": invoice.number,
                "fecha": fmt_date_es(invoice.date),
            },
            "note": (
                "Sign with XAdES before submission — "
                "use es__sign_facturae_xades or a certified VERI*FACTU software."
            ),
        }
        if chain_warnings:
            result["chain_warnings"] = chain_warnings
        return ok(result)

    except EInvoicingError as exc:
        return err(str(exc))
    except Exception as exc:
        logger.exception("es__generate_verifactu_record failed")
        return err(str(exc))


async def handle_es_validate_verifactu_record(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        xml_str = arguments.get("xml", "")
        if not xml_str:
            return err("xml is required", "MISSING_PARAM")

        xml_bytes = xml_str.encode() if isinstance(xml_str, str) else xml_str

        # --- Structural parse ---
        try:
            root = safe_fromstring(xml_bytes)
        except etree.XMLSyntaxError as exc:
            return ok(
                {
                    "valid": False,
                    "errors": [f"XML malformado: {exc}"],
                    "warnings": [],
                    "validation_mode": "structural",
                }
            )

        errors: list[str] = []
        warnings: list[str] = []

        def _req(tag: str) -> None:
            if not root.xpath(f".//*[local-name()='{tag}']"):
                errors.append(f"Elemento obligatorio ausente: <{tag}>")

        # Check mandatory VERI*FACTU elements
        for tag in [
            "IDEmisorFactura",
            "NumSerieFactura",
            "FechaExpedicionFactura",
            "TipoFactura",
            "CuotaTotal",
            "ImporteTotal",
            "FechaHoraHusoGenRegistro",
            "Huella",
        ]:
            _req(tag)

        # --- XSD validation (SuministroLR.xsd is the root schema for submissions) ---
        import pathlib  # noqa: PLC0415

        xsd_path = (
            pathlib.Path(__file__).parent.parent.parent
            / "specs"
            / "verifactu"
            / "xsd"
            / "SuministroLR.xsd"
        )
        validation_mode = "structural"

        if xsd_path.exists():
            try:
                xsd_doc = etree.parse(str(xsd_path))
                schema = etree.XMLSchema(xsd_doc)
                schema.validate(root)
                for e in schema.error_log:
                    errors.append(f"[XSD] {e.message} (linea {e.line})")
                validation_mode = "xsd"
            except Exception as exc:
                warnings.append(f"XSD validation failed to run: {exc}")
        else:
            warnings.append(
                "Validacion XSD no disponible — specs/verifactu/xsd/SuministroLR.xsd "
                "no encontrado. La validacion estructural esta activa."
            )

        return ok(
            {
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings,
                "validation_mode": validation_mode,
            }
        )

    except Exception as exc:
        logger.exception("es__validate_verifactu_record failed")
        return err(str(exc))


async def handle_es_submit_verifactu_to_aeat(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        xml_str = arguments.get("xml", "")
        nif = arguments.get("nif", "")
        confirmation_token: str | None = arguments.get("confirmation_token") or None
        if not xml_str:
            return err("xml is required", "MISSING_PARAM")
        if not nif:
            return err("nif is required", "MISSING_PARAM")

        assert_not_read_only("AEAT_READ_ONLY")
        gate = ConfirmationGate.get_default()
        if not gate.is_confirmed(confirmation_token):
            env_label = aeat_env()
            return ok(
                gate.pending_response(
                    action="es__submit_verifactu_to_aeat",
                    summary=(
                        f"Submit VERI*FACTU XML to AEAT ({env_label}) for NIF {nif!r}. "
                        "This action reports the invoice to the Tax Agency and cannot be retracted."
                    ),
                    token=confirmation_token,
                )
            )

        env = aeat_env()
        base_url = VERIFACTU_ENDPOINTS[env]
        xml_bytes = xml_str.encode() if isinstance(xml_str, str) else xml_str

        if SignerClient.is_configured():
            signer = SignerClient.from_env()
            result = await signer.mtls_submit_files(
                base_url,
                [("xml", "registro.xml", xml_bytes, "application/xml")],
            )
            gate.consume(confirmation_token)
            # ES-SH-2: parse response before returning — do not echo raw AEAT response to LLM
            parsed = _parse_verifactu_response(result.get("body", ""))
            return ok(
                {
                    "status_code": result["status_code"],
                    "environment": env,
                    "parsed_response": parsed,
                    "note": "Use es__parse_aeat_response for full response parsing.",
                }
            )

        # Fallback: direct mTLS (legacy mode — cert lives in MCP process).
        from mcp_einvoicing_core.http_client import AuthMode, BaseEInvoicingClient  # noqa: PLC0415

        cert_path = aeat_settings.certificate_path
        cert_password = aeat_settings.certificate_password
        if not cert_path:
            return err(
                "AEAT_CERTIFICATE_PATH no está configurado. "
                "Arranque el servicio de firma (EINVOICING_SIGNER_SOCKET) "
                "o proporcione la ruta al certificado FNMT-RCM PKCS#12.",
                "MISSING_CONFIG",
            )
        logger.warning(
            "es__submit_verifactu_to_aeat: signer microservice not configured — "
            "cert material is in the MCP process (security risk). "
            "Set EINVOICING_SIGNER_SOCKET and EINVOICING_SIGNER_TOKEN."
        )

        client = BaseEInvoicingClient(
            base_url=base_url,
            auth_mode=AuthMode.MTLS,
            cert_path=cert_path,
            cert_password=cert_password,
        )
        response = await client._request(
            "POST",
            "",
            data=None,
            json=None,
            files={"xml": ("registro.xml", xml_bytes, "application/xml")},
        )
        # ES-SH-2: parse response before returning — do not echo raw AEAT response to LLM
        gate.consume(confirmation_token)
        parsed = _parse_verifactu_response(response.text)
        return ok(
            {
                "status_code": response.status_code,
                "environment": env,
                "parsed_response": parsed,
                "note": "Use es__parse_aeat_response for full response parsing.",
            }
        )

    except Exception as exc:
        logger.exception("es__submit_verifactu_to_aeat failed")
        return err(str(exc))


async def handle_es_generate_qr_verifactu(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        nif = arguments.get("nif", "")
        invoice_number = arguments.get("invoice_number", "")
        invoice_date = arguments.get("invoice_date", "")
        total_amount = arguments.get("total_amount")
        size_px = int(arguments.get("size_px", 200))

        for name, value in [
            ("nif", nif),
            ("invoice_number", invoice_number),
            ("invoice_date", invoice_date),
        ]:
            if not value:
                return err(f"{name} is required", "MISSING_PARAM")
        if total_amount is None:
            return err("total_amount is required", "MISSING_PARAM")

        # Build verification URL (BOE-A-2024-22138, Art. 21)
        # Base URL is provisional pending AEAT technical publication on Sede Electronica.
        # Parameters per Art. 21: NIF, NumSerieFactura, FechaExpedicionFactura, ImporteTotal.
        fecha_es = fmt_date_es(invoice_date)
        importe = fmt_amount(Decimal(str(total_amount)))

        verification_url = (
            f"https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR"
            f"?nif={nif}&numserie={invoice_number}&fecha={fecha_es}&importe={importe}"
        )

        png_b64 = generate_qr_png_base64(verification_url, size_px=size_px)

        logger.info("VERI*FACTU QR generated for %s / %s", nif, invoice_number)

        return ok(
            {
                "qr_png_base64": png_b64,
                "verification_url": verification_url,
                "mandatory_legends": [
                    "Factura verificable en la sede electrónica de la AEAT",
                    "VERIFACTU",
                ],
                "size_px": size_px,
            }
        )

    except ImportError as exc:
        return err(
            f"qrcode[pil] no está instalado: {exc}. Instale con: pip install 'qrcode[pil]'",
            "MISSING_DEPENDENCY",
        )
    except Exception as exc:
        logger.exception("es__generate_qr_verifactu failed")
        return err(str(exc))


async def handle_es_cancel_verifactu_record(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        num_serie = arguments.get("original_invoice_number", "")
        fecha_iso = arguments.get("original_invoice_date", "")
        issuer_nif = arguments.get("issuer_nif", "")
        issuer_name = arguments.get("issuer_name", "")
        previous_hash = arguments.get("previous_hash", "")

        for name, val in [
            ("original_invoice_number", num_serie),
            ("original_invoice_date", fecha_iso),
            ("issuer_nif", issuer_nif),
            ("issuer_name", issuer_name),
            ("previous_hash", previous_hash),
        ]:
            if not val:
                return err(f"{name} is required", "MISSING_PARAM")

        fecha_es = fmt_date_es(fecha_iso)
        now = datetime.now().astimezone()
        fecha_hora_gen = now.strftime("%Y-%m-%dT%H:%M:%S%z")
        if len(fecha_hora_gen) > 19 and ":" not in fecha_hora_gen[-6:]:
            fecha_hora_gen = fecha_hora_gen[:-2] + ":" + fecha_hora_gen[-2:]

        previous_emisor_nif: str | None = arguments.get("previous_emisor_nif") or None
        previous_num_serie_arg: str | None = arguments.get("previous_num_serie") or None
        previous_fecha_arg: str | None = arguments.get("previous_fecha") or None

        # Build RegistroAnulacion
        ra = _el("RegistroAnulacion")
        _sub(ra, "IDVersion", _VERIFACTU_VERSION)
        ra.append(_build_id_factura(num_serie, issuer_nif, fecha_es))
        _sub(ra, "NombreRazonEmisor", issuer_name)

        # ES-LC-4: EncadenamientoFacturaAnteriorType requires all 4 identity fields
        enc = _sub(ra, "Encadenamiento")
        _sub(enc, "PrimerRegistro", "N")
        reg_ant = _sub(enc, "RegistroAnterior")
        _sub(reg_ant, "IDEmisorFactura", previous_emisor_nif or issuer_nif)
        _sub(reg_ant, "NumSerieFactura", previous_num_serie_arg or num_serie)
        _sub(reg_ant, "FechaExpedicionFactura", previous_fecha_arg or fecha_es)
        _sub(reg_ant, "Huella", previous_hash)

        # SistemaInformatico — IdSistemaInformatico is TextMax2Type (max 2 chars)
        si = _sub(ra, "SistemaInformatico")
        _sub(si, "NombreRazon", issuer_name)
        _sub(si, "NIF", issuer_nif)
        _sub(si, "NombreSistemaInformatico", "mcp-facturacion-electronica-es")
        _sub(si, "IdSistemaInformatico", _SOFTWARE_ID_CODE)
        _sub(si, "Version", "0.1.0")
        _sub(si, "NumeroInstalacion", "001")
        _sub(si, "TipoUsoPosibleSoloVerifactu", "S")
        _sub(si, "TipoUsoPosibleMultiOT", "N")
        _sub(si, "IndicadorMultiplesOT", "N")

        _sub(ra, "FechaHoraHusoGenRegistro", fecha_hora_gen)

        # Huella for the anulacion record itself
        huella = _compute_huella(
            emisor_nif=issuer_nif,
            num_serie=num_serie,
            fecha_es=fecha_es,
            tipo_factura="ANULACION",
            cuota_total="0.00",
            fecha_hora_gen=fecha_hora_gen,
            huella_anterior=previous_hash,
        )
        # TipoHuella must be "01" (SHA-256) per TipoHuellaType in SuministroInformacion.xsd
        _sub(ra, "TipoHuella", "01")
        _sub(ra, "Huella", huella)

        xml_bytes = _wrap_registro_facturacion(
            emisor_nif=issuer_nif,
            emisor_name=issuer_name,
            inner=ra,
        )

        return ok(
            {
                "xml": xml_bytes.decode("utf-8"),
                "huella": huella,
                "fecha_hora_gen": fecha_hora_gen,
                "cancelled_invoice": {
                    "emisor_nif": issuer_nif,
                    "num_serie": num_serie,
                    "fecha": fecha_es,
                },
            }
        )

    except Exception as exc:
        logger.exception("es__cancel_verifactu_record failed")
        return err(str(exc))
