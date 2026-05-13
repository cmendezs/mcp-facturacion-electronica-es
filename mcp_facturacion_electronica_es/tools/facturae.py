"""MCP tools: Facturae / FACe — generación XML, firma XAdES, envío y consulta.

Facturae 3.2.2:
    Namespace: http://www.facturae.gob.es/formato/Version3.2.2/Facturae32.xsd
    Schema:    https://www.facturae.gob.es/formato/Paginas/version-3-2.aspx

FACe REST API v2:
    Sandbox:    https://se-face.redsara.es/factura-face-b2b-api/api/v2
    Production: https://face.gob.es/factura-face-b2b-api/api/v2

XAdES-EPES policy (Orden EHA/962/2007):
    URI: http://www.facturae.es/politica_de_firma_formato_facturae/
         politica_de_firma_formato_facturae_v3_1.pdf
    [NEED: compute SHA-256 of the policy PDF and set FACTURAE_POLICY_HASH in _helpers.py]

[NEED: download Facturae 3.2.2 XSD into specs/facturae/ for full schema validation]
[NEED: validate FACe REST API v2 OAuth2 flow against live FACe sandbox credentials]
"""

from __future__ import annotations

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
    FACE_BASE_URLS,
    FACTURAE_POLICY_HASH,
    FACTURAE_POLICY_ID,
    err,
    face_env,
    fmt_amount,
    ok,
    parse_invoice,
)

logger = logging.getLogger(__name__)

_FACTURAE_NS = "http://www.facturae.gob.es/formato/Version3.2.2/Facturae32.xsd"
_DS_NS = "http://www.w3.org/2000/09/xmldsig#"
_XADES_NS = "http://uri.etsi.org/01903/v1.3.2#"


# ---------------------------------------------------------------------------
# Facturae 3.2.2 XML builder
# ---------------------------------------------------------------------------


def _sub(parent: etree._Element, tag: str, text: str | None = None) -> etree._Element:
    child = etree.SubElement(parent, tag)
    if text is not None:
        child.text = text
    return child


def _build_tax_id_block(party_elem: etree._Element, party: Any) -> None:
    """Append TaxIdentification sub-elements to a SellerParty or BuyerParty element."""
    ti = _sub(party_elem, "TaxIdentification")
    is_person = bool(party.first_name)
    _sub(ti, "PersonTypeCode", "F" if is_person else "J")
    country = party.tax_id.country_code.upper()
    res_type = "R" if country == "ES" else ("U" if country in _EU_COUNTRIES else "E")
    _sub(ti, "ResidenceTypeCode", res_type)
    _sub(ti, "TaxIdentificationNumber", party.tax_id.identifier)


_EU_COUNTRIES = frozenset({
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "FI", "FR", "GR",
    "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT",
    "RO", "SE", "SI", "SK",
})


def _build_legal_block(party_elem: etree._Element, party: Any) -> None:
    """Append LegalEntity or Individual block."""
    if party.name:
        le = _sub(party_elem, "LegalEntity")
        _sub(le, "CorporateName", party.name[:80])
        if party.address:
            addr = _sub(le, "AddressInSpain" if party.tax_id.country_code == "ES" else "OverseasAddress")
            _sub(addr, "Address", party.address.street[:80])
            _sub(addr, "PostCode", party.address.postal_code[:10])
            _sub(addr, "Town", party.address.city[:50])
            if party.address.country_code == "ES":
                _sub(addr, "Province", (party.address.province or "")[:20])
            _sub(addr, "CountryCode", party.address.country_code.upper())
    else:
        ind = _sub(party_elem, "Individual")
        _sub(ind, "Name", party.first_name or "")
        _sub(ind, "FirstSurname", party.last_name or "")


