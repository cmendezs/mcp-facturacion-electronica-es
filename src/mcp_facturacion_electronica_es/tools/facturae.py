"""MCP tools: Facturae / FACe — generación XML, firma XAdES, envío y consulta.

Facturae 3.2.2:
    Namespace: http://www.facturae.gob.es/formato/Versiones/Facturaev3_2_2.xml
    Schema:    specs/facturae/xsd/Facturaev3_2_2.xml
    Source:    https://www.facturae.gob.es/formato/Versiones/Esquema_0_3_2_2_20200304.zip

FACe integrator REST API:
    Sandbox:    https://se-api-face.redsara.es
    Production: https://api.face.gob.es
    Source:     specs/facturae/documentation/FACe-manual-api-integradores.pdf s2.2

XAdES-EPES policy (Orden EHA/962/2007):
    URI: http://www.facturae.es/politica_de_firma_formato_facturae/
         politica_de_firma_formato_facturae_v3_1.pdf
    Hash: SHA-1, from AEAT-validated .xsig (FACTURAE_POLICY_HASH in _helpers.py)

FACe authentication: JWS-signed JWT (RS256, x5c header with clean-PEM cert, 5-min TTL).
    Payload carries a "username" claim: SHA-1 hex digest of the clean-PEM cert bytes
    (same bytes as the x5c header entry). Uses AuthMode.JWS from mcp-einvoicing-core
    (core v1.16.0). [Inference] header/claim shape per s2.3; not yet validated
    against a live AEAT sandbox acknowledgement.
    Source: FACe-manual-api-integradores.pdf s2.3 "Conceptos de autenticación".
"""

from __future__ import annotations

import base64
import hashlib
import logging
from decimal import Decimal
from typing import Any

from lxml import etree
from mcp_einvoicing_core.base_server import assert_not_read_only
from mcp_einvoicing_core.confirmation import ConfirmationGate
from mcp_einvoicing_core.digital_signature import (
    XAdESEPESSigner,
    XAdESSignerConfig,
    load_certificate_der,
)
from mcp_einvoicing_core.exceptions import EInvoicingError
from mcp_einvoicing_core.http_client import AuthMode, BaseEInvoicingClient, JWSConfig
from mcp_einvoicing_core.models import InvoiceDocument
from mcp_einvoicing_core.signer_client import SignerClient
from mcp_einvoicing_core.xml_utils import safe_fromstring

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
from mcp_facturacion_electronica_es.config import aeat_settings
from mcp_facturacion_electronica_es.models.es import FACTURAE_TAX_TYPE_CODES, SpanishTaxType

logger = logging.getLogger(__name__)

# ES-SC-1: correct namespace confirmed from specs/facturae/xsd/Facturaev3_2_2.xml targetNamespace
_FACTURAE_NS = "http://www.facturae.gob.es/formato/Versiones/Facturaev3_2_2.xml"
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


_EU_COUNTRIES = frozenset(
    {
        "AT",
        "BE",
        "BG",
        "CY",
        "CZ",
        "DE",
        "DK",
        "EE",
        "FI",
        "FR",
        "GR",
        "HR",
        "HU",
        "IE",
        "IT",
        "LT",
        "LU",
        "LV",
        "MT",
        "NL",
        "PL",
        "PT",
        "RO",
        "SE",
        "SI",
        "SK",
    }
)


def _build_legal_block(party_elem: etree._Element, party: Any) -> None:
    """Append LegalEntity or Individual block."""
    if party.name:
        le = _sub(party_elem, "LegalEntity")
        _sub(le, "CorporateName", party.name[:80])
        if party.address:
            addr = _sub(
                le, "AddressInSpain" if party.tax_id.country_code == "ES" else "OverseasAddress"
            )
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


