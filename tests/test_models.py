"""Tests for ES models: SpanishInvoice, enums, audit CHECK 3 coverage."""

from __future__ import annotations

from decimal import Decimal

import pytest
from mcp_einvoicing_core.models import (
    InvoiceParty,
    PartyAddress,
    TaxIdentifier,
)

from mcp_facturacion_electronica_es.models.es import (
    AEATResponseType,
    B2BFormat,
    EntityType,
    SIICommunicationType,
    SpanishInvoice,
    SpanishRegime,
    VerifactuInvoiceType,
)

# ---------------------------------------------------------------------------
# Enum smoke tests
# ---------------------------------------------------------------------------


def test_spanish_regime_values() -> None:
    assert SpanishRegime.VERIFACTU == "VERIFACTU"
    assert SpanishRegime.VERIFACTU_SII == "VERIFACTU+SII"
    # TicketBAI (Pais Vasco) is out of scope — not in SpanishRegime


def test_verifactu_invoice_type_values() -> None:
    for code in ["F1", "F2", "F3", "R1", "R2", "R3", "R4", "R5"]:
        assert VerifactuInvoiceType(code) == code


def test_sii_comm_type() -> None:
    assert SIICommunicationType.A0 == "A0"
    assert SIICommunicationType.A1 == "A1"
    assert SIICommunicationType.A4 == "A4"


def test_entity_type() -> None:
    assert EntityType.IS == "IS"
    assert EntityType.IRPF == "IRPF"


def test_b2b_format() -> None:
    assert B2BFormat.ubl == "ubl"
    assert B2BFormat.facturae == "facturae"


def test_aeat_response_type() -> None:
    assert AEATResponseType.verifactu == "verifactu"
    assert AEATResponseType.sii == "sii"


# ---------------------------------------------------------------------------
# SpanishInvoice — EN 16931 mandatory field coverage (audit CHECK 3 proxy)
# ---------------------------------------------------------------------------


@pytest.fixture()
def spanish_invoice(minimal_invoice) -> SpanishInvoice:
    return SpanishInvoice.model_validate(minimal_invoice.model_dump())


def test_spanish_invoice_mandatory_properties(spanish_invoice: SpanishInvoice) -> None:
    """All EN 16931 fields must be accessible (audit CHECK 3 verifies these)."""
    assert spanish_invoice.invoice_number == "2025-0001"
    assert spanish_invoice.invoice_date == "2025-03-15"
    assert spanish_invoice.invoice_type_code == "F1"
    assert spanish_invoice.currency_code == "EUR"
    assert spanish_invoice.seller is not None
    assert spanish_invoice.buyer is not None
    assert len(spanish_invoice.tax_lines) == 1


def test_spanish_invoice_computed_totals(spanish_invoice: SpanishInvoice) -> None:
    assert spanish_invoice.tax_exclusive_amount == Decimal("1000.00")
    assert spanish_invoice.tax_total == Decimal("210.00")
    assert spanish_invoice.tax_inclusive_amount == Decimal("1210.00")
    assert spanish_invoice.amount_due == Decimal("1210.00")


def test_spanish_invoice_es_specific_fields(spanish_invoice: SpanishInvoice) -> None:
    """ES-specific optional fields default to None."""
    assert spanish_invoice.regime is None
    assert spanish_invoice.verifactu_type is None
    assert spanish_invoice.software_id is None
    assert spanish_invoice.software_nif is None


def test_spanish_invoice_with_regime(minimal_invoice) -> None:
    invoice = SpanishInvoice.model_validate(
        {
            **minimal_invoice.model_dump(),
            "regime": SpanishRegime.VERIFACTU,
            "verifactu_type": VerifactuInvoiceType.F1,
            "software_id": "SW-001",
            "software_nif": "B87654321",
        }
    )
    assert invoice.regime == SpanishRegime.VERIFACTU
    assert invoice.verifactu_type == VerifactuInvoiceType.F1


# ---------------------------------------------------------------------------
# NIF / NIE / CIF validation (Batch 1 — ES-TL-1)
# ---------------------------------------------------------------------------


def _make_party(nif: str, name: str = "Test Entity") -> InvoiceParty:
    return InvoiceParty(
        tax_id=TaxIdentifier(country_code="ES", identifier=nif),
        name=name,
        address=PartyAddress(
            street="Calle Mayor 1",
            postal_code="28001",
            city="Madrid",
            country_code="ES",
            province="M",
        ),
    )


def test_nif_valid(minimal_invoice) -> None:
    data = minimal_invoice.model_dump()
    data["seller"] = _make_party("12345678Z").model_dump()
    inv = SpanishInvoice.model_validate(data)
    assert inv.seller.tax_id.identifier == "12345678Z"


