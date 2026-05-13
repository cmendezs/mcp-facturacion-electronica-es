"""MCP tools: TicketBAI — generación XML, envío provincial y validación de esquema.

TicketBAI (País Vasco):
    Álava (Araba):   XSD v1.2 — https://batuz.eus/es/documentacion-tecnica
    Gipuzkoa:        XSD v1.2 — https://www.gipuzkoa.eus/ticketbai
    Bizkaia:         XSD v2.1 — https://www.bizkaia.eus/ticketbai

HuellaTBAI chain:
    SHA-256(previous_record_signature_value_bytes) → Base64-encoded.
    Empty string for the first record in the chain.

[NEED: download the three provincial XSDs into specs/ticketbai/{araba,gipuzkoa,bizkaia}/]
[NEED: verify HuellaTBAI algorithm against official TicketBAI technical specification]
[NEED: confirm submission endpoint URLs and auth method per province]
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from decimal import Decimal
from typing import Any

import mcp.types as types
from lxml import etree
from mcp_einvoicing_core.digital_signature import XAdESEPESSigner, XAdESSignerConfig
from mcp_einvoicing_core.exceptions import EInvoicingError
from mcp_einvoicing_core.models import InvoiceDocument

from mcp_facturacion_electronica_es._helpers import (
    TICKETBAI_ENDPOINTS,
    TICKETBAI_POLICY_IDS,
    err,
    fmt_amount,
    fmt_date_es,
    ok,
    parse_invoice,
    ticketbai_env,
)
from mcp_facturacion_electronica_es.models.es import TicketBAIProvince

logger = logging.getLogger(__name__)

# TicketBAI XML namespaces (common across provinces; minor differences in XSD versions)
_TBAI_NS = "urn:ticketbai:emision"
_DS_NS = "http://www.w3.org/2000/09/xmldsig#"
_XADES_NS = "http://uri.etsi.org/01903/v1.3.2#"


# ---------------------------------------------------------------------------
# TicketBAI XML builder
# ---------------------------------------------------------------------------


def _sub(parent: etree._Element, tag: str, text: str | None = None) -> etree._Element:
    child = etree.SubElement(parent, tag)
    if text is not None:
        child.text = text
    return child


def _compute_huella_tbai(previous_signature_value: str | None) -> str:
    """Compute the HuellaTBAI chain link.

    Per TicketBAI specification:
    SHA-256 of the previous record's SignatureValue bytes, encoded as Base64.
    Returns empty string for the first record (no previous signature).

    [NEED: verify exact input to SHA-256 — raw bytes vs. Base64-decoded vs. text]
    """
    if not previous_signature_value:
        return ""
    sig_bytes = previous_signature_value.encode("utf-8")
    return base64.b64encode(hashlib.sha256(sig_bytes).digest()).decode("ascii")


def build_ticketbai_xml(
    invoice: InvoiceDocument,
    province: TicketBAIProvince,
    software_license: str,
    previous_hash: str | None,
) -> bytes:
    """Build a TicketBAI XML document (unsigned).

    Args:
        invoice: Core InvoiceDocument.
        province: Basque province (araba, gipuzkoa, or bizkaia).
        software_license: TicketBAI software license key.
        previous_hash: HuellaTBAI of the previous record (empty for first).

    Returns:
        UTF-8 TicketBAI XML bytes (unsigned; apply XAdES via es__sign_facturae_xades).
    """
    nsmap = {
        "T": _TBAI_NS,
        "ds": _DS_NS,
        "xades": _XADES_NS,
    }
    root = etree.Element(f"{{{_TBAI_NS}}}TicketBai", nsmap=nsmap)

    # Sujetos (parties)
    sujetos = _sub(root, "Sujetos")
    emisor = _sub(sujetos, "Emisor")
    _sub(emisor, "NIF", invoice.seller.tax_id.identifier)
    _sub(emisor, "ApellidosNombreRazonSocial", invoice.seller.display_name[:120])

    destinatarios = _sub(sujetos, "Destinatarios")
    dest = _sub(destinatarios, "IDDestinatario")
    _sub(dest, "ApellidosNombreRazonSocial", invoice.buyer.display_name[:120])
    if invoice.buyer.tax_id.country_code.upper() == "ES":
        _sub(dest, "NIF", invoice.buyer.tax_id.identifier)
    else:
        id_otro = _sub(dest, "IDOtro")
        _sub(id_otro, "CodigoPais", invoice.buyer.tax_id.country_code.upper())
        _sub(id_otro, "IDType", "02")  # NIF-IVA
        _sub(id_otro, "ID", invoice.buyer.tax_id.identifier)

    # Factura
    factura_elem = _sub(root, "Factura")
    cab_factura = _sub(factura_elem, "CabeceraFactura")
    _sub(cab_factura, "SerieFactura", "")
    _sub(cab_factura, "NumFactura", invoice.number)
    _sub(cab_factura, "FechaExpedicionFactura", fmt_date_es(invoice.date))
    # HoraExpedicionFactura: [NEED: pass as argument or use current time]
    from datetime import datetime  # noqa: PLC0415
    _sub(cab_factura, "HoraExpedicionFactura", datetime.now().strftime("%H:%M:%S"))

    datos_factura = _sub(factura_elem, "DatosFactura")
    _sub(datos_factura, "DescripcionFactura", (invoice.note or "Operación")[:250])

    detalles_iva = _sub(datos_factura, "DetallesIVA")
    tax_base = sum((v.taxable_base for v in invoice.vat_summary), Decimal("0"))
    tax_total = sum((v.vat_amount for v in invoice.vat_summary), Decimal("0"))

    for vat in invoice.vat_summary:
        detalle = _sub(detalles_iva, "DetalleIVA")
        _sub(detalle, "BaseImponible", fmt_amount(vat.taxable_base))
        _sub(detalle, "TipoImpositivo", fmt_amount(vat.vat_rate))
        _sub(detalle, "CuotaImpuesto", fmt_amount(vat.vat_amount))
        _sub(detalle, "OperacionEnRecargoDeEquivalenciaORegimenSimplificado", "N")

    _sub(datos_factura, "ImporteTotalFactura", fmt_amount(tax_base + tax_total))
    _sub(datos_factura, "Claves")  # [NEED: populate TipoFactura keys]

    # HuellaTBAI chain
    huella_tbai = _compute_huella_tbai(previous_hash)
    huella_elem = _sub(root, "HuellaTBAI")
    if huella_tbai:
        _sub(huella_elem, "EncadenamientoFacturaAnterior")
        _sub(huella_elem, "SignatureValueFirmaFacturaAnterior", previous_hash or "")
    _sub(huella_elem, "NumSeriesDispositivoAnterior", "")

    # Software
    sw = _sub(root, "Software")
    _sub(sw, "LicenciaTBAI", software_license)
    _sub(sw, "EntidadDesarrolladora")
    _sub(sw, "Nombre", "mcp-facturacion-electronica-es")
    _sub(sw, "Version", "0.1.0")

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOL_ES_GENERATE_TICKETBAI_XML = types.Tool(
    name="es__generate_ticketbai_xml",
    description=(
        "Genera una factura XML TicketBAI con firma XAdES-EPES y cadena HuellaTBAI. "
        "Selecciona automáticamente el XSD provincial: Álava v1.2, Gipuzkoa v1.2, Bizkaia v2.1. "
        "Los XSDs provinciales NO son intercambiables."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "invoice": {"type": "object", "description": "Datos de la factura."},
            "province": {
                "type": "string",
                "enum": ["araba", "gipuzkoa", "bizkaia"],
            },
            "previous_hash": {
                "type": "string",
                "description": "HuellaTBAI del registro precedente (omitir para el primero).",
            },
            "software_license": {
                "type": "string",
                "description": "Clave de licencia TicketBAI del software certificado.",
            },
            "cert_path": {
                "type": "string",
                "description": "Ruta al certificado PKCS#12 para firma XAdES.",
            },
            "cert_password": {
                "type": "string",
                "description": "Contraseña del certificado.",
            },
        },
        "required": ["invoice", "province", "software_license", "cert_path"],
    },
)

TOOL_ES_SUBMIT_TICKETBAI = types.Tool(
    name="es__submit_ticketbai",
    description=(
        "Envía un registro TicketBAI XML a la autoridad provincial vasca correspondiente. "
        "El endpoint se enruta automáticamente: Álava (batuz.eus), "
        "Gipuzkoa (tbai.egoitza.gipuzkoa.eus), Bizkaia (api.ebizkaia.eus)."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "xml": {"type": "string", "description": "XML TicketBAI firmado."},
            "province": {
                "type": "string",
                "enum": ["araba", "gipuzkoa", "bizkaia"],
            },
            "nif": {"type": "string", "description": "NIF del remitente."},
        },
        "required": ["xml", "province", "nif"],
    },
)

TOOL_ES_VALIDATE_TICKETBAI_SCHEMA = types.Tool(
    name="es__validate_ticketbai_schema",
    description=(
        "Valida un documento XML TicketBAI contra el XSD correcto para la provincia indicada. "
        "Los esquemas NO son intercambiables entre provincias."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "xml": {"type": "string", "description": "XML TicketBAI a validar."},
            "province": {
                "type": "string",
                "enum": ["araba", "gipuzkoa", "bizkaia"],
            },
        },
        "required": ["xml", "province"],
    },
)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def handle_es_generate_ticketbai_xml(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        invoice_data = arguments.get("invoice")
        province_str = arguments.get("province", "")
        software_license = arguments.get("software_license", "")
        cert_path = arguments.get("cert_path", "")
        cert_password: str | None = arguments.get("cert_password") or None
        previous_hash: str | None = arguments.get("previous_hash") or None

        if not invoice_data:
            return err("invoice is required", "MISSING_PARAM")
        if not province_str:
            return err("province is required", "MISSING_PARAM")
        if not software_license:
            return err("software_license is required", "MISSING_PARAM")
        if not cert_path:
            return err("cert_path is required", "MISSING_PARAM")

        try:
            province = TicketBAIProvince(province_str)
        except ValueError:
            return err(f"Invalid province: {province_str!r}. Must be araba, gipuzkoa, or bizkaia.")

        invoice = parse_invoice(invoice_data)

        # Build unsigned XML
        unsigned_xml = build_ticketbai_xml(invoice, province, software_license, previous_hash)

        # Apply XAdES-EPES signature with provincial policy
        policy_id = TICKETBAI_POLICY_IDS.get(province.value)
        config = XAdESSignerConfig(
            cert_path=cert_path,
            cert_password=cert_password,
            signature_policy_id=policy_id,
            # [NEED: set policy hash per province]
        )
        signer = XAdESEPESSigner(config)
        signed_xml = signer.sign(unsigned_xml)

        # The HuellaTBAI for the NEXT record is SHA-256 of this record's SignatureValue
        # (the actual bytes of the SignatureValue element text).
        # Parse the signed XML to extract it.
        signed_root = etree.fromstring(signed_xml)
        sv_elem = signed_root.find(
            f".//{{{_DS_NS}}}SignatureValue"
        )
        next_hash = ""
        if sv_elem is not None and sv_elem.text:
            sv_text = sv_elem.text.strip()
            next_hash = base64.b64encode(
                hashlib.sha256(sv_text.encode("utf-8")).digest()
            ).decode("ascii")

        logger.info(
            "TicketBAI XML generated for %s / %s (province=%s)",
            invoice.seller.tax_id.identifier,
            invoice.number,
            province.value,
        )

        return ok({
            "signed_xml": signed_xml.decode("utf-8"),
            "province": province.value,
            "huella_tbai_for_next": next_hash,
            "invoice_number": invoice.number,
            "notes": [
                "[NEED: verify HuellaTBAI algorithm against official provincial technical spec]",
                "[NEED: set provincial signature policy hash in _helpers.py TICKETBAI_POLICY_IDS]",
            ],
        })

    except ImportError as exc:
        return err(f"cryptography is required for XAdES signing: {exc}", "MISSING_DEPENDENCY")
    except EInvoicingError as exc:
        return err(str(exc))
    except Exception as exc:
        logger.exception("es__generate_ticketbai_xml failed")
        return err(str(exc))


async def handle_es_submit_ticketbai(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        from mcp_einvoicing_core.http_client import AuthMode, BaseEInvoicingClient

        xml_str = arguments.get("xml", "")
        province_str = arguments.get("province", "")
        nif = arguments.get("nif", "")

        if not xml_str:
            return err("xml is required", "MISSING_PARAM")
        if not province_str:
            return err("province is required", "MISSING_PARAM")
        if not nif:
            return err("nif is required", "MISSING_PARAM")

        try:
            province = TicketBAIProvince(province_str)
        except ValueError:
            return err(f"Invalid province: {province_str!r}")

        cert_path = os.environ.get("TICKETBAI_CERTIFICATE_PATH")
        cert_password = os.environ.get("TICKETBAI_CERTIFICATE_PASSWORD")
        if not cert_path:
            return err("TICKETBAI_CERTIFICATE_PATH no está configurado.", "MISSING_CONFIG")

        env = ticketbai_env()
        endpoint = TICKETBAI_ENDPOINTS[province.value][env]

        client = BaseEInvoicingClient(
            base_url=endpoint,
            auth_mode=AuthMode.MTLS,
            cert_path=cert_path,
            cert_password=cert_password,
        )

        xml_bytes = xml_str.encode() if isinstance(xml_str, str) else xml_str
        response = await client._request(
            "POST",
            "",
            files={"xml": ("ticketbai.xml", xml_bytes, "application/xml")},
        )

        return ok({
            "province": province.value,
            "environment": env,
            "endpoint": endpoint,
            "status_code": response.status_code,
            "response": response.text[:2000],
        })

    except Exception as exc:
        logger.exception("es__submit_ticketbai failed")
        return err(str(exc))


async def handle_es_validate_ticketbai_schema(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        import pathlib  # noqa: PLC0415

        xml_str = arguments.get("xml", "")
        province_str = arguments.get("province", "")

        if not xml_str:
            return err("xml is required", "MISSING_PARAM")
        if not province_str:
            return err("province is required", "MISSING_PARAM")

        try:
            province = TicketBAIProvince(province_str)
        except ValueError:
            return err(f"Invalid province: {province_str!r}")

        xml_bytes = xml_str.encode() if isinstance(xml_str, str) else xml_str
        try:
            root = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as exc:
            return ok({
                "valid": False,
                "errors": [f"XML malformado: {exc}"],
                "warnings": [],
                "province": province.value,
                "validation_mode": "structural",
            })

        errors: list[str] = []
        warnings: list[str] = []

        def _req(tag: str) -> None:
            if root.find(f".//*[local-name()='{tag}']") is None:
                errors.append(f"Elemento obligatorio ausente: <{tag}>")

        for tag in [
            "Emisor", "NumFactura", "FechaExpedicionFactura",
            "ImporteTotalFactura", "HuellaTBAI",
        ]:
            _req(tag)

        # Check XSDs per province
        xsd_dir = (
            pathlib.Path(__file__).parent.parent.parent
            / "specs" / "ticketbai" / province.value
        )
        xsd_files = list(xsd_dir.glob("*.xsd")) if xsd_dir.exists() else []
        validation_mode = "structural"

        if xsd_files:
            try:
                schema = etree.XMLSchema(etree.parse(str(xsd_files[0])))
                schema.validate(root)
                for e in schema.error_log:
                    errors.append(f"[XSD-{province.value}] {e.message} (línea {e.line})")
                validation_mode = f"xsd-{province.value}"
            except Exception as exc:
                warnings.append(f"XSD validation failed to run: {exc}")
        else:
            warnings.append(
                f"XSD provincial de {province.value} no disponible — "
                f"descárguelo a specs/ticketbai/{province.value}/ para validación completa."
            )

        return ok({
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "province": province.value,
            "validation_mode": validation_mode,
        })

    except Exception as exc:
        logger.exception("es__validate_ticketbai_schema failed")
        return err(str(exc))