def build_facturae_xml(
    invoice: InvoiceDocument,
    invoice_issuer_type: str = "EU",
    irpf_amount: Decimal | None = None,
    irpf_rate: Decimal | None = None,
    resolution_reference: str | None = None,
    receiver_transaction_reference: str | None = None,
    tax_type: str = "IVA",
    recargo_equivalencia_rate: Decimal | None = None,
    recargo_equivalencia_amount: Decimal | None = None,
) -> bytes:
    """Build a Facturae 3.2.2 XML document from an InvoiceDocument.

    Args:
        invoice: Validated core InvoiceDocument.
        invoice_issuer_type: "EU" (private seller), "EM" (issuer is buyer), "TE" (third party).
        irpf_amount: IRPF withholding amount to deduct from invoice total.
        irpf_rate: IRPF withholding rate as a percentage (e.g. 15.00), emitted in the
            <TaxesWithheld><Tax TaxTypeCode="04"> block alongside irpf_amount.
        resolution_reference: PA resolution reference (B2G invoices).
        receiver_transaction_reference: PA receiver transaction reference (B2G invoices).
        tax_type: Applicable indirect tax: "IVA", "IPSI", or "IGIC" (SpanishTaxType).
            Applies to every tax line on the invoice: mixed IGIC/IVA on a single
            invoice is not supported. IGIC/IPSI rate values are caller-supplied via
            each line's vat_rate; this package does not assert Canary Islands IGIC
            rate values ([NEED: verify IGIC rates], ES-INV-1).
        recargo_equivalencia_rate: Recargo de Equivalencia surcharge rate (percentage)
            applied on top of IVA for retailers under the special regime.
        recargo_equivalencia_amount: Explicit surcharge amount; computed from
            taxable_base * recargo_equivalencia_rate / 100 when omitted.

    Returns:
        UTF-8 encoded Facturae 3.2.2 XML bytes (unsigned).
    """
    tax_type_code = FACTURAE_TAX_TYPE_CODES[SpanishTaxType(tax_type)]
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
    _sub(fh, "InvoiceIssuerType", invoice_issuer_type)

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
    _sub(ih, "InvoiceClass", "OO")  # OO = original
    if resolution_reference:
        _sub(ih, "ResolutionReference", resolution_reference)
    if receiver_transaction_reference:
        _sub(ih, "ReceiverTransactionReference", receiver_transaction_reference)

    iid = _sub(inv, "InvoiceIssueData")
    _sub(iid, "IssueDate", invoice.date)
    _sub(iid, "InvoiceCurrencyCode", invoice.currency.upper())
    _sub(iid, "TaxCurrencyCode", invoice.currency.upper())
    _sub(iid, "LanguageName", "es")

    # TaxesOutputs
    taxes = _sub(inv, "TaxesOutputs")
    recargo_total = Decimal("0")
    for vat in invoice.vat_summary:
        tax = _sub(taxes, "Tax")
        _sub(tax, "TaxTypeCode", tax_type_code)
        _sub(tax, "TaxRate", fmt_amount(vat.vat_rate))
        tb = _sub(tax, "TaxableBase")
        _sub(tb, "TotalAmount", fmt_amount(vat.taxable_base))
        ta_elem = _sub(tax, "TaxAmount")
        _sub(ta_elem, "TotalAmount", fmt_amount(vat.vat_amount))
        if recargo_equivalencia_rate is not None:
            re_amount = recargo_equivalencia_amount
            if re_amount is None:
                re_amount = vat.taxable_base * recargo_equivalencia_rate / Decimal("100")
            recargo_total += re_amount
            _sub(tax, "EquivalenceSurcharge", fmt_amount(recargo_equivalencia_rate))
            esa = _sub(tax, "EquivalenceSurchargeAmount")
            _sub(esa, "TotalAmount", fmt_amount(re_amount))

    # TaxesWithheld (IRPF, TaxTypeCode 04): sibling of TaxesOutputs
    withheld = irpf_amount or Decimal("0")
    if withheld:
        withheld_elem = _sub(inv, "TaxesWithheld")
        wtax = _sub(withheld_elem, "Tax")
        _sub(wtax, "TaxTypeCode", "04")  # 04 = IRPF
        _sub(wtax, "TaxRate", fmt_amount(irpf_rate or Decimal("0")))
        wtb = _sub(wtax, "TaxableBase")
        _sub(wtb, "TotalAmount", fmt_amount(tax_base))
        wta = _sub(wtax, "TaxAmount")
        _sub(wta, "TotalAmount", fmt_amount(withheld))

    # InvoiceTotals
    tax_output_total = tax_total + recargo_total
    totals = _sub(inv, "InvoiceTotals")
    _sub(totals, "TotalGrossAmount", fmt_amount(tax_base))
    _sub(totals, "TotalGeneralDiscounts", "0.00")
    _sub(totals, "TotalGeneralSurcharges", "0.00")
    _sub(totals, "TotalGrossAmountBeforeTaxes", fmt_amount(tax_base))
    _sub(totals, "TotalTaxOutputs", fmt_amount(tax_output_total))
    _sub(totals, "TotalTaxesWithheld", fmt_amount(withheld))
    invoice_total = tax_base + tax_output_total - withheld
    _sub(totals, "InvoiceTotal", fmt_amount(invoice_total))
    _sub(totals, "TotalOutstandingAmount", fmt_amount(invoice_total))
    _sub(totals, "TotalExecutableAmount", fmt_amount(invoice_total))

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
            _sub(lt, "TaxTypeCode", tax_type_code)
            _sub(lt, "TaxRate", fmt_amount(line.vat_rate))
            ltb = _sub(lt, "TaxableBase")
            _sub(ltb, "TotalAmount", fmt_amount(line.total_price))
            lta = _sub(lt, "TaxAmount")
            _sub(lta, "TotalAmount", fmt_amount(line.total_price * line.vat_rate / Decimal("100")))

    # PaymentDetails (if provided)
    if invoice.payment:
        pd = _sub(inv, "PaymentDetails")
        installment = _sub(pd, "Installment")
        _sub(installment, "InstallmentDueDate", invoice.payment.due_date or invoice.date)
        _sub(installment, "InstallmentAmount", fmt_amount(invoice.payment.amount))
        _sub(installment, "PaymentMeans", invoice.payment.payment_method_code or "01")
        if invoice.payment.iban:
            acct = _sub(installment, "AccountToBeCredited")
            _sub(acct, "IBAN", invoice.payment.iban)
            if invoice.payment.bic:
                _sub(acct, "BankCode", invoice.payment.bic)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# FACe JWS authentication (ES-LC-14) and response masking (ES-SH-7)
