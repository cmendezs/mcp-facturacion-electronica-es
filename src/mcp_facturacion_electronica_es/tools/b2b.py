"""MCP tools: Crea y Crece / B2B — factura B2B y comprobación de mandato.

Ley 18/2022 'Crea y Crece', developed by RD 238/2026 (BOE-A-2026-7295, published
2026-03-31, in force 2026-04-20):
    Mandates EN 16931-compliant e-invoicing for all B2B transactions.
    Admitted syntaxes (RD 238/2026 art. 7.1): CII, UBL (with B2B adaptations),
    EDIFACT invoice message, Facturae message. This package implements UBL and
    Facturae; CII and EDIFACT are legally admitted but have no emitter here.
    UBL is mandatory for the faithful-copy obligation to the public solution
    (art. 6.2) when a private platform is used to emit.
    Advanced electronic signature required (art. 7.3, per RD 1619/2012 art. 10.1.a).
    Unique invoice code required: issuer NIF + invoice number/series + issue date
    (art. 7.5) — exact insertion into the syntax is deferred to the OM below.
    Orden HAC/1028/2026 (BOE-A-2026-20587, published 2026-10-05, in force
    2026-10-06) regulates the public e-invoicing solution: EN 16931 in UBL
    (art. 3), faithful UBL copy with the "indicador de copia" (BT-ES-1,
    cbc:CopyIndicator, art. 4), unique code = issuer NIF + series/number + issue
    date (art. 6), no embedded files (arts. 3.6, 4.4), content in its Annex I.
    Effective-application dates (RD 238/2026 Disp. final cuarta) run 12/24 months
    from the order's entry into force. Still outstanding: the AEAT technical
    specifications and volumetry, which the order places on the AEAT electronic
    office (arts. 3.1, 4.2) and which this package has not seen.
    See the package's own compliance reference, "B2B mandate (Crea y Crece)".

Mutual exclusion (Royal Decree 254/2025):
    SII-enrolled taxpayers are exempt from VERI*FACTU.
    Always call es__check_b2b_mandate_applicability before generating records.

[NEED: AEAT electronic-office technical specifications (XSD, volumetry) for the public solution]
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

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

# RD 238/2026 Disp. final cuarta §1: turnover threshold (art. 121 Ley 37/1992) that
# determines the 12- vs 24-month post-OM timeline. Distinct from the €6M SII threshold
# in tools/utils.py — do not conflate the two.
_B2B_MANDATE_TURNOVER_THRESHOLD_EUR = 8_000_000

# Orden HAC/1028/2026 (BOE-A-2026-20587) — public e-invoicing solution. [Verified locally:
# BOE núm. 247, 2026-10-05; Disposición final única: in force the day after publication.]
_B2B_OM_REFERENCE = "Orden HAC/1028/2026 (BOE-A-2026-20587)"
_B2B_OM_PUBLICATION_DATE = date(2026, 10, 5)
_B2B_OM_ENTRY_INTO_FORCE = date(2026, 10, 6)


def _add_months(start: date, months: int) -> date:
    """Calendar-month offset (same day number; clamped to the month's last day)."""
    total = start.month - 1 + months
    year, month = start.year + total // 12, total % 12 + 1
    last_day = (date(year + (month == 12), month % 12 + 1, 1) - date(year, month, 1)).days
    return date(year, month, min(start.day, last_day))


# UBL namespaces. UBL 2.5 keeps the UBL 2.1 namespace URNs, so the Invoice-2 /
# CommonAggregateComponents-2 / CommonBasicComponents-2 URNs below are the ones
# the AEAT public solution (UBL 2.5, per its service catalogue) uses.
_UBL_INVOICE_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
_CAC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
_CBC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

# Annex I of the Orden HAC/1028/2026: BT-24 (Identificador de especificacion) and
# BT-23 (Tipo de proceso de negocio) each "adoptara el valor" below.
AEAT_CUSTOMIZATION_ID = "urn:cen.eu:en16931:2026#conformant#urn:aeat.es:spfe:1.0.0:extended"
AEAT_B2B_PROFILE_ID = "urn:aeat:names:specification:schema:profile:B2B"


# ---------------------------------------------------------------------------
# UBL EN 16931 builder for the AEAT public solution (Ley 18/2022, RD 238/2026)
# ---------------------------------------------------------------------------


def _sub(parent: etree._Element, ns: str, tag: str, text: str | None = None) -> etree._Element:
    child = etree.SubElement(parent, f"{{{ns}}}{tag}")
    if text is not None:
        child.text = text
    return child


def _amount(parent: etree._Element, tag: str, value: Decimal, currency: str) -> etree._Element:
    elem = _sub(parent, _CBC_NS, tag, fmt_amount(value))
    elem.set("currencyID", currency)
    return elem


def _vat_identifier(party: Any) -> str:
    """Return the NIF-IVA (BT-31 / BT-48) with the ISO 3166-1 country prefix."""
    country = party.tax_id.country_code.upper()
    ident = party.tax_id.identifier.upper()
    return ident if ident.startswith(country) else f"{country}{ident}"


def _build_party(parent: etree._Element, party: Any) -> None:
    """Append a cac:Party following Annex I (BG-4 to BG-6 and BG-7 to BG-9).

    A Spanish party is identified by its NIF (BT-32 / BT-47: ``CompanyID`` with
    ``schemeID="FC"`` under tax scheme ``LOC``); any other party by its NIF-IVA under
    tax scheme ``VAT``. BT-30 / BT-46 (legal registration identifier) repeats the NIF,
    because Annex I makes it mandatory whenever BT-32 / BT-47 is present.
    """
    party_elem = _sub(parent, _CAC_NS, "Party")
    address = party.address
    if address is not None:  # BG-5 / BG-8 (BR-ES-8, BR-ES-10: street and country mandatory)
        postal = _sub(party_elem, _CAC_NS, "PostalAddress")
        _sub(postal, _CBC_NS, "StreetName", address.street[:200])
        _sub(postal, _CBC_NS, "CityName", address.city[:100])
        _sub(postal, _CBC_NS, "PostalZone", address.postal_code[:20])
        if address.province:
            _sub(postal, _CBC_NS, "CountrySubentity", address.province[:100])
        country = _sub(postal, _CAC_NS, "Country")
        _sub(country, _CBC_NS, "IdentificationCode", address.country_code.upper())

    scheme = _sub(party_elem, _CAC_NS, "PartyTaxScheme")
    if party.tax_id.country_code.upper() == "ES":
        company = _sub(scheme, _CBC_NS, "CompanyID", party.tax_id.identifier)
        company.set("schemeID", "FC")
        _sub(_sub(scheme, _CAC_NS, "TaxScheme"), _CBC_NS, "ID", "LOC")
    else:
        _sub(scheme, _CBC_NS, "CompanyID", _vat_identifier(party))
        _sub(_sub(scheme, _CAC_NS, "TaxScheme"), _CBC_NS, "ID", "VAT")

    legal = _sub(party_elem, _CAC_NS, "PartyLegalEntity")
    _sub(legal, _CBC_NS, "RegistrationName", party.display_name[:200])
    _sub(legal, _CBC_NS, "CompanyID", party.tax_id.identifier)


def build_ubl_invoice(invoice: InvoiceDocument, *, is_copy: bool = False) -> bytes:
    """Build a UBL Invoice for the AEAT public e-invoicing solution.

    The structure follows Annex I of the Orden HAC/1028/2026 (BT-23 and BT-24 values,
    the Spanish party identification, mandatory postal addresses) and is validated in
    the test suite against the OASIS UBL 2.5 ``UBL-Invoice-2.5.xsd``. The Annex I
    Spanish extensions not listed in the supported fields below are not emitted.

    Supported Annex I terms: BT-1, BT-ES-1, BT-2, BT-3 (380 only), BT-5, BT-9, BG-1
    (one free-text note), BG-2 (BT-23, BT-24), BG-4 to BG-9, BG-16, BG-22, BG-23,
    BG-25.

    Args:
        invoice: Core InvoiceDocument.
        is_copy: BT-ES-1. ``True`` marks the document as a faithful copy
            (``cbc:CopyIndicator`` true); the default marks an original.

    Returns:
        UTF-8 UBL XML bytes.
    """
    currency = invoice.currency.upper()
    nsmap = {"in": _UBL_INVOICE_NS, "cac": _CAC_NS, "cbc": _CBC_NS}
    root = etree.Element(f"{{{_UBL_INVOICE_NS}}}Invoice", nsmap=nsmap)

    _sub(root, _CBC_NS, "CustomizationID", AEAT_CUSTOMIZATION_ID)  # BT-24
    _sub(root, _CBC_NS, "ProfileID", AEAT_B2B_PROFILE_ID)  # BT-23
    _sub(root, _CBC_NS, "ID", invoice.number)  # BT-1
    _sub(root, _CBC_NS, "CopyIndicator", "true" if is_copy else "false")  # BT-ES-1
    _sub(root, _CBC_NS, "IssueDate", invoice.date)  # BT-2
    if invoice.payment and invoice.payment.due_date:
        _sub(root, _CBC_NS, "DueDate", invoice.payment.due_date)  # BT-9
    _sub(root, _CBC_NS, "InvoiceTypeCode", "380")  # BT-3: 380 = commercial invoice
    if invoice.note:
        _sub(root, _CBC_NS, "Note", invoice.note[:500])  # BG-1 (BT-22)
    _sub(root, _CBC_NS, "DocumentCurrencyCode", currency)  # BT-5

    _build_party(_sub(root, _CAC_NS, "AccountingSupplierParty"), invoice.seller)
    _build_party(_sub(root, _CAC_NS, "AccountingCustomerParty"), invoice.buyer)

    if invoice.payment:  # BG-16
        pm = _sub(root, _CAC_NS, "PaymentMeans")
        _sub(pm, _CBC_NS, "PaymentMeansCode", invoice.payment.payment_method_code or "30")
        if invoice.payment.iban:
            pfa = _sub(pm, _CAC_NS, "PayeeFinancialAccount")
            account = _sub(pfa, _CBC_NS, "ID", invoice.payment.iban)
            account.set("schemeID", "IBAN")

    tax_base_total = sum((v.taxable_base for v in invoice.vat_summary), Decimal("0"))
    tax_amount_total = sum((v.vat_amount for v in invoice.vat_summary), Decimal("0"))
    grand_total = tax_base_total + tax_amount_total

    tt = _sub(root, _CAC_NS, "TaxTotal")  # BG-22 / BG-23
    _amount(tt, "TaxAmount", tax_amount_total, currency)
    for vat in invoice.vat_summary:
        subtotal = _sub(tt, _CAC_NS, "TaxSubtotal")
        _amount(subtotal, "TaxableAmount", vat.taxable_base, currency)
        _amount(subtotal, "TaxAmount", vat.vat_amount, currency)
        category = _sub(subtotal, _CAC_NS, "TaxCategory")
        _sub(category, _CBC_NS, "ID", "S")
        _sub(category, _CBC_NS, "Percent", fmt_amount(vat.vat_rate))
        _sub(_sub(category, _CAC_NS, "TaxScheme"), _CBC_NS, "ID", "VAT")

    lmt = _sub(root, _CAC_NS, "LegalMonetaryTotal")
    _amount(lmt, "LineExtensionAmount", tax_base_total, currency)
    _amount(lmt, "TaxExclusiveAmount", tax_base_total, currency)
    _amount(lmt, "TaxInclusiveAmount", grand_total, currency)
    _amount(lmt, "PayableAmount", grand_total, currency)

    for i, line in enumerate(invoice.lines, start=1):  # BG-25
        il = _sub(root, _CAC_NS, "InvoiceLine")
        _sub(il, _CBC_NS, "ID", str(i))
        quantity = _sub(il, _CBC_NS, "InvoicedQuantity", fmt_amount(line.quantity or Decimal("1")))
        quantity.set("unitCode", line.unit_of_measure or "EA")
        _amount(il, "LineExtensionAmount", line.total_price, currency)
        item = _sub(il, _CAC_NS, "Item")
        _sub(item, _CBC_NS, "Description", line.description[:500])
        _sub(item, _CBC_NS, "Name", line.description[:100])
        category = _sub(item, _CAC_NS, "ClassifiedTaxCategory")
        _sub(category, _CBC_NS, "ID", "S")
        _sub(category, _CBC_NS, "Percent", fmt_amount(line.vat_rate))
        _sub(_sub(category, _CAC_NS, "TaxScheme"), _CBC_NS, "ID", "VAT")
        _amount(_sub(il, _CAC_NS, "Price"), "PriceAmount", line.unit_price, currency)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def es__generate_b2b_einvoice_es(
    invoice: dict[str, Any],
    format: str = "ubl",  # noqa: A002
    is_copy: bool = False,
) -> dict[str, Any]:
    """Genera una factura B2B conforme a EN 16931 en formato UBL o Facturae 3.2.2.

    Según la Ley 18/2022 'Crea y Crece'. El formato UBL sigue el anexo I de la Orden
    HAC/1028/2026 (identificador de especificación y tipo de proceso de la solución
    pública de la AEAT, identificación fiscal del vendedor y del comprador, dirección
    postal obligatoria) y se valida contra el esquema OASIS UBL 2.5.

    Args:
        invoice: Datos de la factura.
        format: Formato de salida: 'ubl' (por defecto) o 'facturae'.
        is_copy: Solo UBL. BT-ES-1: true marca el documento como copia fiel; por
            defecto es un original.
    """
    try:
        try:
            fmt = B2BFormat(format)
        except ValueError:
            return err(f"Invalid format: {format!r}. Must be 'ubl' or 'facturae'.")

        parsed_invoice = parse_invoice(invoice)

        if fmt == B2BFormat.ubl:
            xml_bytes = build_ubl_invoice(parsed_invoice, is_copy=bool(is_copy))
            schema_desc = "UBL 2.5 (EN 16931, AEAT public solution, Orden HAC/1028/2026 Annex I)"
        else:
            xml_bytes = build_facturae_xml(parsed_invoice)
            schema_desc = "Facturae 3.2.2 (EN 16931)"

        logger.info("B2B e-invoice generated for %s (format=%s)", parsed_invoice.number, fmt.value)

        return ok(
            {
                "xml": xml_bytes.decode("utf-8"),
                "format": fmt.value,
                "schema": schema_desc,
                "invoice_number": parsed_invoice.number,
                "disclaimer": (
                    "RD 238/2026 publicado; formatos confirmados (EN 16931: CII/UBL/EDIFACT/"
                    "Facturae). Orden HAC/1028/2026 (BOE-A-2026-20587) regula la solución "
                    "pública: EN 16931 en sintaxis UBL, código único (NIF emisor + serie/número "
                    "+ fecha) y contenido mínimo en su anexo I. El generador UBL cubre un "
                    "subconjunto del anexo I (factura ordinaria tipo 380, un tipo de IVA 'S' "
                    "por línea, sin los grupos específicos BG-ES) y no ejecuta las reglas "
                    "Schematron EN 16931:2026 de la AEAT, no publicadas [Unverified]. La copia "
                    "fiel remitida a la solución pública será UBL (art. 6.2 RD 238/2026; "
                    "art. 4 de la Orden)."
                ),
            }
        )

    except EInvoicingError as exc:
        return err(str(exc))
    except Exception as exc:
        logger.exception("es__generate_b2b_einvoice_es failed")
        return err(str(exc))


async def es__check_b2b_mandate_applicability(
    annual_turnover_eur: float,
    tax_address_province_code: str,
    enrolled_in_sii: bool = False,
    entity_type: str = "IS",
) -> dict[str, Any]:
    """Determina el régimen de facturación electrónica aplicable.

    VERI*FACTU o SII, a partir del volumen de operaciones, código de provincia
    y enrolamiento en SII. Las provincias forales (TicketBAI, NaTicket) se
    señalan como fuera de alcance. Aplica la lógica de exclusión
    mutua del Real Decreto 254/2025.

    Args:
        annual_turnover_eur: Volumen anual de operaciones IVA en EUR.
        tax_address_province_code: Código de provincia INE de dos dígitos.
        enrolled_in_sii: Inscripción en el SII (por defecto: false).
        entity_type: Tipo de obligado: 'IS' (Sociedades) o 'IRPF'.
    """
    try:
        turnover = annual_turnover_eur
        province_code = str(tax_address_province_code).strip()
        enrolled = bool(enrolled_in_sii)

        if turnover is None:
            return err("annual_turnover_eur is required", "MISSING_PARAM")
        if not province_code:
            return err("tax_address_province_code is required", "MISSING_PARAM")

        try:
            entity_type_enum = EntityType(entity_type)
        except ValueError:
            return err(f"Invalid entity_type: {entity_type!r}. Must be 'IS' or 'IRPF'.")

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
            deadline = "enero 2027" if entity_type_enum == EntityType.IS else "julio 2027"
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

        # Crea y Crece — RD 238/2026 (BOE-A-2026-7295) plus Orden HAC/1028/2026
        # (BOE-A-2026-20587), in force 2026-10-06, which starts the application clocks.
        applicable_systems.append(
            "B2B Crea y Crece (Ley 18/2022 + RD 238/2026 + Orden HAC/1028/2026; "
            "especificaciones técnicas de la AEAT pendientes)"
        )

        turnover_exceeds_8m = float(turnover) > _B2B_MANDATE_TURNOVER_THRESHOLD_EUR
        b2b_months_after_om = 12 if turnover_exceeds_8m else 24
        om_in_force = _B2B_OM_ENTRY_INTO_FORCE
        over_8m_date = _add_months(om_in_force, 12)
        other_date = _add_months(om_in_force, 24)

        return ok(
            {
                "annual_turnover_eur": float(turnover),
                "province_code": province_code,
                "entity_type": entity_type_enum.value,
                "enrolled_in_sii": enrolled,
                "primary_regime": regime.value,
                "applicable_systems": applicable_systems,
                "notes": notes,
                "sii_exclusion_applies": regime == SpanishRegime.VERIFACTU_SII,
                "b2b_syntaxes_confirmed": ["CII", "UBL", "EDIFACT", "Facturae"],
                "b2b_syntaxes_implemented": ["UBL", "Facturae"],
                "b2b_public_solution_pending": True,
                "b2b_public_solution_order": _B2B_OM_REFERENCE,
                "b2b_aeat_technical_specs_pending": True,
                "b2b_format_note": (
                    "Sintaxis admitidas confirmadas por RD 238/2026 art. 7.1 (EN 16931: "
                    "CII/UBL/EDIFACT/Facturae); este paquete implementa UBL y Facturae. "
                    "UBL es obligatorio para la copia fiel a la solución pública cuando se "
                    "emite por plataforma privada (art. 6.2). Firma electrónica avanzada "
                    "requerida (art. 7.3). Código único de factura: concatenación de NIF "
                    "emisor + serie/número + fecha de expedición (art. 7.5 RD 238/2026; "
                    "art. 6 Orden HAC/1028/2026, contenido en su anexo I). Las facturas y "
                    "copias fieles para la solución pública no pueden incorporar ficheros "
                    "embebidos (arts. 3.6 y 4.4) y la copia fiel se marca con el indicador "
                    "de copia (BT-ES-1). La codificación exacta en la sintaxis UBL depende de "
                    "las especificaciones técnicas de la AEAT "
                    "[NEED: AEAT electronic-office specifications, not yet supplied]."
                ),
                "b2b_mandate_timeline": {
                    "basis": "RD 238/2026 Disp. final cuarta — offsets run from the entry "
                    "into force of Orden HAC/1028/2026 (published 2026-10-05, in force "
                    "2026-10-06 per its Disp. final única).",
                    "om_reference": _B2B_OM_REFERENCE,
                    "om_publication_date": _B2B_OM_PUBLICATION_DATE.isoformat(),
                    "om_entry_into_force_date": om_in_force.isoformat(),
                    "this_taxpayer_application_date": (
                        over_8m_date if turnover_exceeds_8m else other_date
                    ).isoformat(),
                    "over_8m_application_date": over_8m_date.isoformat(),
                    "other_taxpayers_application_date": other_date.isoformat(),
                    "platform_operator_application_date": over_8m_date.isoformat(),
                    "turnover_threshold_eur": _B2B_MANDATE_TURNOVER_THRESHOLD_EUR,
                    "this_taxpayer_months_after_om": b2b_months_after_om,
                    "over_8m_turnover_months_after_om": 12,
                    "other_taxpayers_months_after_om": 24,
                    "platform_operator_obligations_months_after_om": 12,
                    "note": (
                        "8M€ threshold (art. 121 Ley 37/1992) is distinct from the €6M SII "
                        "threshold above — do not conflate. Application dates are the "
                        "entry-into-force date plus the calendar-month offset "
                        "[Inference: whether the obligation applies on that day or the day "
                        "after is not stated in the supplied texts]. Over-8M taxpayers must "
                        "also attach a readable PDF for 12 months after their effective date "
                        "unless the recipient accepts the original format (RD 238/2026 "
                        "Disp. transitoria segunda); the PDF is not sent to the public "
                        "solution."
                    ),
                },
                "disclaimer": (
                    "Según RD-ley 15/2025, RD 254/2025 y RD 238/2026. "
                    "Sujeto a cambios por legislación posterior, en particular las "
                    "especificaciones técnicas de la AEAT para la solución pública. "
                    "No constituye asesoramiento jurídico ni fiscal."
                ),
            }
        )

    except Exception as exc:
        logger.exception("es__check_b2b_mandate_applicability failed")
        return err(str(exc))
