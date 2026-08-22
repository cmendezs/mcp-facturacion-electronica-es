"""MCP server entrypoint for mcp-facturacion-electronica-es."""

from __future__ import annotations

import logging
import os
from typing import Any

from mcp_einvoicing_core import EInvoicingMCPServer

from mcp_facturacion_electronica_es.tools.b2b import (
    es__check_b2b_mandate_applicability,
    es__generate_b2b_einvoice_es,
)
from mcp_facturacion_electronica_es.tools.facturae import (
    es__generate_facturae_xml,
    es__get_face_invoice_status,
    es__sign_facturae_xades,
    es__submit_to_face,
    es__validate_facturae_schema,
)
from mcp_facturacion_electronica_es.tools.sii import (
    es__build_sii_invoice_record,
    es__generate_sii_correction,
    es__query_sii_status,
    es__submit_sii_batch,
)
from mcp_facturacion_electronica_es.tools.utils import (
    es__detect_regional_regime,
    es__get_compliance_status,
    es__parse_aeat_response,
)
from mcp_facturacion_electronica_es.tools.verifactu import (
    es__cancel_verifactu_record,
    es__generate_qr_verifactu,
    es__generate_verifactu_record,
    es__query_verifactu_status,
    es__submit_verifactu_to_aeat,
    es__validate_verifactu_record,
)

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)


def _register_es_tools(mcp: Any) -> None:
    """Register all Spanish e-invoicing tools onto the shared FastMCP instance."""
    # VERI*FACTU
    mcp.tool()(es__generate_verifactu_record)
    mcp.tool()(es__validate_verifactu_record)
    mcp.tool()(es__submit_verifactu_to_aeat)
    mcp.tool()(es__query_verifactu_status)
    mcp.tool()(es__generate_qr_verifactu)
    mcp.tool()(es__cancel_verifactu_record)
    # Facturae / FACe
    mcp.tool()(es__generate_facturae_xml)
    mcp.tool()(es__sign_facturae_xades)
    mcp.tool()(es__submit_to_face)
    mcp.tool()(es__get_face_invoice_status)
    mcp.tool()(es__validate_facturae_schema)
    # SII
    mcp.tool()(es__build_sii_invoice_record)
    mcp.tool()(es__submit_sii_batch)
    mcp.tool()(es__query_sii_status)
    mcp.tool()(es__generate_sii_correction)
    # Crea y Crece / B2B
    mcp.tool()(es__generate_b2b_einvoice_es)
    mcp.tool()(es__check_b2b_mandate_applicability)
    # Utilities
    mcp.tool()(es__detect_regional_regime)
    mcp.tool()(es__get_compliance_status)
    mcp.tool()(es__parse_aeat_response)


mcp = EInvoicingMCPServer(
    "mcp-facturacion-electronica-es",
    instructions=(
        "MCP server for Spanish electronic invoicing: VERI*FACTU (real-time AEAT "
        "reporting), Facturae/FACe (B2G), SII (Suministro Inmediato de Informacion), "
        "and Crea y Crece B2B (UBL 2.1 / Facturae). "
        "Call es__detect_regional_regime first to confirm the applicable regime "
        "before generating VERI*FACTU or SII records. TicketBAI (Basque Country) "
        "and NaTicket (Navarre) are out of scope for this package."
    ),
)
mcp.register_plugin(_register_es_tools, "es")


def main() -> None:
    """CLI entrypoint registered in pyproject.toml."""
    mcp.run()


if __name__ == "__main__":
    main()
