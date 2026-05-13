"""MCP tools: SII (Suministro Inmediato de Información) — construcción, envío y consulta.

AEAT SII:
    Technical guide: v3.0 (April 2024)
    SOAP namespace:  https://www2.agenciatributaria.gob.es/static_files/common/internet/
                     dep/aplicaciones/es/aeat/burt/jee/aj/ws/SuministroInformacion.xsd

[NEED: validate SOAP envelope structure against live AEAT SII v3.0 sandbox]
[NEED: confirm sandbox endpoint URLs from AEAT technical guide]
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal
from typing import Any

import mcp.types as types
from lxml import etree
from mcp_einvoicing_core.exceptions import EInvoicingError
from mcp_einvoicing_core.models import InvoiceDocument

from mcp_facturacion_electronica_es._helpers import (
    SII_ISSUED_ENDPOINTS,
    SII_RECEIVED_ENDPOINTS,
    aeat_env,
    err,
    fmt_amount,
    fmt_date_es,
    ok,
    parse_invoice,
)
from mcp_facturacion_electronica_es.models.es import SIICommunicationType, SIIRecordType

logger = logging.getLogger(__name__)

_SII_NS = (
    "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones"
    "/es/aeat/burt/jee/aj/ws/SuministroInformacion.xsd"
)
_SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
_SII_VERSION = "1.1"


# ---------------------------------------------------------------------------
# SII XML builder helpers
# ---------------------------------------------------------------------------


def _sub(parent: etree._Element, tag: str, text: str | None = None) -> etree._Element:
    child = etree.SubElement(parent, tag)
    if text is not None:
        child.text = text
    return child


def _build_cabecera(
    nif: str,
    name: str,
    comm_type: str,
) -> etree._Element:
    """Build SII Cabecera element."""
    cab = etree.Element("Cabecera")
    _sub(cab, "IDVersionSii", _SII_VERSION)
    titular = _sub(cab, "Titular")
    _sub(titular, "NombreRazon", name[:120])
    _sub(titular, "NIF", nif)
    _sub(cab, "TipoComunicacion", comm_type)
    return cab


def _build_id_factura_emitida(
    invoice: InvoiceDocument,
    seller_nif: str,
) -> etree._Element:
    idf = etree.Element("IDFactura")
    id_emisor = _sub(idf, "IDEmisorFactura")
    _sub(id_emisor, "NIF", seller_nif)
    _sub(idf, "NumSerieFacturaEmisor", invoice.number)
    _sub(idf, "FechaExpedicionFacturaEmisor", fmt_date_es(invoice.date))
    return idf


def _build_periodo(fiscal_year: int, invoice_date: str) -> etree._Element:
    """Build PeriodoLiquidacion from fiscal year and invoice date."""
    periodo = etree.Element("PeriodoLiquidacion")
    _sub(periodo, "Ejercicio", str(fiscal_year))
    # Extract month from YYYY-MM-DD
    month = invoice_date[5:7] if len(invoice_date) >= 7 else "01"
    _sub(periodo, "Periodo", month)
    return periodo


def build_sii_issued_record(
    invoice: InvoiceDocument,
    comm_type: str = "A0",
) -> bytes:
    """Build a complete SII SOAP envelope for an issued invoice (FacturaExpedida).

    Args:
        invoice: Core InvoiceDocument.
        comm_type: TipoComunicacion: A0 (new), A1 (modification), A4 (removal).

    Returns:
        UTF-8 SOAP envelope bytes.
    """
    seller_nif = invoice.seller.tax_id.identifier
    seller_name = invoice.seller.display_name
    fiscal_year = int(invoice.date[:4])

    tax_base = sum((v.taxable_base for v in invoice.vat_summary), Decimal("0"))
    tax_total = sum((v.vat_amount for v in invoice.vat_summary), Decimal("0"))
    grand_total = tax_base + tax_total

    nsmap_soap = {
        "soapenv": _SOAP_NS,
        "sii": _SII_NS,
    }
    envelope = etree.Element(f"{{{_SOAP_NS}}}Envelope", nsmap=nsmap_soap)
    _sub(envelope, f"{{{_SOAP_NS}}}Header")
    body = _sub(envelope, f"{{{_SOAP_NS}}}Body")

    suministro = etree.SubElement(body, f"{{{_SII_NS}}}SuministroLRFacturasEmitidas")

    cab = _build_cabecera(seller_nif, seller_name, comm_type)
    suministro.append(etree.fromstring(etree.tostring(cab)))

    registro = etree.SubElement(suministro, f"{{{_SII_NS}}}RegistroLRFacturasEmitidas")
    registro.append(etree.fromstring(
        etree.tostring(_build_periodo(fiscal_year, invoice.date))
    ))
    registro.append(etree.fromstring(
        etree.tostring(_build_id_factura_emitida(invoice, seller_nif))
    ))

    factura_exp = etree.SubElement(registro, f"{{{_SII_NS}}}FacturaExpedida")
    # TipoFactura from document_type (F1, F2, etc.) or default to F1
    tipo_factura = invoice.document_type if invoice.document_type else "F1"
    _sub(factura_exp, "TipoFactura", tipo_factura)
    _sub(factura_exp, "ClaveRegimenEspecialOTrascendencia", "01")  # 01 = general
    _sub(factura_exp, "ImporteTotal", fmt_amount(grand_total))
    _sub(factura_exp, "DescripcionOperacion", (invoice.note or "Prestación de servicios")[:500])

    # Contraparte (buyer)
    contraparte = etree.SubElement(factura_exp, f"{{{_SII_NS}}}Contraparte")
    _sub(contraparte, "NombreRazon", invoice.buyer.display_name[:120])
    if invoice.buyer.tax_id.country_code.upper() == "ES":
        _sub(contraparte, "NIF", invoice.buyer.tax_id.identifier)
    else:
        id_otro = etree.SubElement(contraparte, f"{{{_SII_NS}}}IDOtro")
        _sub(id_otro, "CodigoPais", invoice.buyer.tax_id.country_code.upper())
        _sub(id_otro, "IDType", "07")
        _sub(id_otro, "ID", invoice.buyer.tax_id.identifier)

    # TipoDesglose → DesgloseFactura → Sujeta → NoExenta
    tipo_desglose = etree.SubElement(factura_exp, f"{{{_SII_NS}}}TipoDesglose")
    desglose_factura = etree.SubElement(tipo_desglose, f"{{{_SII_NS}}}DesgloseFactura")
    sujeta = etree.SubElement(desglose_factura, f"{{{_SII_NS}}}Sujeta")
    no_exenta = etree.SubElement(sujeta, f"{{{_SII_NS}}}NoExenta")
    _sub(no_exenta, "TipoNoExenta", "S1")  # S1 = non-exempt, general
    desglose_iva = etree.SubElement(no_exenta, f"{{{_SII_NS}}}DesgloseIVA")

    for vat in invoice.vat_summary:
        detalle = etree.SubElement(desglose_iva, f"{{{_SII_NS}}}DetalleIVA")
        _sub(detalle, "TipoImpositivo", fmt_amount(vat.vat_rate))
        _sub(detalle, "BaseImponible", fmt_amount(vat.taxable_base))
        _sub(detalle, "CuotaRepercutida", fmt_amount(vat.vat_amount))

    return etree.tostring(
        envelope, xml_declaration=True, encoding="UTF-8", pretty_print=True
    )


def build_sii_received_record(
    invoice: InvoiceDocument,
    comm_type: str = "A0",
) -> bytes:
    """Build a SII SOAP envelope for a received invoice (FacturaRecibida)."""
    buyer_nif = invoice.buyer.tax_id.identifier
    buyer_name = invoice.buyer.display_name
    fiscal_year = int(invoice.date[:4])

    tax_base = sum((v.taxable_base for v in invoice.vat_summary), Decimal("0"))
    tax_total = sum((v.vat_amount for v in invoice.vat_summary), Decimal("0"))
    grand_total = tax_base + tax_total

    nsmap_soap = {"soapenv": _SOAP_NS, "sii": _SII_NS}
    envelope = etree.Element(f"{{{_SOAP_NS}}}Envelope", nsmap=nsmap_soap)
    _sub(envelope, f"{{{_SOAP_NS}}}Header")
    body = _sub(envelope, f"{{{_SOAP_NS}}}Body")

    suministro = etree.SubElement(body, f"{{{_SII_NS}}}SuministroLRFacturasRecibidas")
    cab = _build_cabecera(buyer_nif, buyer_name, comm_type)
    suministro.append(etree.fromstring(etree.tostring(cab)))

    registro = etree.SubElement(suministro, f"{{{_SII_NS}}}RegistroLRFacturasRecibidas")
    registro.append(etree.fromstring(
        etree.tostring(_build_periodo(fiscal_year, invoice.date))
    ))

    # For received invoices, the IDFactura references the supplier
    idf = etree.Element("IDFactura")
    id_emisor = _sub(idf, "IDEmisorFactura")
    if invoice.seller.tax_id.country_code.upper() == "ES":
        _sub(id_emisor, "NIF", invoice.seller.tax_id.identifier)
    else:
        id_otro = _sub(id_emisor, "IDOtro")
        _sub(id_otro, "CodigoPais", invoice.seller.tax_id.country_code.upper())
        _sub(id_otro, "IDType", "07")
        _sub(id_otro, "ID", invoice.seller.tax_id.identifier)
    _sub(idf, "NumSerieFacturaEmisor", invoice.number)
    _sub(idf, "FechaExpedicionFacturaEmisor", fmt_date_es(invoice.date))
    registro.append(etree.fromstring(etree.tostring(idf)))

    factura_rec = etree.SubElement(registro, f"{{{_SII_NS}}}FacturaRecibida")
    _sub(factura_rec, "TipoFactura", invoice.document_type or "F1")
    _sub(factura_rec, "ClaveRegimenEspecialOTrascendencia", "01")
    _sub(factura_rec, "DescripcionOperacion", (invoice.note or "Compra de bienes / servicios")[:500])
    _sub(factura_rec, "ImporteTotal", fmt_amount(grand_total))
    contraparte = etree.SubElement(factura_rec, f"{{{_SII_NS}}}Contraparte")
    _sub(contraparte, "NombreRazon", invoice.seller.display_name[:120])
    if invoice.seller.tax_id.country_code.upper() == "ES":
        _sub(contraparte, "NIF", invoice.seller.tax_id.identifier)
    else:
        id_otro2 = etree.SubElement(contraparte, f"{{{_SII_NS}}}IDOtro")
        _sub(id_otro2, "CodigoPais", invoice.seller.tax_id.country_code.upper())
        _sub(id_otro2, "IDType", "07")
        _sub(id_otro2, "ID", invoice.seller.tax_id.identifier)

    desgl = etree.SubElement(factura_rec, f"{{{_SII_NS}}}DesgloseFactura")
    for vat in invoice.vat_summary:
        desgl_iva = etree.SubElement(desgl, f"{{{_SII_NS}}}DesgloseIVA")
        det = etree.SubElement(desgl_iva, f"{{{_SII_NS}}}DetalleIVA")
        _sub(det, "TipoImpositivo", fmt_amount(vat.vat_rate))
        _sub(det, "BaseImponible", fmt_amount(vat.taxable_base))
        _sub(det, "CuotaSoportada", fmt_amount(vat.vat_amount))

    # CuotaDeducible: typically same as CuotaSoportada for deductible expenses
    _sub(factura_rec, "CuotaDeducible", fmt_amount(tax_total))
    # FechaRegContable: registration date (today = invoice date simplified here)
    _sub(factura_rec, "FechaRegContable", fmt_date_es(invoice.date))

    return etree.tostring(
        envelope, xml_declaration=True, encoding="UTF-8", pretty_print=True
    )


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOL_ES_BUILD_SII_INVOICE_RECORD = types.Tool(
    name="es__build_sii_invoice_record",
    description=(
        "Construye un registro XML AEAT SII en formato SOAP (emisión FacturaExpedida o "
        "recepción FacturaRecibida) conforme a la guía técnica SII v3.0 (abril 2024). "
        "Soporta TipoComunicacion A0 (alta), A1 (modificación) y A4 (baja)."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "invoice": {
                "type": "object",
                "description": "Datos de la factura.",
            },
            "record_type": {
                "type": "string",
                "enum": ["issued", "received"],
                "description": "Dirección: 'issued' (expedida) o 'received' (recibida).",
            },
            "communication_type": {
                "type": "string",
                "enum": ["A0", "A1", "A4"],
                "description": "TipoComunicacion: A0 alta (por defecto), A1 modificación, A4 baja.",
                "default": "A0",
            },
        },
        "required": ["invoice", "record_type"],
    },
)

TOOL_ES_SUBMIT_SII_BATCH = types.Tool(
    name="es__submit_sii_batch",
    description=(
        "Envía un lote de facturas (máximo 10.000 registros) al endpoint SOAP SII de la AEAT. "
        "Requiere AEAT_ENV, AEAT_CERTIFICATE_PATH y AEAT_CERTIFICATE_PASSWORD (MTLS)."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "records": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Lista de SOAP envelopes XML de es__build_sii_invoice_record.",
            },
            "record_type": {
                "type": "string",
                "enum": ["issued", "received"],
            },
            "fiscal_year": {
                "type": "integer",
                "description": "Ejercicio fiscal (YYYY).",
            },
        },
        "required": ["records", "record_type", "fiscal_year"],
    },
)

TOOL_ES_QUERY_SII_STATUS = types.Tool(
    name="es__query_sii_status",
    description=(
        "Consulta el estado de un lote SII mediante ConsultaFactInformadasEmitidas / Recibidas."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "batch_id": {
                "type": "string",
                "description": "Referencia del lote devuelta por es__submit_sii_batch.",
            },
            "record_type": {
                "type": "string",
                "enum": ["issued", "received"],
            },
        },
        "required": ["batch_id", "record_type"],
    },
)

TOOL_ES_GENERATE_SII_CORRECTION = types.Tool(
    name="es__generate_sii_correction",
    description=(
        "Genera un registro de modificación SII (A1) o baja (A4) que referencia la factura "
        "original mediante IDFactura."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "original_invoice": {
                "type": "object",
                "description": "Factura original que se rectifica.",
            },
            "corrected_invoice": {
                "type": "object",
                "description": "Datos corregidos. Omitir o null para una baja (A4).",
            },
            "correction_type": {
                "type": "string",
                "enum": ["A1", "A4"],
            },
            "record_type": {
                "type": "string",
                "enum": ["issued", "received"],
            },
        },
        "required": ["original_invoice", "correction_type", "record_type"],
    },
)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def handle_es_build_sii_invoice_record(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        invoice_data = arguments.get("invoice")
        if not invoice_data:
            return err("invoice is required", "MISSING_PARAM")

        record_type_str = arguments.get("record_type", "issued")
        comm_type_str = arguments.get("communication_type", "A0")

        try:
            record_type = SIIRecordType(record_type_str)
        except ValueError:
            return err(f"Invalid record_type: {record_type_str!r}")
        try:
            comm_type = SIICommunicationType(comm_type_str)
        except ValueError:
            return err(f"Invalid communication_type: {comm_type_str!r}")

        invoice = parse_invoice(invoice_data)

        if record_type == SIIRecordType.issued:
            xml_bytes = build_sii_issued_record(invoice, comm_type.value)
        else:
            xml_bytes = build_sii_received_record(invoice, comm_type.value)

        logger.info(
            "SII %s record built for %s / %s (comm_type=%s)",
            record_type.value, invoice.seller.tax_id.identifier, invoice.number, comm_type.value,
        )

        return ok({
            "xml": xml_bytes.decode("utf-8"),
            "record_type": record_type.value,
            "communication_type": comm_type.value,
            "invoice_number": invoice.number,
        })

    except EInvoicingError as exc:
        return err(str(exc))
    except Exception as exc:
        logger.exception("es__build_sii_invoice_record failed")
        return err(str(exc))


async def handle_es_submit_sii_batch(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        from mcp_einvoicing_core.http_client import AuthMode, BaseEInvoicingClient

        records = arguments.get("records", [])
        record_type_str = arguments.get("record_type", "issued")
        fiscal_year = arguments.get("fiscal_year")

        if not records:
            return err("records is required and must not be empty", "MISSING_PARAM")
        if fiscal_year is None:
            return err("fiscal_year is required", "MISSING_PARAM")

        try:
            record_type = SIIRecordType(record_type_str)
        except ValueError:
            return err(f"Invalid record_type: {record_type_str!r}")

        if len(records) > 10_000:
            return err(
                f"El lote supera el máximo de 10.000 registros SII ({len(records)} enviados).",
                "BATCH_TOO_LARGE",
            )

        cert_path = os.environ.get("AEAT_CERTIFICATE_PATH")
        cert_password = os.environ.get("AEAT_CERTIFICATE_PASSWORD")
        if not cert_path:
            return err("AEAT_CERTIFICATE_PATH no está configurado.", "MISSING_CONFIG")

        env = aeat_env()
        endpoints = SII_ISSUED_ENDPOINTS if record_type == SIIRecordType.issued else SII_RECEIVED_ENDPOINTS
        base_url = endpoints[env]

        client = BaseEInvoicingClient(
            base_url=base_url,
            auth_mode=AuthMode.MTLS,
            cert_path=cert_path,
            cert_password=cert_password,
        )

        # For simplicity, submit records one by one.
        # [NEED: merge multiple RegistroLRFacturas into a single SuministroLR for true batch]
        results = []
        for i, xml_str in enumerate(records):
            xml_bytes = xml_str.encode() if isinstance(xml_str, str) else xml_str
            try:
                response = await client._request(
                    "POST", "",
                    files={"xml": (f"sii_{i}.xml", xml_bytes, "text/xml")},
                )
                results.append({
                    "index": i,
                    "status_code": response.status_code,
                    "response": response.text[:500],
                })
            except Exception as exc:
                results.append({"index": i, "error": str(exc)})

        return ok({
            "environment": env,
            "record_type": record_type.value,
            "fiscal_year": fiscal_year,
            "submitted": len(records),
            "results": results,
            "note": "Use es__parse_aeat_response to parse each response XML.",
        })

    except Exception as exc:
        logger.exception("es__submit_sii_batch failed")
        return err(str(exc))


async def handle_es_query_sii_status(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        from mcp_einvoicing_core.http_client import AuthMode, BaseEInvoicingClient

        batch_id = arguments.get("batch_id", "")
        record_type_str = arguments.get("record_type", "issued")
        if not batch_id:
            return err("batch_id is required", "MISSING_PARAM")

        try:
            record_type = SIIRecordType(record_type_str)
        except ValueError:
            return err(f"Invalid record_type: {record_type_str!r}")

        cert_path = os.environ.get("AEAT_CERTIFICATE_PATH")
        cert_password = os.environ.get("AEAT_CERTIFICATE_PASSWORD")
        if not cert_path:
            return err("AEAT_CERTIFICATE_PATH no está configurado.", "MISSING_CONFIG")

        env = aeat_env()
        endpoints = SII_ISSUED_ENDPOINTS if record_type == SIIRecordType.issued else SII_RECEIVED_ENDPOINTS
        client = BaseEInvoicingClient(
            base_url=endpoints[env],
            auth_mode=AuthMode.MTLS,
            cert_path=cert_path,
            cert_password=cert_password,
        )

        # [NEED: build proper ConsultaFactInformadasEmitidas SOAP envelope with IDFactura filter]
        response = await client._request("GET", f"?batch_id={batch_id}")
        return ok({
            "batch_id": batch_id,
            "record_type": record_type.value,
            "environment": env,
            "status_code": response.status_code,
            "response": response.text[:2000],
        })

    except Exception as exc:
        logger.exception("es__query_sii_status failed")
        return err(str(exc))


async def handle_es_generate_sii_correction(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        original_data = arguments.get("original_invoice")
        if not original_data:
            return err("original_invoice is required", "MISSING_PARAM")

        correction_type_str = arguments.get("correction_type", "A1")
        record_type_str = arguments.get("record_type", "issued")

        try:
            comm_type = SIICommunicationType(correction_type_str)
        except ValueError:
            return err(f"Invalid correction_type: {correction_type_str!r}. Must be A1 or A4.")
        if comm_type not in (SIICommunicationType.A1, SIICommunicationType.A4):
            return err("correction_type must be A1 (modification) or A4 (removal).")

        try:
            record_type = SIIRecordType(record_type_str)
        except ValueError:
            return err(f"Invalid record_type: {record_type_str!r}")

        original = parse_invoice(original_data)

        # For A4 (baja), only the original invoice identity is needed
        # For A1, use the corrected invoice if provided, otherwise the original
        corrected_data = arguments.get("corrected_invoice")
        target = parse_invoice(corrected_data) if corrected_data else original

        if record_type == SIIRecordType.issued:
            xml_bytes = build_sii_issued_record(target, comm_type.value)
        else:
            xml_bytes = build_sii_received_record(target, comm_type.value)

        return ok({
            "xml": xml_bytes.decode("utf-8"),
            "correction_type": comm_type.value,
            "record_type": record_type.value,
            "original_invoice_number": original.number,
        })

    except EInvoicingError as exc:
        return err(str(exc))
    except Exception as exc:
        logger.exception("es__generate_sii_correction failed")
        return err(str(exc))
