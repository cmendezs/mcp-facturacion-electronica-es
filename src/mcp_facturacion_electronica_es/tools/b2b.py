"""MCP tools: Crea y Crece / B2B — factura B2B y comprobación de mandato.

Ley 18/2022 'Crea y Crece':
    Mandates EN 16931-compliant e-invoicing for all B2B transactions.
    Format: UBL 2.1 or Facturae 3.2.2.
    Implementing decree: PENDING as of May 2026.

Mutual exclusion (Royal Decree 254/2025):
    SII-enrolled taxpayers are exempt from VERI*FACTU.
    Always call es__check_b2b_mandate_applicability before generating records.

[NEED: confirm format requirements once implementing decree is published]
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import mcp.types as types
from lxml import etree
from mcp_einvoicing_core.exceptions import EInvoicingError
from mcp_einvoicing_core.models import InvoiceDocument

from mcp_facturacion_electronica_es._helpers import err, fmt_amount, ok, parse_invoice
from mcp_facturacion_electronica_es.models.es import B2BFormat, EntityType, SpanishRegime
from mcp_facturacion_electronica_es.tools.facturae import build_facturae_xml
from mcp_facturacion_electronica_es.tools.utils import (
    _SII_TURNOVER_THRESHOLD_EUR,
    _detect_regime,
)

logger = logging.getLogger(__name__)

# UBL 2.1 namespaces
_UBL_INVOICE_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
_CAC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
_CBC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"


# ---------------------------------------------------------------------------
# UBL 2.1 EN 16931 builder (minimal, Ley 18/2022)
# ---------------------------------------------------------------------------


def _sub(parent: etree._Element, ns: str, tag: str, text: str | None = None) -> etree._Element:
    child = etree.SubElement(parent, f"{{{ns}}}{tag}")
    if text is not None:
        child.text = text
    return child


def build_ubl_invoice(invoice: InvoiceDocument) -> bytes:
    """Build an EN 16931-compliant UBL 2.1 Invoice from a core InvoiceDocument.

    Args:
        invoice: Core InvoiceDocument.

    Returns:
        UTF-8 UBL 2.1 XML bytes.
    """
    nsmap = {
        None: _UBL_INVOICE_NS,
        "cac": _CAC_NS,
        "cbc": _CBC_NS,
    }
    root = etree.Element(f"{{{_UBL_INVOICE_NS}}}Invoice", nsmap=nsmap)

    _sub(root, _CBC_NS, "CustomizationID",
         "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0")
    _sub(root, _CBC_NS, "ProfileID", "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0")
    _sub(root, _CBC_NS, "ID", invoice.number)
    _sub(root, _CBC_NS, "IssueDate", invoice.date)
    _sub(root, _CBC_NS, "InvoiceTypeCode", "380")  # 380 = commercial invoice
    _sub(root, _CBC_NS, "DocumentCurrencyCode", invoice.currency.upper())

    if invoice.note:
        _sub(root, _CBC_NS, "Note", invoice.note[:500])

    # AccountingSupplierParty (seller)
    asp = _sub(root, _CAC_NS, "AccountingSupplierParty")
    party_s = _sub(asp, _CAC_NS, "Party")
    ep_s = _sub(party_s, _CAC_NS, "EndpointID")
    ep_s.set("schemeID", "0088")
    ep_s.text = invoice.seller.tax_id.identifier
    pid_s = _sub(party_s, _CAC_NS, "PartyIdentification")
    pid_id_s = _sub(pid_s, _CBC_NS, "ID")
    pid_id_s.set("schemeID", "0002")
    pid_id_s.text = invoice.seller.tax_id.identifier
    pn_s = _sub(party_s, _CAC_NS, "PartyName")
    _sub(pn_s, _CBC_NS, "Name", invoice.seller.display_name[:100])
    ptv_s = _sub(party_s, _CAC_NS, "PartyTaxScheme")
    _sub(ptv_s, _CBC_NS, "CompanyID", invoice.seller.tax_id.identifier)
    ts_s = _sub(ptv_s, _CAC_NS, "TaxScheme")
    _sub(ts_s, _CBC_NS, "ID", "VAT")
    pli_s = _sub(party_s, _CAC_NS, "PartyLegalEntity")
    _sub(pli_s, _CBC_NS, "RegistrationName", invoice.seller.display_name[:100])
    _sub(pli_s, _CBC_NS, "CompanyID", invoice.seller.tax_id.identifier)

    # AccountingCustomerParty (buyer)
    acp = _sub(root, _CAC_NS, "AccountingCustomerParty")
    party_b = _sub(acp, _CAC_NS, "Party")
    ep_b = _sub(party_b, _CAC_NS, "EndpointID")
    ep_b.set("schemeID", "0088")
    ep_b.text = invoice.buyer.tax_id.identifier
    pn_b = _sub(party_b, _CAC_NS, "PartyName")
    _sub(pn_b, _CBC_NS, "Name", invoice.buyer.display_name[:100])
    ptv_b = _sub(party_b, _CAC_NS, "PartyTaxScheme")
    _sub(ptv_b, _CBC_NS, "CompanyID", invoice.buyer.tax_id.identifier)
    ts_b = _sub(ptv_b, _CAC_NS, "TaxScheme")
    _sub(ts_b, _CBC_NS, "ID", "VAT")
    pli_b = _sub(party_b, _CAC_NS, "PartyLegalEntity")
    _sub(pli_b, _CBC_NS, "RegistrationName", invoice.buyer.display_name[:100])
    _sub(pli_b, _CBC_NS, "CompanyID", invoice.buyer.tax_id.identifier)

    # Payment means (if payment provided)
    if invoice.payment:
        pm = _sub(root, _CAC_NS, "PaymentMeans")
        _sub(pm, _CBC_NS, "PaymentMeansCode", invoice.payment.payment_method_code or "30")
        if invoice.payment.due_date:
            _sub(pm, _CBC_NS, "PaymentDueDate", invoice.payment.due_date)
        if invoice.payment.iban:
            pfa = _sub(pm, _CAC_NS, "PayeeFinancialAccount")
            _sub(pfa, _CBC_NS, "ID", invoice.payment.iban)

    # TaxTotal
    tax_base_total = sum((v.taxable_base for v in invoice.vat_summary), Decimal("0"))
    tax_amount_total = sum((v.vat_amount for v in invoice.vat_summary), Decimal("0"))
    grand_total = tax_base_total + tax_amount_total

    tt = _sub(root, _CAC_NS, "TaxTotal")
    tta = _sub(tt, _CBC_NS, "TaxAmount", fmt_amount(tax_amount_total))
    tta.set("currencyID", invoice.currency.upper())
    for vat in invoice.vat_summary:
        ts_elem = _sub(tt, _CAC_NS, "TaxSubtotal")
        tsb = _sub(ts_elem, _CBC_NS, "TaxableAmount", fmt_amount(vat.taxable_base))
        tsb.set("currencyID", invoice.currency.upper())
        tsa = _sub(ts_elem, _CBC_NS, "TaxAmount", fmt_amount(vat.vat_amount))
        tsa.set("currencyID", invoice.currency.upper())
        tc = _sub(ts_elem, _CAC_NS, "TaxCategory")
        _sub(tc, _CBC_NS, "ID", "S")
        _sub(tc, _CBC_NS, "Percent", fmt_amount(vat.vat_rate))
        tsch = _sub(tc, _CAC_NS, "TaxScheme")
        _sub(tsch, _CBC_NS, "ID", "VAT")

    # LegalMonetaryTotal
    lmt = _sub(root, _CAC_NS, "LegalMonetaryTotal")
    lab = _sub(lmt, _CBC_NS, "LineExtensionAmount", fmt_amount(tax_base_total))
    lab.set("currencyID", invoice.currency.upper())
    teb = _sub(lmt, _CBC_NS, "TaxExclusiveAmount", fmt_amount(tax_base_total))
    teb.set("currencyID", invoice.currency.upper())
    tib = _sub(lmt, _CBC_NS, "TaxInclusiveAmount", fmt_amount(grand_total))
    tib.set("currencyID", invoice.currency.upper())
    pab = _sub(lmt, _CBC_NS, "PayableAmount", fmt_amount(grand_total))
    pab.set("currencyID", invoice.currency.upper())

    # InvoiceLine
    for i, line in enumerate(invoice.lines, start=1):
        il = _sub(root, _CAC_NS, "InvoiceLine")
        _sub(il, _CBC_NS, "ID", str(i))
        ilq = _sub(il, _CBC_NS, "InvoicedQuantity", fmt_amount(line.quantity or Decimal("1")))
        ilq.set("unitCode", line.unit_of_measure or "EA")
        ila = _sub(il, _CBC_NS, "LineExtensionAmount", fmt_amount(line.total_price))
        ila.set("currencyID", invoice.currency.upper())
        item = _sub(il, _CAC_NS, "Item")
        _sub(item, _CBC_NS, "Description", line.description[:500])
        itc = _sub(item, _CAC_NS, "ClassifiedTaxCategory")
        _sub(itc, _CBC_NS, "ID", "S")
        _sub(itc, _CBC_NS, "Percent", fmt_amount(line.vat_rate))
        isc = _sub(itc, _CAC_NS, "TaxScheme")
        _sub(isc, _CBC_NS, "ID", "VAT")
        pp = _sub(il, _CAC_NS, "Price")
        ppa = _sub(pp, _CBC_NS, "PriceAmount", fmt_amount(line.unit_price))
        ppa.set("currencyID", invoice.currency.upper())

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOL_ES_GENERATE_B2B_EINVOICE_ES = types.Tool(
    name="es__generate_b2b_einvoice_es",
    description=(
        "Genera una factura B2B conforme a EN 16931 en formato UBL 2.1 o Facturae 3.2.2 "
        "según la Ley 18/2022 'Crea y Crece'. "
        "El reglamento de desarrollo está pendiente de publicación."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "invoice": {"type": "object", "description": "Datos de la factura."},
            "format": {
                "type": "string",
                "enum": ["ubl", "facturae"],
                "description": "Formato de salida: 'ubl' (por defecto) o 'facturae'.",
                "default": "ubl",
            },
        },
        "required": ["invoice"],
    },
)

TOOL_ES_CHECK_B2B_MANDATE_APPLICABILITY = types.Tool(
    name="es__check_b2b_mandate_applicability",
    description=(
        "Determina el régimen de facturación electrónica aplicable (VERI*FACTU, SII, TicketBAI, "
        "NaTicket) a partir del volumen de operaciones, código de provincia y enrolamiento en SII. "
        "Aplica la lógica de exclusión mutua del Real Decreto 254/2025."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "annual_turnover_eur": {
                "type": "number",
                "description": "Volumen anual de operaciones IVA en EUR.",
            },
            "tax_address_province_code": {
                "type": "string",
                "description": "Código de provincia INE de dos dígitos.",
            },
            "enrolled_in_sii": {
                "type": "boolean",
                "description": "Inscripción en el SII (por defecto: false).",
                "default": False,
            },
            "entity_type": {
                "type": "string",
                "enum": ["IS", "IRPF"],
                "description": "Tipo de obligado: 'IS' (Sociedades) o 'IRPF'.",
            },
        },
        "required": ["annual_turnover_eur", "tax_address_province_code"],
    },
)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def handle_es_generate_b2b_einvoice_es(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        invoice_data = arguments.get("invoice")
        if not invoice_data:
            return err("invoice is required", "MISSING_PARAM")

        format_str = arguments.get("format", "ubl")
        try:
            fmt = B2BFormat(format_str)
        except ValueError:
            return err(f"Invalid format: {format_str!r}. Must be 'ubl' or 'facturae'.")

        invoice = parse_invoice(invoice_data)

        if fmt == B2BFormat.ubl:
            xml_bytes = build_ubl_invoice(invoice)
            schema_desc = "UBL 2.1 (EN 16931)"
        else:
            xml_bytes = build_facturae_xml(invoice)
            schema_desc = "Facturae 3.2.2 (EN 16931)"

        logger.info(
            "B2B e-invoice generated for %s (format=%s)", invoice.number, fmt.value
        )

        return ok({
            "xml": xml_bytes.decode("utf-8"),
            "format": fmt.value,
            "schema": schema_desc,
            "invoice_number": invoice.number,
            "disclaimer": (
                "El reglamento de desarrollo de la Ley 18/2022 (Crea y Crece) está pendiente "
                "de publicación. El formato definitivo puede variar."
            ),
        })

    except EInvoicingError as exc:
        return err(str(exc))
    except Exception as exc:
        logger.exception("es__generate_b2b_einvoice_es failed")
        return err(str(exc))


async def handle_es_check_b2b_mandate_applicability(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        turnover = arguments.get("annual_turnover_eur")
        province_code = str(arguments.get("tax_address_province_code", "")).strip()
        enrolled = bool(arguments.get("enrolled_in_sii", False))
        entity_type_str = arguments.get("entity_type", "IS")

        if turnover is None:
            return err("annual_turnover_eur is required", "MISSING_PARAM")
        if not province_code:
            return err("tax_address_province_code is required", "MISSING_PARAM")

        try:
            entity_type = EntityType(entity_type_str)
        except ValueError:
            return err(f"Invalid entity_type: {entity_type_str!r}. Must be 'IS' or 'IRPF'.")

        regime = _detect_regime(province_code, enrolled, annual_turnover_eur=float(turnover))

        notes: list[str] = []
        applicable_systems: list[str] = []

        # Check for out-of-scope foral territories before regime branching
        from mcp_facturacion_electronica_es.tools.utils import (
            _is_out_of_scope_territory,  # noqa: PLC0415
        )
        out_of_scope = _is_out_of_scope_territory(province_code)
        if out_of_scope:
            applicable_systems = ["Foral (out of scope)"]
            notes.append(out_of_scope)

        if regime == SpanishRegime.VERIFACTU_SII:
            applicable_systems = ["SII"]
            notes.append(
                "Inscrito en SII: exento de VERI*FACTU (Real Decreto 254/2025). "
                "Obligación de comunicación de facturas en 4 días hábiles."
            )
            if float(turnover) > _SII_TURNOVER_THRESHOLD_EUR:
                notes.append(
                    f"Facturación ({float(turnover):,.2f} EUR) supera el umbral SII (€6M)."
                )
        else:
            # VERIFACTU
            applicable_systems = ["VERI*FACTU"]
            deadline = "enero 2027" if entity_type == EntityType.IS else "julio 2027"
            notes.append(
                f"VERI*FACTU obligatorio desde {deadline} (RD-ley 15/2025). "
                "Obligatorio también Facturae/FACe para facturas B2G."
            )
            if float(turnover) > _SII_TURNOVER_THRESHOLD_EUR:
                notes.append(
                    f"Facturación ({float(turnover):,.2f} EUR) supera el umbral SII (€6M). "
                    "Puede estar obligado a inscribirse en el SII, lo cual excluye VERI*FACTU."
                )

        # Facturae/FACe always applies for B2G
        applicable_systems.append("Facturae / FACe (obligatorio para facturas B2G desde 2015)")

        # Crea y Crece (pending)
        applicable_systems.append("B2B Crea y Crece (Ley 18/2022, reglamento pendiente)")

        return ok({
            "annual_turnover_eur": float(turnover),
            "province_code": province_code,
            "entity_type": entity_type.value,
            "enrolled_in_sii": enrolled,
            "primary_regime": regime.value,
            "applicable_systems": applicable_systems,
            "notes": notes,
            "sii_exclusion_applies": regime == SpanishRegime.VERIFACTU_SII,
            "disclaimer": (
                "Según RD-ley 15/2025 y RD 254/2025. "
                "Sujeto a cambios por legislación posterior. "
                "No constituye asesoramiento jurídico ni fiscal."
            ),
        })

    except Exception as exc:
        logger.exception("es__check_b2b_mandate_applicability failed")
        return err(str(exc))
