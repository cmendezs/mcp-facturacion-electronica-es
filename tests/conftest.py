"""Shared test fixtures for mcp-facturacion-electronica-es tests."""

from __future__ import annotations

from decimal import Decimal

import pytest
from mcp_einvoicing_core.models import (
    InvoiceDocument,
    InvoiceLineItem,
    InvoiceParty,
    PartyAddress,
    TaxIdentifier,
    VATSummary,
)


def _make_party(nif: str, name: str, city: str = "Madrid") -> InvoiceParty:
    return InvoiceParty(
        tax_id=TaxIdentifier(country_code="ES", identifier=nif),
        name=name,
        address=PartyAddress(
            street="Calle Mayor 1",
            postal_code="28001",
            city=city,
            country_code="ES",
            province="M",
        ),
    )


@pytest.fixture()
def seller() -> InvoiceParty:
    return _make_party("B12345674", "Empresa de Prueba SL")


@pytest.fixture()
def buyer() -> InvoiceParty:
    return _make_party("A98765431", "Cliente de Prueba SA", city="Barcelona")


@pytest.fixture()
def minimal_invoice(seller: InvoiceParty, buyer: InvoiceParty) -> InvoiceDocument:
    """Minimal valid InvoiceDocument covering EN 16931 mandatory fields.

    Uses a standard F1 invoice with a single 21% VAT line — suitable for
    VERI*FACTU, Facturae, SII, and B2B tool tests.
    """
    return InvoiceDocument(
        document_type="F1",
        date="2025-03-15",
        number="2025-0001",
        currency="EUR",
        seller=seller,
        buyer=buyer,
        lines=[
            InvoiceLineItem(
                line_number=1,
                description="Servicios de consultoría",
                quantity=Decimal("10"),
                unit_of_measure="HUR",
                unit_price=Decimal("100.00"),
                total_price=Decimal("1000.00"),
                vat_rate=Decimal("21"),
                currency="EUR",
            )
        ],
        vat_summary=[
            VATSummary(
                vat_rate=Decimal("21"),
                taxable_base=Decimal("1000.00"),
                vat_amount=Decimal("210.00"),
            )
        ],
        note="Servicios de consultoría — período marzo 2025",
    )


@pytest.fixture()
def minimal_verifactu_xml() -> str:
    """Minimal plausible VERI*FACTU XML for parser tests.

    [NEED: validate against official XSD v1.0 from BOE-A-2024-22138]
    """
    return """<?xml version="1.0" encoding="UTF-8"?>
<RegFactuSistemaFacturacion>
  <Cabecera>
    <ObligadoEmision>
      <NombreRazonSocial>Empresa de Prueba SL</NombreRazonSocial>
      <NIF>B12345678</NIF>
    </ObligadoEmision>
  </Cabecera>
  <RegistroAlta>
    <IDVersion>1.0</IDVersion>
    <IDFactura>
      <IDEmisorFactura>B12345678</IDEmisorFactura>
      <NumSerieFactura>2025-0001</NumSerieFactura>
      <FechaExpedicionFactura>15-03-2025</FechaExpedicionFactura>
    </IDFactura>
    <NombreRazonEmisor>Empresa de Prueba SL</NombreRazonEmisor>
    <TipoFactura>F1</TipoFactura>
    <DescripcionOperacion>Servicios de consultoría</DescripcionOperacion>
    <CuotaTotal>210.00</CuotaTotal>
    <ImporteTotal>1210.00</ImporteTotal>
    <FechaHoraHusoGenRegistro>2025-03-15T10:30:00+01:00</FechaHoraHusoGenRegistro>
    <Huella>AABBCCDDEEFF00112233445566778899AABBCCDDEEFF00112233445566778899</Huella>
  </RegistroAlta>
</RegFactuSistemaFacturacion>"""