# ---------------------------------------------------------------------------


def _build_face_client(base_url: str) -> BaseEInvoicingClient:
    """Build a FACe-authenticated HTTP client using JWS per FACe manual s2.3.

    The JWT payload carries a "username" claim: the SHA-1 hex digest of the
    certificate's clean-PEM bytes (base64 DER, no BEGIN/END markers, no line
    breaks), the same bytes attached as the JOSE header's x5c claim. SHA-1 is
    used because it is what the FACe spec mandates for this claim, not as a
    security-relevant hash.
    """
    cert_path = aeat_settings.certificate_path or ""
    if not cert_path:
        raise EInvoicingError(
            "AEAT_CERTIFICATE_PATH es obligatorio para autenticación JWS con FACe "
            "(FACe-manual-api-integradores.pdf s2.3)."
        )
    clean_pem = base64.b64encode(
        load_certificate_der(cert_path, aeat_settings.certificate_password)
    )
    username_claim = hashlib.sha1(clean_pem).hexdigest()
    jws_config = JWSConfig(
        cert_path=cert_path,
        cert_password=aeat_settings.certificate_password,
        ttl_seconds=300,
        extra_claims={"username": username_claim},
    )
    return BaseEInvoicingClient(base_url=base_url, auth_mode=AuthMode.JWS, jws_config=jws_config)


