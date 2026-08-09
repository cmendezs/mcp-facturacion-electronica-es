"""Shared helpers for mcp-facturacion-electronica-es tool implementations.

All tool handlers import from here. Nothing in this module imports from tool modules.
"""

from __future__ import annotations

import json
import logging
import os
from decimal import ROUND_HALF_UP, Decimal
from types import MappingProxyType
from typing import Any

import mcp.types as types
from mcp_einvoicing_core.exceptions import EInvoicingError
from mcp_einvoicing_core.models import InvoiceDocument, TaxIdentifier

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Input parsing
# ---------------------------------------------------------------------------


def parse_invoice(data: Any) -> InvoiceDocument:
    """Parse a dict (from MCP arguments) into an InvoiceDocument.

    Args:
        data: Raw dict from MCP tool arguments or an already-parsed InvoiceDocument.

    Returns:
        Validated InvoiceDocument.

    Raises:
        EInvoicingError: If the dict cannot be validated.
    """
    if isinstance(data, InvoiceDocument):
        return data
    try:
        return InvoiceDocument.model_validate(data)
    except Exception as exc:
        raise EInvoicingError(f"Invalid invoice data: {exc}") from exc


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------


def ok(data: dict[str, Any]) -> list[types.TextContent]:
    """Wrap a result dict as a successful MCP TextContent response."""
    return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False, default=str))]