@pytest.fixture()
def minimal_facturae_xml() -> str:
    """Minimal plausible Facturae 3.2.2 XML for parser tests.

    [NEED: validate against Facturae 3.2.2 XSD from facturae.gob.es]
    """
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Facturae xmlns="http://www.facturae.gob.es/formato/Versiones/Facturaev3_2_2.xml">'
        "<FileHeader>"
        "<SchemaVersion>3.2.2</SchemaVersion>"
        "<Modality>I</Modality>"
        "<InvoiceIssuerType>EU</InvoiceIssuerType>"
        "<Batch>"
        "<BatchIdentifier>2025-0001</BatchIdentifier>"
        "<InvoicesCount>1</InvoicesCount>"
        "<TotalInvoicesAmount><TotalAmount>1210.00</TotalAmount></TotalInvoicesAmount>"
        "<TotalOutstandingAmount><TotalAmount>1210.00</TotalAmount></TotalOutstandingAmount>"
        "<TotalExecutableAmount><TotalAmount>1210.00</TotalAmount></TotalExecutableAmount>"
        "<InvoiceCurrencyCode>EUR</InvoiceCurrencyCode>"
        "</Batch>"
        "</FileHeader>"
        "<Parties>"
        "<SellerParty>"
        "<TaxIdentification>"
        "<PersonTypeCode>J</PersonTypeCode>"
        "<ResidenceTypeCode>R</ResidenceTypeCode>"
        "<TaxIdentificationNumber>B12345678</TaxIdentificationNumber>"
        "</TaxIdentification>"
        "<LegalEntity><CorporateName>Empresa de Prueba SL</CorporateName></LegalEntity>"
        "</SellerParty>"
        "<BuyerParty>"
        "<TaxIdentification>"
        "<PersonTypeCode>J</PersonTypeCode>"
        "<ResidenceTypeCode>R</ResidenceTypeCode>"
        "<TaxIdentificationNumber>A98765432</TaxIdentificationNumber>"
        "</TaxIdentification>"
        "<LegalEntity><CorporateName>Cliente de Prueba SA</CorporateName></LegalEntity>"
        "</BuyerParty>"
        "</Parties>"
        "<Invoices>"
        "<Invoice>"
        "<InvoiceHeader>"
        "<InvoiceNumber>2025-0001</InvoiceNumber>"
        "<InvoiceDocumentType>FC</InvoiceDocumentType>"
        "<InvoiceClass>OO</InvoiceClass>"
        "</InvoiceHeader>"
        "<InvoiceIssueData>"
        "<IssueDate>2025-03-15</IssueDate>"
        "<InvoiceCurrencyCode>EUR</InvoiceCurrencyCode>"
        "<TaxCurrencyCode>EUR</TaxCurrencyCode>"
        "<LanguageName>es</LanguageName>"
        "</InvoiceIssueData>"
        "<TaxesOutputs>"
        "<Tax>"
        "<TaxTypeCode>01</TaxTypeCode>"
        "<TaxRate>21.00</TaxRate>"
        "<TaxableBase><TotalAmount>1000.00</TotalAmount></TaxableBase>"
        "<TaxAmount><TotalAmount>210.00</TotalAmount></TaxAmount>"
        "</Tax>"
        "</TaxesOutputs>"
        "<InvoiceTotals>"
        "<TotalGrossAmount>1000.00</TotalGrossAmount>"
        "<TotalGeneralDiscounts>0.00</TotalGeneralDiscounts>"
        "<TotalGeneralSurcharges>0.00</TotalGeneralSurcharges>"
        "<TotalGrossAmountBeforeTaxes>1000.00</TotalGrossAmountBeforeTaxes>"
        "<TotalTaxOutputs>210.00</TotalTaxOutputs>"
        "<TotalTaxesWithheld>0.00</TotalTaxesWithheld>"
        "<InvoiceTotal>1210.00</InvoiceTotal>"
        "<TotalOutstandingAmount>1210.00</TotalOutstandingAmount>"
        "<TotalExecutableAmount>1210.00</TotalExecutableAmount>"
        "</InvoiceTotals>"
        "</Invoice>"
        "</Invoices>"
        "</Facturae>"
    )
