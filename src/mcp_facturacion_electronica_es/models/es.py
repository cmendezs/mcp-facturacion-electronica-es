"""Spanish e-invoicing domain models and enumerations.

ES-specific enums and the SpanishInvoice validation model.
All tool handlers use InvoiceDocument from mcp-einvoicing-core as the
primary invoice representation; SpanishInvoice wraps it for audit CHECK 3.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from mcp_einvoicing_core.models import (
    InvoiceDocument,
    VATSummary,
)
from pydantic import Field


class SpanishRegime(StrEnum):
    """Applicable e-invoicing regime, determined by tax address and SII enrolment.

    TicketBAI (Pais Vasco) is explicitly out of scope for this package.
    """

    VERIFACTU = "VERIFACTU"
    VERIFACTU_SII = "VERIFACTU+SII"


class VerifactuInvoiceType(StrEnum):
    """VERI*FACTU TipoFactura codes (Order HAC/1177/2024 Annex I)."""

    F1 = "F1"   # Standard invoice
    F2 = "F2"   # Simplified invoice (ticket)
    F3 = "F3"   # Invoice replacing simplified invoices (art. 33 RD 1619/2012)
    R1 = "R1"   # Corrective — art. 80.1 and 80.2 LIVA (error of law, insolvency)
    R2 = "R2"   # Corrective — art. 80.3 LIVA (total non-payment)
    R3 = "R3"   # Corrective — art. 80.4 LIVA (partial non-payment)
    R4 = "R4"   # Corrective — other reasons (art. 80.1, 80.2, 80.6 LIVA)
    R5 = "R5"   # Corrective — simplified invoices


class SIIRecordType(StrEnum):
    """SII record direction."""

    issued = "issued"      # FacturaExpedida
    received = "received"  # FacturaRecibida


class SIICommunicationType(StrEnum):
    """SII TipoComunicacion codes (AEAT SII technical guide v3.0)."""

    A0 = "A0"  # New record (alta)
    A1 = "A1"  # Modification
    A4 = "A4"  # Removal / baja


class B2BFormat(StrEnum):
    """Output format for Crea y Crece B2B e-invoices (Ley 18/2022)."""

    ubl = "ubl"
    facturae = "facturae"


class EntityType(StrEnum):
    """Spanish tax entity type for mandate applicability checks."""

    IS = "IS"      # Impuesto sobre Sociedades (corporate tax)
    IRPF = "IRPF"  # Impuesto sobre la Renta (income tax / self-employed)


class AEATResponseType(StrEnum):
    """AEAT XML response type for es__parse_aeat_response."""

    verifactu = "verifactu"
    sii = "sii"


# ---------------------------------------------------------------------------
# SpanishInvoice — ES validation wrapper (extends core InvoiceDocument)
# Required by audit CHECK 3 to verify EN 16931 mandatory field coverage.
# Tools use InvoiceDocument.model_validate() directly; this class is the
# validated ES-specific document with regime and VERI*FACTU metadata.
# ---------------------------------------------------------------------------

class SpanishInvoice(InvoiceDocument):
    """Spanish invoice extending the core InvoiceDocument with ES-specific fields.

    All EN 16931 mandatory fields (BT-1, BT-2, BT-3, BT-5, BG-4, BG-7,
    BG-23, BT-109, BT-112, BT-110, BT-115) are inherited from InvoiceDocument.

    Additional ES fields:
        regime:        Detected e-invoicing regime (use es__detect_regional_regime).
        verifactu_type: TipoFactura code for VERI*FACTU records.
        software_id:   IDSistemaInformatico of the certified software.
        software_nif:  NIF of the software developer.
    """

    # Inherited mandatory fields (audit CHECK 3 checks these on SpanishInvoice):
    #   invoice_number    → InvoiceDocument.number
    #   invoice_date      → InvoiceDocument.date
    #   invoice_type_code → InvoiceDocument.document_type
    #   currency_code     → InvoiceDocument.currency
    #   seller            → InvoiceDocument.seller
    #   buyer             → InvoiceDocument.buyer
    #   tax_lines         → InvoiceDocument.vat_summary (alias below)
    #   tax_exclusive_amount / tax_inclusive_amount / tax_total / amount_due
    #
    # These aliases map the audit field names to InvoiceDocument fields:

    @property
    def invoice_number(self) -> str:
        return self.number

    @property
    def invoice_date(self) -> str:
        return self.date

    @property
    def invoice_type_code(self) -> str:
        return self.document_type

    @property
    def currency_code(self) -> str:
        return self.currency

    @property
    def tax_lines(self) -> list[VATSummary]:
        return self.vat_summary

    # Computed totals (derived from vat_summary if not set explicitly)
    @property
    def tax_exclusive_amount(self) -> Decimal:
        return sum((v.taxable_base for v in self.vat_summary), Decimal("0"))

    @property
    def tax_total(self) -> Decimal:
        return sum((v.vat_amount for v in self.vat_summary), Decimal("0"))

    @property
    def tax_inclusive_amount(self) -> Decimal:
        return self.tax_exclusive_amount + self.tax_total

    @property
    def amount_due(self) -> Decimal:
        return self.tax_inclusive_amount

    # ES-specific optional fields
    regime: SpanishRegime | None = Field(
        default=None,
        description=(
            "Applicable e-invoicing regime. "
            "Call es__detect_regional_regime before generating records."
        ),
    )
    verifactu_type: VerifactuInvoiceType | None = Field(
        default=None,
        description="TipoFactura for VERI*FACTU (overrides document_type if set).",
    )
    software_id: str | None = Field(
        default=None,
        description="IDSistemaInformatico of the certified software.",
    )
    software_nif: str | None = Field(
        default=None,
        description="NIF of the software developer.",
    )
