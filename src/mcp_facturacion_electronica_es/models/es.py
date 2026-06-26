"""Spanish e-invoicing domain models and enumerations.

ES-specific enums and the SpanishInvoice validation model.
All tool handlers use InvoiceDocument from mcp-einvoicing-core as the
primary invoice representation; SpanishInvoice wraps it for audit CHECK 3.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Any

from mcp_einvoicing_core.en16931 import EN16931Invoice
from mcp_einvoicing_core.models import (
    InvoiceDocument,
    VATSummary,
)
from pydantic import Field, field_validator, model_validator


class SpanishRegime(StrEnum):
    """Applicable e-invoicing regime, determined by tax address and SII enrolment.

    TicketBAI (Pais Vasco) is explicitly out of scope for this package.
    """

    VERIFACTU = "VERIFACTU"
    VERIFACTU_SII = "VERIFACTU+SII"


class VerifactuInvoiceType(StrEnum):
    """VERI*FACTU TipoFactura codes (Order HAC/1177/2024 Annex I)."""

    F1 = "F1"  # Standard invoice
    F2 = "F2"  # Simplified invoice (ticket)
    F3 = "F3"  # Invoice replacing simplified invoices (art. 33 RD 1619/2012)
    R1 = "R1"  # Corrective — art. 80.1 and 80.2 LIVA (error of law, insolvency)
    R2 = "R2"  # Corrective — art. 80.3 LIVA (total non-payment)
    R3 = "R3"  # Corrective — art. 80.4 LIVA (partial non-payment)
    R4 = "R4"  # Corrective — other reasons (art. 80.1, 80.2, 80.6 LIVA)
    R5 = "R5"  # Corrective — simplified invoices


class SIIRecordType(StrEnum):
    """SII record direction."""

    issued = "issued"  # FacturaExpedida
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

    IS = "IS"  # Impuesto sobre Sociedades (corporate tax)
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
    clave_regimen: str | None = Field(
        default=None,
        description="ClaveRegimen fiscal (AEAT taxonomy, e.g. '01' general).",
    )
    irpf_rate: Decimal | None = Field(
        default=None,
        description="IRPF withholding rate as percentage (e.g. 15.00).",
    )
    irpf_amount: Decimal | None = Field(
        default=None,
        description="IRPF withholding amount (computed from taxable base * irpf_rate).",
    )
    recargo_equivalencia_rate: Decimal | None = Field(
        default=None,
        description="Recargo de Equivalencia surcharge rate as percentage.",
    )
    resolution_reference: str | None = Field(
        default=None,
        description="Factura-e ResolutionReference for B2G PA invoices.",
    )
    receiver_transaction_reference: str | None = Field(
        default=None,
        description="Factura-e ReceiverTransactionReference for B2G PA invoices.",
    )

    @field_validator("seller", "buyer", mode="before")
    @classmethod
    def _validate_party_tax_id(cls, v: Any) -> Any:
        """Validate Spanish tax IDs (NIF/NIE/CIF) on seller and buyer parties."""
        if v is None:
            return v
        from mcp_facturacion_electronica_es._helpers import validate_spanish_tax_id

        tax_id = None
        if hasattr(v, "tax_id"):
            tax_id = v.tax_id
        elif isinstance(v, dict):
            tax_id = v.get("tax_id")
        if tax_id is None:
            return v

        identifier = None
        country = None
        if hasattr(tax_id, "identifier"):
            identifier = tax_id.identifier
            country = getattr(tax_id, "country_code", None)
        elif isinstance(tax_id, dict):
            identifier = tax_id.get("identifier")
            country = tax_id.get("country_code")

        if identifier and country == "ES":
            valid, error = validate_spanish_tax_id(identifier)
            if not valid:
                raise ValueError(f"Invalid Spanish tax ID '{identifier}': {error}")
        return v

    @model_validator(mode="after")
    def _require_resolution_ref_for_pa(self) -> SpanishInvoice:
        """PA buyers (NIF starting with P, Q, or S) require a resolution_reference."""
        if self.buyer and self.buyer.tax_id:
            nif = self.buyer.tax_id.identifier.strip().upper()
            if nif and nif[0] in {"P", "Q", "S"} and not self.resolution_reference:
                msg = (
                    "resolution_reference is required when the buyer is a Spanish "
                    f"public administration entity (NIF prefix '{nif[0]}')"
                )
                raise ValueError(msg)
        return self


# ---------------------------------------------------------------------------
# FaturaeInvoice — EN 16931 family model for Factura-e 3.2.2
# Audit CHECK 1 verifies canonical tree against EN16931Invoice.
# AEAT-specific fields (regime, verifactu_type, etc.) stay on SpanishInvoice.
# ---------------------------------------------------------------------------


class FaturaeInvoice(EN16931Invoice):
    """Factura-e 3.2.2 invoice extending EN16931Invoice with B2G PA fields.

    Factura-e is EN 16931-adjacent: it predates the standard but maps to its
    semantics. This class carries Factura-e PA extension fields that are not
    part of EN 16931 but are required for Spanish public administration invoices.
    """

    resolution_reference: str | None = Field(
        default=None,
        description="Factura-e ResolutionReference for B2G PA invoices.",
    )
    receiver_transaction_reference: str | None = Field(
        default=None,
        description="Factura-e ReceiverTransactionReference for B2G PA invoices.",
    )
    invoice_issuer_type: str = Field(
        default="EU",
        description="Factura-e InvoiceIssuerType: EU (seller), EM (buyer), TE (third party).",
    )