def err(message: str, code: str | None = None) -> list[types.TextContent]:
    """Wrap an error message as an MCP TextContent response."""
    payload: dict[str, Any] = {"error": message}
    if code:
        payload["error_code"] = code
    return [types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def fmt_amount(value: Decimal | float | int | str) -> str:
    """Return a monetary value formatted to exactly 2 decimal places (HALF_UP).

    Per Factura-e spec s4.1 (document/line totals, 2 decimal places) and the
    AEAT VeriFactu huella normalization rules, half-cent amounts round HALF_UP
    (e.g. 2.665 -> 2.67), not Python's Decimal-context-default HALF_EVEN.
    """
    return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def fmt_date_es(date_iso: str) -> str:
    """Convert YYYY-MM-DD to DD-MM-YYYY (VERI*FACTU, SII, and Facturae date format).

    Example: "2025-03-15" → "15-03-2025"
    """
    if len(date_iso) == 10 and date_iso[4] == "-":
        y, m, d = date_iso.split("-")
        return f"{d}-{m}-{y}"
    return date_iso


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------


def aeat_env() -> str:
    """Return 'sandbox' or 'production' from AEAT_ENV (default: 'sandbox')."""
    raw = os.environ.get("AEAT_ENV", "sandbox").lower().strip()
    if raw not in {"sandbox", "production"}:
        logger.warning("Unknown AEAT_ENV value %r — defaulting to 'sandbox'", raw)
        return "sandbox"
    return raw


def face_env() -> str:
    """Return 'sandbox' or 'production' from FACE_ENV (default: 'sandbox')."""
    raw = os.environ.get("FACE_ENV", "sandbox").lower().strip()
    if raw not in {"sandbox", "production"}:
        logger.warning("Unknown FACE_ENV value %r — defaulting to 'sandbox'", raw)
        return "sandbox"
    return raw


# ---------------------------------------------------------------------------
# AEAT endpoint registry
# ---------------------------------------------------------------------------

#: VERI*FACTU submission endpoints (immutable — MappingProxyType prevents runtime mutation)
VERIFACTU_ENDPOINTS: MappingProxyType[str, str] = MappingProxyType(
    {
        "sandbox": (
            "https://prewww2.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/FactSistemaFacturacion"
        ),
        "production": (
            "https://www2.agenciatributaria.gob.es"
            "/wlpl/TIKE-CONT/ws/SistemaFacturacion/FactSistemaFacturacion"
        ),
        # [NEED: verify both URLs against AEAT VeriFactu technical guide PDF
        #  (not included in bundled specs/ as of 2026-06-26; XSD namespace path
        #  /tike/cont/ws/ is consistent with the TIKE-CONT path used here)]
    }
)

#: VERI*FACTU consulta (ConsultaFactuSistemaFacturacion / ConsultaLR.xsd) endpoints.
#: [NEED: verify: no VeriFactu WSDL is bundled in specs/ (only XSDs); the exact
#:  URL segment for the consulta operation has not been confirmed. Reuses the
#:  same TIKE-CONT service base path as VERIFACTU_ENDPOINTS by convention.]
VERIFACTU_CONSULTA_ENDPOINTS: MappingProxyType[str, str] = MappingProxyType(
    {
        "sandbox": ("https://prewww2.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/ConsultaLR"),
        "production": (
            "https://www2.agenciatributaria.gob.es"
            "/wlpl/TIKE-CONT/ws/SistemaFacturacion/ConsultaLR"
        ),
    }
)

#: SII issued-invoice submission endpoints (immutable).
#: The www10 host is not a failover secondary: its WSDL port name
#: ("SuministroFactEmitidasSello") and the AEAT integration guide identify it as
#: the company-seal-certificate (Certificado de Sello Electrónico) variant of the
#: same operation, addressed separately from the www1 port used with a personal/
#: representative certificate. Callers must pick "primary" or "sello" based on
#: which certificate type is presented, not as a primary/failover pair.
#: Source: specs/sii/schemas/SuministroFactEmitidas.wsdl (wsdl:port names)
SII_ISSUED_ENDPOINTS: MappingProxyType[str, MappingProxyType[str, str]] = MappingProxyType(
    {
        "sandbox": MappingProxyType(
            {
                "primary": "https://prewww1.aeat.es/wlpl/SSII-FACT/ws/fe/SiiFactFEV1SOAP",
                "sello": "https://prewww10.aeat.es/wlpl/SSII-FACT/ws/fe/SiiFactFEV1SOAP",
            }
        ),
        "production": MappingProxyType(
            {
                "primary": "https://www1.agenciatributaria.gob.es/wlpl/SSII-FACT/ws/fe/SiiFactFEV1SOAP",
                "sello": "https://www10.agenciatributaria.gob.es/wlpl/SSII-FACT/ws/fe/SiiFactFEV1SOAP",
            }
        ),
    }
)

#: SII received-invoice submission endpoints (immutable).
#: The www10 host is not a failover secondary: its WSDL port name
#: ("SuministroFactRecibidasSello") identifies it as the company-seal-certificate
#: variant of the same operation, mirroring SII_ISSUED_ENDPOINTS above.
#: Source: specs/sii/schemas/SuministroFactRecibidas.wsdl (wsdl:port names)
SII_RECEIVED_ENDPOINTS: MappingProxyType[str, MappingProxyType[str, str]] = MappingProxyType(
    {
        "sandbox": MappingProxyType(
            {
                "primary": "https://prewww1.aeat.es/wlpl/SSII-FACT/ws/fr/SiiFactFRV1SOAP",
                "sello": "https://prewww10.aeat.es/wlpl/SSII-FACT/ws/fr/SiiFactFRV1SOAP",
            }
        ),
        "production": MappingProxyType(
            {
                "primary": "https://www1.agenciatributaria.gob.es/wlpl/SSII-FACT/ws/fr/SiiFactFRV1SOAP",
                "sello": "https://www10.agenciatributaria.gob.es/wlpl/SSII-FACT/ws/fr/SiiFactFRV1SOAP",
            }
        ),
    }
)

#: FACe integrator REST API base URLs (immutable).
#: Source: specs/facturae/documentation/FACe-manual-api-integradores.pdf section 2.2
FACE_BASE_URLS: MappingProxyType[str, str] = MappingProxyType(
    {
        "sandbox": "https://se-api-face.redsara.es",
        "production": "https://api.face.gob.es",
    }
)

# ---------------------------------------------------------------------------
# Spanish tax-ID validation (NIF / NIE / CIF prefix routing)
# ---------------------------------------------------------------------------


def validate_spanish_tax_id(value: str) -> tuple[bool, str]:
    """Route a Spanish tax identifier to the appropriate core validator.

    Prefix routing:
        [0-9] or [KLM] -> NIF (individuals, foreign nationals with K/L/M prefix)
        [XYZ]           -> NIE (foreigners)
        [ABCDEFGHJNPQRSUVW] -> CIF (companies)

    Returns:
        (True, "") on success, (False, error_message) on failure.
    """
    cleaned = value.strip().upper()
    if not cleaned:
        return False, "Empty tax identifier."
    first = cleaned[0]
    if first.isdigit() or first in {"K", "L", "M"}:
        return TaxIdentifier.validate_es_nif(cleaned)
    if first in {"X", "Y", "Z"}:
        return TaxIdentifier.validate_es_nie(cleaned)
    if first in set("ABCDEFGHJNPQRSUVW"):
        return TaxIdentifier.validate_es_cif(cleaned)
    return False, f"Unrecognised Spanish tax-ID prefix '{first}'."


#: Facturae XAdES-EPES signature policy (Orden EHA/962/2007)
FACTURAE_POLICY_ID = (
    "http://www.facturae.es/politica_de_firma_formato_facturae"
    "/politica_de_firma_formato_facturae_v3_1.pdf"
)
#: SHA-1 digest from the AEAT-validated .xsig example (specs/facturae/examples/)
FACTURAE_POLICY_HASH: str = "Ohixl6upD6av8N7pEvDABhEL6hM="
FACTURAE_POLICY_HASH_ALGORITHM: str = "http://www.w3.org/2000/09/xmldsig#sha1"
#: SHA-256 fallback (inactive until AEAT mandates SHA-256 for policy digest)
FACTURAE_POLICY_HASH_SHA256: str | None = None
FACTURAE_POLICY_HASH_SHA256_ALGORITHM: str = "http://www.w3.org/2001/04/xmlenc#sha256"

# VeriFactu re-chaining: on permanent submission failure, the caller must persist
# the prior Huella so the next record can chain correctly. The chain is broken if
# a record is generated but never accepted by AEAT, because subsequent records
# reference its Huella. Callers should store (emisor_nif, num_serie, fecha, huella)
# for each generated record and re-submit with the last accepted Huella on retry.
