"""Spanish e-invoicing domain models and enumerations.

All Pydantic models and enums specific to the Spanish regulatory landscape.
Shared base models (InvoiceDocument, InvoiceParty, etc.) come from
mcp-einvoicing-core once that interface is finalised.

[NEED: replace stub SpanishInvoice with a class that extends core BaseInvoice
       once mcp-einvoicing-core BaseInvoice is published]
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SpanishRegime(str, Enum):
    """Applicable e-invoicing regime, determined by tax address and SII enrolment."""

    VERIFACTU = "VERIFACTU"
    TICKETBAI = "TICKETBAI"
    NATICKET = "NATICKET"
    VERIFACTU_SII = "VERIFACTU+SII"


class VerifactuInvoiceType(str, Enum):
    """VERI*FACTU TipoFactura codes (Order HAC/1177/2024)."""

    F1 = "F1"   # Standard invoice
    F2 = "F2"   # Simplified invoice
    F3 = "F3"   # Invoice replacing simplified invoices
    R1 = "R1"   # Corrective — art. 80.1 and 80.2 LIVA
    R2 = "R2"   # Corrective — art. 80.3 LIVA
    R3 = "R3"   # Corrective — art. 80.4 LIVA
    R4 = "R4"   # Corrective — other reasons
    R5 = "R5"   # Corrective — simplified invoices


class SIIRecordType(str, Enum):
    """SII record direction."""

    issued = "issued"      # FacturaExpedida
    received = "received"  # FacturaRecibida


class SIICommunicationType(str, Enum):
    """SII TipoComunicacion codes (AEAT SII technical guide v3.0)."""

    A0 = "A0"  # New record
    A1 = "A1"  # Modification
    A4 = "A4"  # Removal / baja


class TicketBAIProvince(str, Enum):
    """Basque Country province for TicketBAI routing."""

    araba = "araba"
    gipuzkoa = "gipuzkoa"
    bizkaia = "bizkaia"


class B2BFormat(str, Enum):
    """Output format for Crea y Crece B2B e-invoices (Ley 18/2022)."""

    ubl = "ubl"
    facturae = "facturae"


class EntityType(str, Enum):
    """Spanish tax entity type for mandate applicability checks."""

    IS = "IS"      # Impuesto sobre Sociedades (corporate tax)
    IRPF = "IRPF"  # Impuesto sobre la Renta (income tax / self-employed)


class AEATResponseType(str, Enum):
    """AEAT XML response type for parsing."""

    verifactu = "verifactu"
    sii = "sii"


# ---------------------------------------------------------------------------
# Stub invoice model
# [NEED: replace with a class extending core BaseInvoice once core is available]
# ---------------------------------------------------------------------------

class SpanishInvoice(BaseModel):
    """Minimal Spanish invoice model covering EN 16931 mandatory fields.

    [NEED: extend with VERI*FACTU-specific fields (software_id, software_nif,
           Huella chain) and Facturae-specific fields once implementation begins]
    [NEED: derive from mcp-einvoicing-core BaseInvoice when that model is published]
    """

    invoice_number: str = Field(..., description="BT-1 — Número de factura")
    invoice_date: date = Field(..., description="BT-2 — Fecha de expedición")
    invoice_type_code: VerifactuInvoiceType = Field(
        VerifactuInvoiceType.F1, description="BT-3 — Tipo de factura"
    )
    currency_code: str = Field("EUR", description="BT-5 — Moneda")
    seller: dict = Field(..., description="BG-4 — Emisor")
    buyer: dict = Field(..., description="BG-7 — Receptor")
    tax_lines: list[dict] = Field(default_factory=list, description="BG-23 — Desglose IVA")
    tax_exclusive_amount: Decimal = Field(..., description="BT-109 — Base imponible")
    tax_inclusive_amount: Decimal = Field(..., description="BT-112 — Total con IVA")
    tax_total: Decimal = Field(..., description="BT-110 — Cuota IVA")
    amount_due: Decimal = Field(..., description="BT-115 — Importe a pagar")
    regime: Optional[SpanishRegime] = Field(
        None,
        description="Régimen detectado (VERIFACTU / TICKETBAI / NATICKET / VERIFACTU+SII). "
                    "Use es__detect_regional_regime before generating any records.",
    )