def build_facturae_xml(invoice: InvoiceDocument) -> bytes:
    """Build a Facturae 3.2.2 XML document from an InvoiceDocument.

    Args:
        invoice: Validated core InvoiceDocument.

    Returns:
        UTF-8 encoded Facturae 3.2.2 XML bytes (unsigned).
    """
    nsmap = {
        None: _FACTURAE_NS,
        "ds": _DS_NS,
        "xades": _XADES_NS,
    }
    root = etree.Element("Facturae", nsmap=nsmap)

    # FileHeader
    fh = _sub(root, "FileHeader")
    _sub(fh, "SchemaVersion", "3.2.2")
    _sub(fh, "Modality", "I")  # I = individual invoice
    _sub(fh, "InvoiceIssuerType", "EU")  # EU = private seller

    # Compute totals
    tax_base = sum((v.taxable_base for v in invoice.vat_summary), Decimal("0"))
    tax_total = sum((v.vat_amount for v in invoice.vat_summary), Decimal("0"))
    grand_total = tax_base + tax_total

    batch = _sub(fh, "Batch")
    _sub(batch, "BatchIdentifier", invoice.number)
    _sub(batch, "InvoicesCount", "1")
    ta = _sub(batch, "TotalInvoicesAmount")
    _sub(ta, "TotalAmount", fmt_amount(grand_total))
    oa = _sub(batch, "TotalOutstandingAmount")
    _sub(oa, "TotalAmount", fmt_amount(grand_total))
    ea = _sub(batch, "TotalExecutableAmount")
    _sub(ea, "TotalAmount", fmt_amount(grand_total))
    _sub(batch, "InvoiceCurrencyCode", invoice.currency.upper())

    # Parties
    parties = _sub(root, "Parties")
    seller_elem = _sub(parties, "SellerParty")
    _build_tax_id_block(seller_elem, invoice.seller)
    _build_legal_block(seller_elem, invoice.seller)

    buyer_elem = _sub(parties, "BuyerParty")
    _build_tax_id_block(buyer_elem, invoice.buyer)
    _build_legal_block(buyer_elem, invoice.buyer)

    # Invoices
    invoices_elem = _sub(root, "Invoices")
    inv = _sub(invoices_elem, "Invoice")

    ih = _sub(inv, "InvoiceHeader")
    _sub(ih, "InvoiceNumber", invoice.number)
    _sub(ih, "InvoiceDocumentType", "FC")  # FC = complete invoice
    _sub(ih, "InvoiceClass", "OO")          # OO = original

    iid = _sub(inv, "InvoiceIssueData")
    _sub(iid, "IssueDate", invoice.date)
    _sub(iid, "InvoiceCurrencyCode", invoice.currency.upper())
    _sub(iid, "TaxCurrencyCode", invoice.currency.upper())
    _sub(iid, "LanguageName", "es")

    # TaxesOutputs
    taxes = _sub(inv, "TaxesOutputs")
    for vat in invoice.vat_summary:
        tax = _sub(taxes, "Tax")
        _sub(tax, "TaxTypeCode", "01")  # 01 = IVA
        _sub(tax, "TaxRate", fmt_amount(vat.vat_rate))
        tb = _sub(tax, "TaxableBase")
        _sub(tb, "TotalAmount", fmt_amount(vat.taxable_base))
        ta_elem = _sub(tax, "TaxAmount")
        _sub(ta_elem, "TotalAmount", fmt_amount(vat.vat_amount))

    # InvoiceTotals
    totals = _sub(inv, "InvoiceTotals")
    _sub(totals, "TotalGrossAmount", fmt_amount(tax_base))
    _sub(totals, "TotalGeneralDiscounts", "0.00")
    _sub(totals, "TotalGeneralSurcharges", "0.00")
    _sub(totals, "TotalGrossAmountBeforeTaxes", fmt_amount(tax_base))
    _sub(totals, "TotalTaxOutputs", fmt_amount(tax_total))
    _sub(totals, "TotalTaxesWithheld", "0.00")
    _sub(totals, "InvoiceTotal", fmt_amount(grand_total))
    _sub(totals, "TotalOutstandingAmount", fmt_amount(grand_total))
    _sub(totals, "TotalExecutableAmount", fmt_amount(grand_total))

    # Items
    if invoice.lines:
        items = _sub(inv, "Items")
        for line in invoice.lines:
            il = _sub(items, "InvoiceLine")
            _sub(il, "ItemDescription", line.description[:2500])
            if line.quantity is not None:
                _sub(il, "Quantity", fmt_amount(line.quantity))
            _sub(il, "UnitPriceWithoutTax", fmt_amount(line.unit_price))
            _sub(il, "TotalCost", fmt_amount(line.total_price))
            _sub(il, "GrossAmount", fmt_amount(line.total_price))
            line_taxes = _sub(il, "TaxesOutputs")
            lt = _sub(line_taxes, "Tax")
            _sub(lt, "TaxTypeCode", "01")
            _sub(lt, "TaxRate", fmt_amount(line.vat_rate))
            ltb = _sub(lt, "TaxableBase")
            _sub(ltb, "TotalAmount", fmt_amount(line.total_price))
            lta = _sub(lt, "TaxAmount")
            _sub(lta, "TotalAmount", fmt_amount(line.total_price * line.vat_rate / 100))

    # PaymentDetails (if provided)
    if invoice.payment:
        pd = _sub(inv, "PaymentDetails")
        installment = _sub(pd, "Installment")
        _sub(installment, "InstallmentDueDate", invoice.payment.due_date or invoice.date)
        _sub(installment, "InstallmentAmount", fmt_amount(invoice.payment.amount))
        _sub(installment, "PaymentMeans", invoice.payment.payment_method_code or "01")
        if invoice.payment.iban:
            _sub(installment, "AccountToBeCredited")
            # AccountToBeCredited needs full bank details; simplified here
            # [NEED: add IBAN and BIC fields per Facturae 3.2.2 schema]

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOL_ES_GENERATE_FACTURAE_XML = types.Tool(
    name="es__generate_facturae_xml",
    description=(
        "Genera una factura XML conforme a Facturae 3.2.2 para envío B2G al portal FACe. "
        "El documento generado está sin firmar; use es__sign_facturae_xades para firmarlo."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "invoice": {
                "type": "object",
                "description": "InvoiceDocument con seller, buyer, vat_summary y lines.",
            },
            "schema_version": {
                "type": "string",
                "description": "Versión del esquema Facturae (por defecto: '3.2.2').",
                "default": "3.2.2",
            },
        },
        "required": ["invoice"],
    },
)

