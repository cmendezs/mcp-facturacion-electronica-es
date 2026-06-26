"""MCP server entrypoint for mcp-facturacion-electronica-es."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from mcp_facturacion_electronica_es import __version__
from mcp_facturacion_electronica_es.tools.b2b import (
    TOOL_ES_CHECK_B2B_MANDATE_APPLICABILITY,
    TOOL_ES_GENERATE_B2B_EINVOICE_ES,
    handle_es_check_b2b_mandate_applicability,
    handle_es_generate_b2b_einvoice_es,
)
from mcp_facturacion_electronica_es.tools.facturae import (
    TOOL_ES_GENERATE_FACTURAE_XML,
    TOOL_ES_GET_FACE_INVOICE_STATUS,
    TOOL_ES_SIGN_FACTURAE_XADES,
    TOOL_ES_SUBMIT_TO_FACE,
    TOOL_ES_VALIDATE_FACTURAE_SCHEMA,
    handle_es_generate_facturae_xml,
    handle_es_get_face_invoice_status,
    handle_es_sign_facturae_xades,
    handle_es_submit_to_face,
    handle_es_validate_facturae_schema,
)
from mcp_facturacion_electronica_es.tools.sii import (
    TOOL_ES_BUILD_SII_INVOICE_RECORD,
    TOOL_ES_GENERATE_SII_CORRECTION,
    TOOL_ES_QUERY_SII_STATUS,
    TOOL_ES_SUBMIT_SII_BATCH,
    handle_es_build_sii_invoice_record,
    handle_es_generate_sii_correction,
    handle_es_query_sii_status,
    handle_es_submit_sii_batch,
)
from mcp_facturacion_electronica_es.tools.utils import (
    TOOL_ES_DETECT_REGIONAL_REGIME,
    TOOL_ES_GET_COMPLIANCE_STATUS,
    TOOL_ES_PARSE_AEAT_RESPONSE,
    handle_es_detect_regional_regime,
    handle_es_get_compliance_status,
    handle_es_parse_aeat_response,
)
from mcp_facturacion_electronica_es.tools.verifactu import (
    TOOL_ES_CANCEL_VERIFACTU_RECORD,
    TOOL_ES_GENERATE_QR_VERIFACTU,
    TOOL_ES_GENERATE_VERIFACTU_RECORD,
    TOOL_ES_SUBMIT_VERIFACTU_TO_AEAT,
    TOOL_ES_VALIDATE_VERIFACTU_RECORD,
    handle_es_cancel_verifactu_record,
    handle_es_generate_qr_verifactu,
    handle_es_generate_verifactu_record,
    handle_es_submit_verifactu_to_aeat,
    handle_es_validate_verifactu_record,
)

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)

_ALL_TOOLS: list[types.Tool] = [
    # VERI*FACTU
    TOOL_ES_GENERATE_VERIFACTU_RECORD,
    TOOL_ES_VALIDATE_VERIFACTU_RECORD,
    TOOL_ES_SUBMIT_VERIFACTU_TO_AEAT,
    TOOL_ES_GENERATE_QR_VERIFACTU,
    TOOL_ES_CANCEL_VERIFACTU_RECORD,
    # Facturae / FACe
    TOOL_ES_GENERATE_FACTURAE_XML,
    TOOL_ES_SIGN_FACTURAE_XADES,
    TOOL_ES_SUBMIT_TO_FACE,
    TOOL_ES_GET_FACE_INVOICE_STATUS,
    TOOL_ES_VALIDATE_FACTURAE_SCHEMA,
    # SII
    TOOL_ES_BUILD_SII_INVOICE_RECORD,
    TOOL_ES_SUBMIT_SII_BATCH,
    TOOL_ES_QUERY_SII_STATUS,
    TOOL_ES_GENERATE_SII_CORRECTION,
    # Crea y Crece / B2B
    TOOL_ES_GENERATE_B2B_EINVOICE_ES,
    TOOL_ES_CHECK_B2B_MANDATE_APPLICABILITY,
    # Utilities
    TOOL_ES_DETECT_REGIONAL_REGIME,
    TOOL_ES_GET_COMPLIANCE_STATUS,
    TOOL_ES_PARSE_AEAT_RESPONSE,
]

_TOOL_HANDLERS: dict[str, Any] = {
    # VERI*FACTU
    "es__generate_verifactu_record": handle_es_generate_verifactu_record,
    "es__validate_verifactu_record": handle_es_validate_verifactu_record,
    "es__submit_verifactu_to_aeat": handle_es_submit_verifactu_to_aeat,
    "es__generate_qr_verifactu": handle_es_generate_qr_verifactu,
    "es__cancel_verifactu_record": handle_es_cancel_verifactu_record,
    # Facturae / FACe
    "es__generate_facturae_xml": handle_es_generate_facturae_xml,
    "es__sign_facturae_xades": handle_es_sign_facturae_xades,
    "es__submit_to_face": handle_es_submit_to_face,
    "es__get_face_invoice_status": handle_es_get_face_invoice_status,
    "es__validate_facturae_schema": handle_es_validate_facturae_schema,
    # SII
    "es__build_sii_invoice_record": handle_es_build_sii_invoice_record,
    "es__submit_sii_batch": handle_es_submit_sii_batch,
    "es__query_sii_status": handle_es_query_sii_status,
    "es__generate_sii_correction": handle_es_generate_sii_correction,
    # Crea y Crece / B2B
    "es__generate_b2b_einvoice_es": handle_es_generate_b2b_einvoice_es,
    "es__check_b2b_mandate_applicability": handle_es_check_b2b_mandate_applicability,
    # Utilities
    "es__detect_regional_regime": handle_es_detect_regional_regime,
    "es__get_compliance_status": handle_es_get_compliance_status,
    "es__parse_aeat_response": handle_es_parse_aeat_response,
}


def _build_server() -> Server:
    """Instantiate and wire the MCP server."""
    server = Server("mcp-facturacion-electronica-es")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return _ALL_TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        handler = _TOOL_HANDLERS.get(name)
        if handler is None:
            raise ValueError(f"Unknown tool: {name!r}")
        # ES-SH-4: redact credential fields before logging to prevent plaintext password leak
        _REDACTED_KEYS = frozenset(
            {
                "cert_password",
                "certificate_password",
                "client_secret",
                "face_client_secret",
                "password",
                "token",
            }
        )
        safe_args = {k: "***" if k in _REDACTED_KEYS else v for k, v in arguments.items()}
        logger.debug("Dispatching tool %r with args %r", name, safe_args)
        return await handler(arguments)

    return server


async def _run() -> None:
    server = _build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mcp-facturacion-electronica-es",
                server_version=__version__,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main() -> None:
    """CLI entrypoint registered in pyproject.toml."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
