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
from decimal import Decimal
from typing import Any

import mcp.types as types
from lxml import etree
from mcp_einvoicing_core.base_server import assert_not_read_only
from mcp_einvoicing_core.confirmation import ConfirmationGate
from mcp_einvoicing_core.exceptions import EInvoicingError
from mcp_einvoicing_core.models import InvoiceDocument
from mcp_einvoicing_core.signer_client import SignerClient
from mcp_einvoicing_core.xml_utils import safe_fromstring

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
from mcp_facturacion_electronica_es.config import aeat_settings
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


def _mask_nif(nif: str) -> str:
    """Mask a NIF for safe logging: retain first 4 and last 1 characters."""
    if len(nif) <= 5:
        return nif[:1] + "***" + nif[-1:]
    return nif[:4] + "*" * (len(nif) - 5) + nif[-1:]


def _parse_sii_response(raw: str) -> dict[str, Any]:
    """Parse an AEAT SII SOAP response into a structured dict with masked NIFs.

    Returns:
        {
            "estado_envio": str,
            "csv": str | None,
            "accepted": [...],
            "rejected": [{"nif_masked", "error_code", "message"}],
        }
    """
    result: dict[str, Any] = {
        "estado_envio": None,
        "csv": None,
        "accepted": [],
        "rejected": [],
    }
    if not raw:
        return result
    try:
        root = safe_fromstring(raw.encode() if isinstance(raw, str) else raw)
        estado_elems = root.xpath(".//*[local-name()='EstadoEnvio']")
        if estado_elems:
            result["estado_envio"] = estado_elems[0].text
        csv_elems = root.xpath(".//*[local-name()='CSV']")
        if csv_elems:
            result["csv"] = csv_elems[0].text

        for linea in root.xpath(".//*[local-name()='RespuestaLinea']"):
            estado = None
            error_code = None
            message = None
            nif = None
            for child in linea.iter():
                tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""
                if tag == "EstadoRegistro":
                    estado = child.text
                elif tag == "CodigoErrorRegistro":
                    error_code = child.text
                elif tag == "DescripcionErrorRegistro":
                    message = child.text
                elif tag == "NIF":
                    nif = child.text
            entry: dict[str, Any] = {"estado": estado}
            if nif:
                entry["nif_masked"] = _mask_nif(nif)
            if estado == "Correcto":
                result["accepted"].append(entry)
            else:
                entry["error_code"] = error_code
                entry["message"] = message
                result["rejected"].append(entry)
    except Exception as exc:
        result["parse_error"] = f"Could not parse SII response: {exc}"
    return result