TOOL_ES_SIGN_FACTURAE_XADES = types.Tool(
    name="es__sign_facturae_xades",
    description=(
        "Aplica una firma digital XAdES-EPES (ETSI EN 319 132-1) a un documento Facturae XML. "
        "Usa el certificado PKCS#12 indicado para firmar con SHA-256 + RSA. "
        "La política de firma por defecto es la de Facturae (Orden EHA/962/2007)."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "xml": {"type": "string", "description": "XML Facturae sin firmar."},
            "cert_path": {
                "type": "string",
                "description": "Ruta al certificado PKCS#12 (.p12 / .pfx).",
            },
            "cert_password": {
                "type": "string",
                "description": "Contraseña del certificado (omitir si sin protección).",
            },
            "signature_policy_id": {
                "type": "string",
                "description": (
                    "OID/URI de la política de firma. "
                    "Por defecto: política Facturae (Orden EHA/962/2007)."
                ),
            },
            "signature_policy_hash": {
                "type": "string",
                "description": "SHA-256 base64 del documento de política de firma.",
            },
        },
        "required": ["xml", "cert_path"],
    },
)

TOOL_ES_SUBMIT_TO_FACE = types.Tool(
    name="es__submit_to_face",
    description=(
        "Envía un XML Facturae firmado con XAdES a FACe (Punto General de Entrada de Facturas "
        "Electrónicas) a través de la API REST B2B de FACe v2. "
        "Requiere FACE_ENV, FACE_CLIENT_ID y FACE_CLIENT_SECRET."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "xml": {"type": "string", "description": "XML Facturae con firma XAdES."},
            "administrative_unit": {
                "type": "string",
                "description": "Código UnidadTramitadora de FACe.",
            },
            "accounting_office": {
                "type": "string",
                "description": "Código OficinasContables de FACe.",
            },
            "management_body": {
                "type": "string",
                "description": "Código OrganoGestor de FACe.",
            },
        },
        "required": ["xml", "administrative_unit", "accounting_office", "management_body"],
    },
)

TOOL_ES_GET_FACE_INVOICE_STATUS = types.Tool(
    name="es__get_face_invoice_status",
    description=(
        "Consulta el estado de tramitación de una factura en FACe. "
        "Códigos: 1200 Registrada, 2400 Reconocida, 3100 Rechazada, 4100 Pagada."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "invoice_id": {"type": "string", "description": "Número de registro FACe."},
        },
        "required": ["invoice_id"],
    },
)

