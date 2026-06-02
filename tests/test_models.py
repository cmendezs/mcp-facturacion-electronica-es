"""Tests for ES models: SpanishInvoice, enums, audit CHECK 3 coverage."""

from __future__ import annotations

from decimal import Decimal

import pytest

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
    invoice = SpanishInvoice.model_validate({
        **minimal_invoice.model_dump(),
        "regime": SpanishRegime.VERIFACTU,
        "verifactu_type": VerifactuInvoiceType.F1,
        "software_id": "SW-001",
        "software_nif": "B87654321",
    })
    assert invoice.regime == SpanishRegime.VERIFACTU
    assert invoice.verifactu_type == VerifactuInvoiceType.F1