def _merge_sii_records(
    records_xml: list[str],
    seller_nif: str,
    seller_name: str,
    comm_type: str,
    record_type: SIIRecordType,
) -> bytes:
    """Merge multiple SII record XML strings into one SuministroLR envelope.

    Per SII spec, up to 10,000 RegistroLRFacturas fit in a single envelope.
    """
    nsmap_soap = {
        "soapenv": _SOAP_NS,
        "sii": _SII_NS,
    }
    envelope = etree.Element(f"{{{_SOAP_NS}}}Envelope", nsmap=nsmap_soap)
    _sub(envelope, f"{{{_SOAP_NS}}}Header")
    body = _sub(envelope, f"{{{_SOAP_NS}}}Body")

    if record_type == SIIRecordType.issued:
        suministro_tag = "SuministroLRFacturasEmitidas"
    else:
        suministro_tag = "SuministroLRFacturasRecibidas"

    suministro = etree.SubElement(body, f"{{{_SII_NS}}}{suministro_tag}")

    cab = _build_cabecera(seller_nif, seller_name, comm_type)
    suministro.append(safe_fromstring(etree.tostring(cab)))

    for xml_str in records_xml:
        xml_bytes = xml_str.encode() if isinstance(xml_str, str) else xml_str
        record_root = safe_fromstring(xml_bytes)
        registros = record_root.xpath(".//*[local-name()='RegistroLRFacturasEmitidas']")
        if not registros:
            registros = record_root.xpath(".//*[local-name()='RegistroLRFacturasRecibidas']")
        for reg in registros:
            suministro.append(reg)

    return etree.tostring(envelope, xml_declaration=True, encoding="UTF-8", pretty_print=True)


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
    clave_regimen: str = "01",
    impuesto: str = "01",
) -> bytes:
    """Build a complete SII SOAP envelope for an issued invoice (FacturaExpedida).

    Args:
        invoice: Core InvoiceDocument.
        comm_type: TipoComunicacion: A0 (new), A1 (modification), A4 (removal).
        clave_regimen: ClaveRegimenEspecialOTrascendencia (default "01" general).
        impuesto: Impuesto code, "01" IVA, "02" IGIC, "03" IPSI (default "01").

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
    suministro.append(safe_fromstring(etree.tostring(cab)))

    registro = etree.SubElement(suministro, f"{{{_SII_NS}}}RegistroLRFacturasEmitidas")
    registro.append(etree.fromstring(etree.tostring(_build_periodo(fiscal_year, invoice.date))))
    registro.append(
        etree.fromstring(etree.tostring(_build_id_factura_emitida(invoice, seller_nif)))
    )

    factura_exp = etree.SubElement(registro, f"{{{_SII_NS}}}FacturaExpedida")
    # TipoFactura from document_type (F1, F2, etc.) or default to F1
    tipo_factura = invoice.document_type if invoice.document_type else "F1"
    _sub(factura_exp, "TipoFactura", tipo_factura)
    _sub(factura_exp, "ClaveRegimenEspecialOTrascendencia", clave_regimen)
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

    return etree.tostring(envelope, xml_declaration=True, encoding="UTF-8", pretty_print=True)


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
    suministro.append(safe_fromstring(etree.tostring(cab)))

    registro = etree.SubElement(suministro, f"{{{_SII_NS}}}RegistroLRFacturasRecibidas")
    registro.append(etree.fromstring(etree.tostring(_build_periodo(fiscal_year, invoice.date))))

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
    registro.append(safe_fromstring(etree.tostring(idf)))

    factura_rec = etree.SubElement(registro, f"{{{_SII_NS}}}FacturaRecibida")
    _sub(factura_rec, "TipoFactura", invoice.document_type or "F1")
    _sub(factura_rec, "ClaveRegimenEspecialOTrascendencia", "01")
    _sub(
        factura_rec, "DescripcionOperacion", (invoice.note or "Compra de bienes / servicios")[:500]
    )
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

    return etree.tostring(envelope, xml_declaration=True, encoding="UTF-8", pretty_print=True)


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
        "Consulta el estado de facturas en el SII mediante ConsultaFactInformadasEmitidas / "
        "ConsultaFactInformadasRecibidas (SOAP). Filtra por ejercicio, periodo y, "
        "opcionalmente, por NIF del emisor y numero de factura."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "nif_titular": {
                "type": "string",
                "description": "NIF del titular SII (obligado tributario).",
            },
            "nombre_titular": {
                "type": "string",
                "description": "Nombre o razon social del titular.",
            },
            "fiscal_year": {
                "type": "integer",
                "description": "Ejercicio fiscal (YYYY).",
            },
            "period": {
                "type": "string",
                "description": "Periodo de liquidacion: '01'..'12' para mensual, o '0A' para anual.",
            },
            "record_type": {
                "type": "string",
                "enum": ["issued", "received"],
                "description": "Tipo de registro: 'issued' (expedidas) o 'received' (recibidas).",
            },
            "invoice_number": {
                "type": "string",
                "description": "NumSerieFacturaEmisor para filtrar por factura concreta (opcional).",
            },
            "emisor_nif": {
                "type": "string",
                "description": "NIF del emisor para filtrar (opcional, solo para received).",
            },
        },
        "required": ["nif_titular", "nombre_titular", "fiscal_year", "period", "record_type"],
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
        clave_regimen: str = arguments.get("clave_regimen", "01")

        if record_type == SIIRecordType.issued:
            xml_bytes = build_sii_issued_record(
                invoice,
                comm_type.value,
                clave_regimen=clave_regimen,
            )
        else:
            xml_bytes = build_sii_received_record(invoice, comm_type.value)

        logger.info(
            "SII %s record built for %s / %s (comm_type=%s)",
            record_type.value,
            invoice.seller.tax_id.identifier,
            invoice.number,
            comm_type.value,
        )

        return ok(
            {
                "xml": xml_bytes.decode("utf-8"),
                "record_type": record_type.value,
                "communication_type": comm_type.value,
                "invoice_number": invoice.number,
            }
        )

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
        confirmation_token: str | None = arguments.get("confirmation_token") or None

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

        assert_not_read_only("AEAT_READ_ONLY")
        gate = ConfirmationGate.get_default()
        if not gate.is_confirmed(confirmation_token):
            env_label = aeat_env()
            return ok(
                gate.pending_response(
                    action="es__submit_sii_batch",
                    summary=(
                        f"Submit {len(records)} SII {record_type_str} record(s) to AEAT "
                        f"({env_label}, ejercicio {fiscal_year}). "
                        "SII records are immediately reported to the Tax Agency."
                    ),
                    token=confirmation_token,
                )
            )

        env = aeat_env()
        endpoints = (
            SII_ISSUED_ENDPOINTS if record_type == SIIRecordType.issued else SII_RECEIVED_ENDPOINTS
        )
        base_url = endpoints[env]

        use_signer = SignerClient.is_configured()
        if use_signer:
            signer = SignerClient.from_env()
        else:
            cert_path = aeat_settings.certificate_path
            cert_password = aeat_settings.certificate_password
            if not cert_path:
                return err("AEAT_CERTIFICATE_PATH no está configurado.", "MISSING_CONFIG")
            logger.warning(
                "es__submit_sii_batch: signer microservice not configured — "
                "cert material is in the MCP process (security risk)."
            )
            client = BaseEInvoicingClient(
                base_url=base_url,
                auth_mode=AuthMode.MTLS,
                cert_path=cert_path,
                cert_password=cert_password,
            )

        # ES-LC-1: merge all records into a single SuministroLR envelope
        first_record = safe_fromstring(
            records[0].encode() if isinstance(records[0], str) else records[0]
        )
        nif_elems = first_record.xpath(".//*[local-name()='NIF']")
        seller_nif = nif_elems[0].text if nif_elems else ""
        name_elems = first_record.xpath(".//*[local-name()='NombreRazon']")
        seller_name = name_elems[0].text if name_elems else ""

        merged_xml = _merge_sii_records(
            records_xml=records,
            seller_nif=seller_nif,
            seller_name=seller_name,
            comm_type="A0",
            record_type=record_type,
        )

        try:
            if use_signer:
                resp = await signer.mtls_submit_files(  # type: ignore[possibly-undefined]
                    base_url,
                    [("xml", "sii_batch.xml", merged_xml, "text/xml")],
                )
                raw_body = resp.get("body", "")
                status_code = resp["status_code"]
            else:
                response = await client._request(  # type: ignore[possibly-undefined]
                    "POST",
                    "",
                    files={"xml": ("sii_batch.xml", merged_xml, "text/xml")},
                )
                raw_body = response.text
                status_code = response.status_code

            parsed = _parse_sii_response(raw_body)
        except Exception as exc:
            parsed = {"error": str(exc)}
            status_code = 0

        gate.consume(confirmation_token)
        return ok(
            {
                "environment": env,
                "record_type": record_type.value,
                "fiscal_year": fiscal_year,
                "submitted": len(records),
                "status_code": status_code,
                "parsed_response": parsed,
            }
        )

    except Exception as exc:
        logger.exception("es__submit_sii_batch failed")
        return err(str(exc))


def _build_sii_consulta_envelope(
    nif: str,
    name: str,
    fiscal_year: int,
    period: str,
    record_type: SIIRecordType,
    invoice_number: str | None = None,
    emisor_nif: str | None = None,
) -> bytes:
    """Build a SII ConsultaFactInformadasEmitidas / Recibidas SOAP envelope.

    ES-LC-2: The SII status endpoint is SOAP-only. REST GET is not supported.
    This constructs the correct ConsultaLRFacturasEmitidas or ConsultaLRFacturasRecibidas
    SOAP envelope per the SII technical guide v3.0.
    """
    _SII_CONSULTA_NS = (
        "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones"
        "/es/aeat/ssii/fact/ws/ConsultaLR.xsd"
    )
    nsmap_soap = {
        "soapenv": _SOAP_NS,
        "sii": _SII_NS,
        "con": _SII_CONSULTA_NS,
    }
    envelope = etree.Element(f"{{{_SOAP_NS}}}Envelope", nsmap=nsmap_soap)
    _sub(envelope, f"{{{_SOAP_NS}}}Header")
    body = _sub(envelope, f"{{{_SOAP_NS}}}Body")

    if record_type == SIIRecordType.issued:
        op_name = "ConsultaLRFacturasEmitidas"
    else:
        op_name = "ConsultaLRFacturasRecibidas"

    consulta = etree.SubElement(body, f"{{{_SII_NS}}}{op_name}")

    cab = _build_cabecera(nif, name, "A0")
    consulta.append(safe_fromstring(etree.tostring(cab)))

    # FiltroConsulta
    filtro = etree.SubElement(consulta, f"{{{_SII_NS}}}FiltroConsulta")
    periodo = etree.SubElement(filtro, f"{{{_SII_NS}}}PeriodoLiquidacion")
    _sub(periodo, "Ejercicio", str(fiscal_year))
    _sub(periodo, "Periodo", period)

    if invoice_number or emisor_nif:
        id_factura = etree.SubElement(filtro, f"{{{_SII_NS}}}IDFactura")
        if emisor_nif and record_type == SIIRecordType.received:
            id_emisor = etree.SubElement(id_factura, f"{{{_SII_NS}}}IDEmisorFactura")
            _sub(id_emisor, "NIF", emisor_nif)
        if invoice_number:
            _sub(id_factura, "NumSerieFacturaEmisor", invoice_number)

    return etree.tostring(envelope, xml_declaration=True, encoding="UTF-8", pretty_print=True)


async def handle_es_query_sii_status(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    """Query SII invoice status via SOAP ConsultaFactInformadasEmitidas/Recibidas.

    ES-LC-2: replaced non-functional REST GET with correct SOAP envelope.
    """
    try:
        from mcp_einvoicing_core.http_client import AuthMode, BaseEInvoicingClient

        nif_titular = arguments.get("nif_titular", "")
        nombre_titular = arguments.get("nombre_titular", "")
        fiscal_year = arguments.get("fiscal_year")
        period = arguments.get("period", "")
        record_type_str = arguments.get("record_type", "issued")
        invoice_number: str | None = arguments.get("invoice_number") or None
        emisor_nif: str | None = arguments.get("emisor_nif") or None

        for name, val in [
            ("nif_titular", nif_titular),
            ("nombre_titular", nombre_titular),
            ("period", period),
        ]:
            if not val:
                return err(f"{name} is required", "MISSING_PARAM")
        if fiscal_year is None:
            return err("fiscal_year is required", "MISSING_PARAM")

        try:
            record_type = SIIRecordType(record_type_str)
        except ValueError:
            return err(f"Invalid record_type: {record_type_str!r}")

        soap_bytes = _build_sii_consulta_envelope(
            nif=nif_titular,
            name=nombre_titular,
            fiscal_year=int(fiscal_year),
            period=period,
            record_type=record_type,
            invoice_number=invoice_number,
            emisor_nif=emisor_nif,
        )

        cert_path = aeat_settings.certificate_path
        if not cert_path:
            # Return the SOAP envelope without submitting if no certificate is configured
            return ok(
                {
                    "soap_envelope": soap_bytes.decode("utf-8"),
                    "note": (
                        "AEAT_CERTIFICATE_PATH no configurado — SOAP envelope generado pero no enviado. "
                        "Configure el certificado FNMT-RCM para enviar la consulta."
                    ),
                    "record_type": record_type.value,
                    "fiscal_year": fiscal_year,
                    "period": period,
                }
            )

        env = aeat_env()
        endpoints = (
            SII_ISSUED_ENDPOINTS if record_type == SIIRecordType.issued else SII_RECEIVED_ENDPOINTS
        )
        cert_password = aeat_settings.certificate_password
        client = BaseEInvoicingClient(
            base_url=endpoints[env],
            auth_mode=AuthMode.MTLS,
            cert_path=cert_path,
            cert_password=cert_password,
        )

        response = await client._request(
            "POST",
            "",
            data=soap_bytes,
            headers={"Content-Type": "text/xml; charset=utf-8"},
        )

        # Parse SOAP response — extract EstadoEnvio without echoing raw AEAT response
        raw_text = response.text
        parsed_status: dict[str, Any] = {}
        try:
            resp_root = safe_fromstring(raw_text.encode())
            # Extract key SII response fields using local-name() for namespace-agnostic lookup
            for field in ["EstadoEnvio", "CSV", "TipoComunicacion"]:
                elems = resp_root.xpath(f".//*[local-name()='{field}']")
                if elems:
                    parsed_status[field] = elems[0].text
        except Exception:
            parsed_status["parse_error"] = "Could not parse AEAT SOAP response"

        logger.info(
            "SII consulta %s: ejercicio=%s periodo=%s status=%s",
            record_type.value,
            fiscal_year,
            period,
            response.status_code,
        )
        return ok(
            {
                "record_type": record_type.value,
                "fiscal_year": fiscal_year,
                "period": period,
                "environment": env,
                "status_code": response.status_code,
                "parsed_response": parsed_status,
            }
        )

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

        return ok(
            {
                "xml": xml_bytes.decode("utf-8"),
                "correction_type": comm_type.value,
                "record_type": record_type.value,
                "original_invoice_number": original.number,
            }
        )

    except EInvoicingError as exc:
        return err(str(exc))
    except Exception as exc:
        logger.exception("es__generate_sii_correction failed")
        return err(str(exc))