TOOL_ES_VALIDATE_FACTURAE_SCHEMA = types.Tool(
    name="es__validate_facturae_schema",
    description=(
        "Valida un XML Facturae contra el XSD oficial 3.2.2. Realiza validación estructural "
        "y, si el XSD está disponible en specs/facturae/, también validación de esquema completa."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "xml": {"type": "string", "description": "XML Facturae a validar."},
            "schema_version": {
                "type": "string",
                "description": "Versión del esquema (por defecto: '3.2.2').",
                "default": "3.2.2",
            },
        },
        "required": ["xml"],
    },
)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def handle_es_generate_facturae_xml(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        invoice_data = arguments.get("invoice")
        if not invoice_data:
            return err("invoice is required", "MISSING_PARAM")

        invoice = parse_invoice(invoice_data)
        xml_bytes = build_facturae_xml(invoice)

        logger.info("Facturae 3.2.2 XML generated for invoice %s", invoice.number)
        return ok({
            "xml": xml_bytes.decode("utf-8"),
            "schema_version": "3.2.2",
            "invoice_number": invoice.number,
            "next_step": "Use es__sign_facturae_xades to apply XAdES-EPES signature before submitting to FACe.",
        })

    except EInvoicingError as exc:
        return err(str(exc))
    except Exception as exc:
        logger.exception("es__generate_facturae_xml failed")
        return err(str(exc))


async def handle_es_sign_facturae_xades(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        xml_str = arguments.get("xml", "")
        cert_path = arguments.get("cert_path", "")
        if not xml_str:
            return err("xml is required", "MISSING_PARAM")
        if not cert_path:
            return err("cert_path is required", "MISSING_PARAM")

        cert_password: str | None = arguments.get("cert_password") or None
        policy_id: str = arguments.get("signature_policy_id") or FACTURAE_POLICY_ID
        policy_hash: str | None = arguments.get("signature_policy_hash") or FACTURAE_POLICY_HASH

        config = XAdESSignerConfig(
            cert_path=cert_path,
            cert_password=cert_password,
            signature_policy_id=policy_id,
            signature_policy_hash=policy_hash,
        )
        signer = XAdESEPESSigner(config)

        xml_bytes = xml_str.encode() if isinstance(xml_str, str) else xml_str
        signed_bytes = signer.sign(xml_bytes)

        logger.info("Facturae XAdES-EPES signature applied with cert %s", cert_path)

        notes: list[str] = []
        if not policy_hash:
            notes.append(
                "[NEED: set FACTURAE_POLICY_HASH in _helpers.py — compute SHA-256 of "
                "the Facturae signature policy PDF for full EPES compliance]"
            )

        result: dict[str, Any] = {
            "signed_xml": signed_bytes.decode("utf-8"),
            "signature_policy": policy_id,
        }
        if notes:
            result["notes"] = notes
        return ok(result)

    except ImportError as exc:
        return err(
            f"cryptography>=42.0.0 is required for XAdES signing: {exc}",
            "MISSING_DEPENDENCY",
        )
    except Exception as exc:
        logger.exception("es__sign_facturae_xades failed")
        return err(str(exc))


async def handle_es_submit_to_face(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        from mcp_einvoicing_core.http_client import AuthMode, BaseEInvoicingClient, OAuthConfig

        xml_str = arguments.get("xml", "")
        admin_unit = arguments.get("administrative_unit", "")
        accounting_office = arguments.get("accounting_office", "")
        management_body = arguments.get("management_body", "")

        for name, val in [
            ("xml", xml_str), ("administrative_unit", admin_unit),
            ("accounting_office", accounting_office), ("management_body", management_body),
        ]:
            if not val:
                return err(f"{name} is required", "MISSING_PARAM")

        client_id = os.environ.get("FACE_CLIENT_ID", "")
        client_secret = os.environ.get("FACE_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            return err(
                "FACE_CLIENT_ID y FACE_CLIENT_SECRET son obligatorios.",
                "MISSING_CONFIG",
            )

        env = face_env()
        base_url = FACE_BASE_URLS[env]

        # [NEED: verify FACe OAuth2 token endpoint URL for sandbox and production]
        oauth_cfg = OAuthConfig(
            token_url=f"{base_url}/oauth/token",
            client_id=client_id,
            client_secret=client_secret,
        )
        client = BaseEInvoicingClient(
            base_url=base_url,
            auth_mode=AuthMode.OAUTH2_CLIENT_CREDENTIALS,
            oauth_config=oauth_cfg,
        )

        xml_bytes = xml_str.encode() if isinstance(xml_str, str) else xml_str
        payload = {
            "unidadTramitadora": admin_unit,
            "oficinasContables": accounting_office,
            "organoGestor": management_body,
        }
        response = await client._request(
            "POST",
            "/facturas",
            json=payload,
            files={"factura": ("factura.xml", xml_bytes, "application/xml")},
        )

        return ok({
            "status_code": response.status_code,
            "environment": env,
            "response": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text[:2000],
        })

    except Exception as exc:
        logger.exception("es__submit_to_face failed")
        return err(str(exc))


async def handle_es_get_face_invoice_status(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        from mcp_einvoicing_core.http_client import AuthMode, BaseEInvoicingClient, OAuthConfig

        invoice_id = arguments.get("invoice_id", "")
        if not invoice_id:
            return err("invoice_id is required", "MISSING_PARAM")

        client_id = os.environ.get("FACE_CLIENT_ID", "")
        client_secret = os.environ.get("FACE_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            return err("FACE_CLIENT_ID y FACE_CLIENT_SECRET son obligatorios.", "MISSING_CONFIG")

        env = face_env()
        base_url = FACE_BASE_URLS[env]
        oauth_cfg = OAuthConfig(
            token_url=f"{base_url}/oauth/token",
            client_id=client_id,
            client_secret=client_secret,
        )
        client = BaseEInvoicingClient(
            base_url=base_url,
            auth_mode=AuthMode.OAUTH2_CLIENT_CREDENTIALS,
            oauth_config=oauth_cfg,
        )

        response = await client._request("GET", f"/facturas/{invoice_id}")
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"raw": response.text}

        # Map known FACe status codes
        status_codes = {
            "1200": "Registrada",
            "2400": "Reconocida por la unidad tramitadora",
            "3100": "Rechazada",
            "4100": "Pagada",
        }
        raw_status = str(body.get("codigo", body.get("status", "")))
        return ok({
            "invoice_id": invoice_id,
            "status_code": raw_status,
            "status_description": status_codes.get(raw_status, "Desconocido"),
            "environment": env,
            "response": body,
        })

    except Exception as exc:
        logger.exception("es__get_face_invoice_status failed")
        return err(str(exc))


async def handle_es_validate_facturae_schema(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        xml_str = arguments.get("xml", "")
        if not xml_str:
            return err("xml is required", "MISSING_PARAM")

        xml_bytes = xml_str.encode() if isinstance(xml_str, str) else xml_str
        try:
            root = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as exc:
            return ok({
                "valid": False,
                "errors": [f"XML malformado: {exc}"],
                "warnings": [],
                "validation_mode": "structural",
            })

        errors: list[str] = []
        warnings: list[str] = []

        def _req(tag: str) -> None:
            if not root.xpath(f".//*[local-name()='{tag}']"):
                errors.append(f"Elemento obligatorio ausente: <{tag}>")

        for tag in [
            "SchemaVersion", "Modality", "InvoiceIssuerType",
            "SellerParty", "BuyerParty",
            "InvoiceNumber", "IssueDate",
            "TaxesOutputs", "InvoiceTotals",
        ]:
            _req(tag)

        # XSD validation if available
        xsd_dir = (
            __import__("pathlib").Path(__file__).parent.parent.parent
            / "specs" / "facturae"
        )
        xsd_files = list(xsd_dir.glob("*.xsd")) if xsd_dir.exists() else []
        validation_mode = "structural"

        if xsd_files:
            try:
                schema = etree.XMLSchema(etree.parse(str(xsd_files[0])))
                schema.validate(root)
                for e in schema.error_log:
                    errors.append(f"[XSD] {e.message} (línea {e.line})")
                validation_mode = "xsd"
            except Exception as exc:
                warnings.append(f"XSD validation failed to run: {exc}")
        else:
            warnings.append(
                "Validación XSD no disponible — descargue el XSD de Facturae 3.2.2 "
                "desde facturae.gob.es a specs/facturae/ para validación completa."
            )

        return ok({
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "validation_mode": validation_mode,
        })

    except Exception as exc:
        logger.exception("es__validate_facturae_schema failed")
        return err(str(exc))