def _parse_face_response(response: Any) -> dict[str, Any]:
    """Extract a structured, non-sensitive subset from a raw FACe HTTP response.

    Never returns the full raw response body to the LLM (ES-SH-7): only the
    known FACe response fields are surfaced.
    """
    body: dict[str, Any] = {}
    if response.headers.get("content-type", "").startswith("application/json"):
        try:
            body = response.json()
        except Exception:
            body = {}
    return {
        "status_code": response.status_code,
        "codigo": body.get("codigo"),
        "descripcion": body.get("descripcion"),
        "numeroRegistro": body.get("numeroRegistro"),
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def es__generate_facturae_xml(
    invoice: dict[str, Any],
    schema_version: str = "3.2.2",
    invoice_issuer_type: str = "EU",
    tax_type: str = "IVA",
    recargo_equivalencia_rate: float | None = None,
    recargo_equivalencia_amount: float | None = None,
    irpf_amount: float | None = None,
    irpf_rate: float | None = None,
    resolution_reference: str | None = None,
    receiver_transaction_reference: str | None = None,
) -> dict[str, Any]:
    """Genera una factura XML conforme a Facturae 3.2.2 para envío B2G al portal FACe.

    El documento generado está sin firmar; use es__sign_facturae_xades para firmarlo.

    Args:
        invoice: InvoiceDocument con seller, buyer, vat_summary y lines.
        schema_version: Versión del esquema Facturae (por defecto: '3.2.2').
        invoice_issuer_type: EU (emisor=vendedor), EM (emisor=comprador),
            TE (tercero). Por defecto: 'EU'.
        tax_type: Impuesto indirecto aplicable a todas las líneas de la factura
            (IVA: península/Baleares; IPSI: Ceuta/Melilla; IGIC: Canarias).
            No se admite mezclar impuestos en una misma factura. Por defecto: 'IVA'.
        recargo_equivalencia_rate: Tipo de Recargo de Equivalencia (%), si aplica.
        recargo_equivalencia_amount: Importe explícito del Recargo de Equivalencia.
            Si se omite, se calcula como base_imponible * recargo_equivalencia_rate / 100.
        irpf_amount: Importe de retención IRPF a deducir del total de la factura.
        irpf_rate: Tipo de retención IRPF (%), emitido en TaxesWithheld.
        resolution_reference: ResolutionReference para facturas B2G a
            Administraciones Públicas.
        receiver_transaction_reference: ReceiverTransactionReference para
            facturas B2G.
    """
    del schema_version  # reserved for future multi-version XSD selection
    try:
        parsed_invoice = parse_invoice(invoice)

        def _opt_decimal(raw: float | None) -> Decimal | None:
            return Decimal(str(raw)) if raw is not None else None

        xml_bytes = build_facturae_xml(
            parsed_invoice,
            invoice_issuer_type=invoice_issuer_type,
            irpf_amount=_opt_decimal(irpf_amount),
            irpf_rate=_opt_decimal(irpf_rate),
            resolution_reference=resolution_reference,
            receiver_transaction_reference=receiver_transaction_reference,
            tax_type=tax_type,
            recargo_equivalencia_rate=_opt_decimal(recargo_equivalencia_rate),
            recargo_equivalencia_amount=_opt_decimal(recargo_equivalencia_amount),
        )

        logger.info("Facturae 3.2.2 XML generated for invoice %s", parsed_invoice.number)
        return ok(
            {
                "xml": xml_bytes.decode("utf-8"),
                "schema_version": "3.2.2",
                "invoice_number": parsed_invoice.number,
                "next_step": "Use es__sign_facturae_xades to apply XAdES-EPES signature before submitting to FACe.",
            }
        )

    except EInvoicingError as exc:
        return err(str(exc))
    except Exception as exc:
        logger.exception("es__generate_facturae_xml failed")
        return err(str(exc))


async def es__sign_facturae_xades(
    xml: str,
    cert_path: str | None = None,
    signature_policy_id: str | None = None,
    signature_policy_hash: str | None = None,
    confirmation_token: str | None = None,
) -> dict[str, Any]:
    """Aplica una firma digital XAdES-EPES (ETSI EN 319 132-1) a un documento Facturae XML.

    Usa el certificado PKCS#12 indicado para firmar con SHA-256 + RSA. La
    política de firma por defecto es la de Facturae (Orden EHA/962/2007).

    HUMAN-IN-THE-LOOP: llame sin confirmation_token para recibir un resumen de
    confirmación y un token; muéstrelo al usuario y vuelva a llamar con
    confirmation_token para aplicar la firma real.

    Args:
        xml: XML Facturae sin firmar.
        cert_path: Ruta al certificado PKCS#12 (.p12 / .pfx). La contraseña se
            lee de AEAT_CERTIFICATE_PASSWORD (nunca como argumento de la tool).
        signature_policy_id: OID/URI de la política de firma. Por defecto:
            política Facturae (Orden EHA/962/2007).
        signature_policy_hash: SHA-256 base64 del documento de política de firma.
        confirmation_token: Token de la respuesta awaiting_confirmation previa.
    """
    try:
        if not xml:
            return err("xml is required", "MISSING_PARAM")

        assert_not_read_only("AEAT_READ_ONLY")
        gate = ConfirmationGate.get_default()
        if not gate.is_confirmed(confirmation_token):
            return ok(
                gate.pending_response(
                    action="es__sign_facturae_xades",
                    summary=(
                        "Apply XAdES-EPES signature to a Facturae XML document using the "
                        "FNMT-RCM PKCS#12 certificate. The signed XML will contain a "
                        "legally binding electronic signature."
                    ),
                    token=confirmation_token,
                )
            )

        policy_id: str = signature_policy_id or FACTURAE_POLICY_ID
        policy_hash: str | None = signature_policy_hash or FACTURAE_POLICY_HASH

        xml_bytes = xml.encode() if isinstance(xml, str) else xml

        if SignerClient.is_configured():
            signer_client = SignerClient.from_env()
            signed_bytes = await signer_client.sign(
                xml_bytes,
                signature_policy_id=policy_id,
                signature_policy_hash=policy_hash,
            )
            logger.info("Facturae XAdES-EPES signature applied via signer microservice")
        else:
            if not cert_path:
                return err(
                    "cert_path is required when signer microservice is not configured "
                    "(EINVOICING_SIGNER_SOCKET not set)",
                    "MISSING_PARAM",
                )
            config = XAdESSignerConfig(
                cert_path=cert_path,
                cert_password=aeat_settings.certificate_password,
                signature_policy_id=policy_id,
                signature_policy_hash=policy_hash,
            )
            signer = XAdESEPESSigner(config)
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
        gate.consume(confirmation_token)
        return ok(result)

    except ImportError as exc:
        return err(
            f"cryptography>=42.0.0 is required for XAdES signing: {exc}",
            "MISSING_DEPENDENCY",
        )
    except Exception as exc:
        logger.exception("es__sign_facturae_xades failed")
        return err(str(exc))


async def es__submit_to_face(
    xml: str,
    administrative_unit: str,
    accounting_office: str,
    management_body: str,
    confirmation_token: str | None = None,
) -> dict[str, Any]:
    """Envía un XML Facturae firmado con XAdES a FACe a través de la API REST B2B de FACe v2.

    FACe = Punto General de Entrada de Facturas Electrónicas. Autenticación JWS
    (RS256 + x5c) per FACe-manual-api-integradores.pdf s2.3: requiere FACE_ENV
    y AEAT_CERTIFICATE_PATH (+ AEAT_CERTIFICATE_PASSWORD).

    HUMAN-IN-THE-LOOP: llame sin confirmation_token para recibir un resumen de
    confirmación y un token; muéstrelo al usuario y vuelva a llamar con
    confirmation_token para ejecutar el envío real.

    Args:
        xml: XML Facturae con firma XAdES.
        administrative_unit: Código UnidadTramitadora de FACe.
        accounting_office: Código OficinasContables de FACe.
        management_body: Código OrganoGestor de FACe.
        confirmation_token: Token de la respuesta awaiting_confirmation previa.
    """
    try:
        for name, val in [
            ("xml", xml),
            ("administrative_unit", administrative_unit),
            ("accounting_office", accounting_office),
            ("management_body", management_body),
        ]:
            if not val:
                return err(f"{name} is required", "MISSING_PARAM")

        assert_not_read_only("AEAT_READ_ONLY")
        gate = ConfirmationGate.get_default()
        if not gate.is_confirmed(confirmation_token):
            env_label = face_env()
            return ok(
                gate.pending_response(
                    action="es__submit_to_face",
                    summary=(
                        f"Submit Facturae XML to FACe ({env_label}) for unit "
                        f"{administrative_unit!r} / office {accounting_office!r}. "
                        "This registers the invoice with the government B2B platform."
                    ),
                    token=confirmation_token,
                )
            )

        env = face_env()
        base_url = FACE_BASE_URLS[env]
        client = _build_face_client(base_url)

        xml_bytes = xml.encode() if isinstance(xml, str) else xml
        payload = {
            "unidadTramitadora": administrative_unit,
            "oficinasContables": accounting_office,
            "organoGestor": management_body,
        }
        response = await client._request(
            "POST",
            "/facturas",
            json=payload,
            files={"factura": ("factura.xml", xml_bytes, "application/xml")},
        )

        gate.consume(confirmation_token)
        result = _parse_face_response(response)
        result["environment"] = env
        return ok(result)

    except Exception as exc:
        logger.exception("es__submit_to_face failed")
        return err(str(exc))


async def es__get_face_invoice_status(invoice_id: str) -> dict[str, Any]:
    """Consulta el estado de tramitación de una factura en FACe.

    Códigos: 1200 Registrada, 2400 Reconocida, 3100 Rechazada, 4100 Pagada.

    Args:
        invoice_id: Número de registro FACe.
    """
    try:
        if not invoice_id:
            return err("invoice_id is required", "MISSING_PARAM")

        env = face_env()
        base_url = FACE_BASE_URLS[env]
        client = _build_face_client(base_url)

        response = await client._request("GET", f"/facturas/{invoice_id}")
        parsed = _parse_face_response(response)

        # Map known FACe tramitación status codes (the "codigo" field)
        status_codes = {
            "1200": "Registrada",
            "2400": "Reconocida por la unidad tramitadora",
            "3100": "Rechazada",
            "4100": "Pagada",
        }
        raw_status = str(parsed.get("codigo") or "")
        return ok(
            {
                "invoice_id": invoice_id,
                "status_code": raw_status,
                "status_description": status_codes.get(raw_status, "Desconocido"),
                "environment": env,
                "http_status_code": parsed["status_code"],
                "descripcion": parsed.get("descripcion"),
            }
        )

    except Exception as exc:
        logger.exception("es__get_face_invoice_status failed")
        return err(str(exc))


async def es__validate_facturae_schema(
    xml: str,
    schema_version: str = "3.2.2",
) -> dict[str, Any]:
    """Valida un XML Facturae contra el XSD oficial 3.2.2.

    Realiza validación estructural y, si el XSD está disponible en
    specs/facturae/, también validación de esquema completa.

    Args:
        xml: XML Facturae a validar.
        schema_version: Versión del esquema (por defecto: '3.2.2').
    """
    del schema_version  # reserved for future multi-version XSD selection
    try:
        if not xml:
            return err("xml is required", "MISSING_PARAM")

        xml_bytes = xml.encode() if isinstance(xml, str) else xml
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

        for tag in [
            "SchemaVersion",
            "Modality",
            "InvoiceIssuerType",
            "SellerParty",
            "BuyerParty",
            "InvoiceNumber",
            "IssueDate",
            "TaxesOutputs",
            "InvoiceTotals",
        ]:
            _req(tag)

        # XSD validation — Facturaev3_2_2.xml uses .xml extension intentionally
        # (the targetNamespace URI itself ends in Facturaev3_2_2.xml)
        import pathlib  # noqa: PLC0415

        xsd_path = (
            pathlib.Path(__file__).parent.parent.parent
            / "specs"
            / "facturae"
            / "xsd"
            / "Facturaev3_2_2.xml"
        )
        validation_mode = "structural"

        if xsd_path.exists():
            try:
                schema = etree.XMLSchema(etree.parse(str(xsd_path)))
                schema.validate(root)
                for e in schema.error_log:
                    errors.append(f"[XSD] {e.message} (línea {e.line})")
                validation_mode = "xsd"
            except Exception as exc:
                warnings.append(f"XSD validation failed to run: {exc}")
        else:
            warnings.append(
                "Validación XSD no disponible — specs/facturae/xsd/Facturaev3_2_2.xml "
                "no encontrado. La validación estructural está activa."
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
        logger.exception("es__validate_facturae_schema failed")
        return err(str(exc))