def test_nif_invalid_checksum(minimal_invoice) -> None:
    data = minimal_invoice.model_dump()
    data["seller"] = _make_party("12345678A").model_dump()
    with pytest.raises(ValueError, match="Invalid Spanish tax ID"):
        SpanishInvoice.model_validate(data)


def test_nie_valid(minimal_invoice) -> None:
    data = minimal_invoice.model_dump()
    data["seller"] = _make_party("X1234567L").model_dump()
    inv = SpanishInvoice.model_validate(data)
    assert inv.seller.tax_id.identifier == "X1234567L"


def test_nie_invalid(minimal_invoice) -> None:
    data = minimal_invoice.model_dump()
    data["seller"] = _make_party("X1234567A").model_dump()
    with pytest.raises(ValueError, match="Invalid Spanish tax ID"):
        SpanishInvoice.model_validate(data)


def test_cif_valid(minimal_invoice) -> None:
    data = minimal_invoice.model_dump()
    data["seller"] = _make_party("A12345674").model_dump()
    inv = SpanishInvoice.model_validate(data)
    assert inv.seller.tax_id.identifier == "A12345674"


def test_cif_invalid(minimal_invoice) -> None:
    data = minimal_invoice.model_dump()
    data["seller"] = _make_party("A12345670").model_dump()
    with pytest.raises(ValueError, match="Invalid Spanish tax ID"):
        SpanishInvoice.model_validate(data)


# ---------------------------------------------------------------------------
# IRPF round-trip (Batch 1 — ES-TL-4)
# ---------------------------------------------------------------------------


def test_irpf_fields_roundtrip(minimal_invoice) -> None:
    data = minimal_invoice.model_dump()
    data["irpf_rate"] = "15.00"
    data["irpf_amount"] = "150.00"
    inv = SpanishInvoice.model_validate(data)
    assert inv.irpf_rate == Decimal("15.00")
    assert inv.irpf_amount == Decimal("150.00")


# ---------------------------------------------------------------------------
# PA-buyer requires resolution_reference (Batch 1 — ES-SC-4)
# ---------------------------------------------------------------------------


def test_pa_buyer_requires_resolution_reference(minimal_invoice) -> None:
    data = minimal_invoice.model_dump()
    data["buyer"] = _make_party("P1234567D", "Ayuntamiento de Madrid").model_dump()
    with pytest.raises(ValueError, match="resolution_reference is required"):
        SpanishInvoice.model_validate(data)


def test_pa_buyer_with_resolution_reference(minimal_invoice) -> None:
    data = minimal_invoice.model_dump()
    data["buyer"] = _make_party("P1234567D", "Ayuntamiento de Madrid").model_dump()
    data["resolution_reference"] = "RES-2025-001"
    inv = SpanishInvoice.model_validate(data)
    assert inv.resolution_reference == "RES-2025-001"


# ---------------------------------------------------------------------------
# FaturaeInvoice — EN 16931 family scaffold (Batch 5 — ES-SC-9)
# ---------------------------------------------------------------------------


def test_faturae_invoice_is_en16931_subclass() -> None:
    from mcp_einvoicing_core.en16931 import EN16931Invoice

    from mcp_facturacion_electronica_es.models.es import FaturaeInvoice

    assert issubclass(FaturaeInvoice, EN16931Invoice)


def test_faturae_invoice_pa_fields() -> None:
    from mcp_facturacion_electronica_es.models.es import FaturaeInvoice

    fields = FaturaeInvoice.model_fields
    assert "resolution_reference" in fields
    assert "receiver_transaction_reference" in fields
    assert "invoice_issuer_type" in fields


def test_faturae_invoice_default_issuer_type() -> None:
    from datetime import date

    from mcp_einvoicing_core.en16931 import EN16931Address, EN16931Party, EN16931Tax

    from mcp_facturacion_electronica_es.models.es import FaturaeInvoice

    addr = EN16931Address(
        line_one="Calle Mayor 1",
        city="Madrid",
        postcode="28001",
        country_code="ES",
    )
    inv = FaturaeInvoice(
        profile="urn:cen.eu:en16931:2017",
        invoice_number="FE-001",
        invoice_date=date(2025, 3, 15),
        invoice_type_code="380",
        currency_code="EUR",
        seller=EN16931Party(name="Seller SL", address=addr),
        buyer=EN16931Party(name="Buyer SA", address=addr),
        tax_lines=[
            EN16931Tax(
                category="S",
                rate=Decimal("21"),
                taxable_amount=Decimal("1000"),
                tax_amount=Decimal("210"),
            )
        ],
        sum_of_line_net_amounts=Decimal("1000"),
        tax_exclusive_amount=Decimal("1000"),
        tax_total=Decimal("210"),
        tax_inclusive_amount=Decimal("1210"),
        amount_due=Decimal("1210"),
    )
    assert inv.invoice_issuer_type == "EU"
