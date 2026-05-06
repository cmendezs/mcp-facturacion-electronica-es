"""MCP tools: SII (Suministro Inmediato de Información) — construcción, envío y consulta.

AEAT SII:
    Technical guide: v3.0 (April 2024) — https://www.agenciatributaria.es/SII
    Mandatory for turnover > EUR 6M, VAT groups, REDEME (RD 596/2016)
    Endpoint: SOAP/REST via MTLS

[NEED: AuthMode.MTLS — blocked on mcp-einvoicing-core gap (CONFIRMED GAP)]
[NEED: promote corrective invoice builder to mcp-einvoicing-core (score 3/3)]
[NEED: download AEAT SII XSD schemas into specs/sii/]
"""

from __future__ import annotations

import json
import logging
from typing import Any

import mcp.types as types

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOL_ES_BUILD_SII_INVOICE_RECORD = types.Tool(
    name="es__build_sii_invoice_record",
    description=(
        "Construye un registro XML AEAT SII (emisión FacturaExpedida o recepción "
        "FacturaRecibida) conforme a la guía técnica SII v3.0 (abril 2024). "
        "Soporta TipoComunicacion A0 (alta), A1 (modificación) y A4 (baja). "
        "[PENDIENTE DE IMPLEMENTACION]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "invoice": {
                "type": "object",
                "description": "Datos de la factura según el modelo de core.",
            },
            "record_type": {
                "type": "string",
                "enum": ["issued", "received"],
                "description": "Dirección del registro: 'issued' (expedida) o 'received' (recibida).",
            },
            "communication_type": {
                "type": "string",
                "enum": ["A0", "A1", "A4"],
                "description": "TipoComunicacion: A0 alta (por defecto), A1 modificación, A4 baja.",
                "default": "A0",
            },
        },
        "required": ["invoice", "record_type"],
    },
)

TOOL_ES_SUBMIT_SII_BATCH = types.Tool(
    name="es__submit_sii_batch",
    description=(
        "Envía un lote de facturas (máximo 10.000 registros) al endpoint SOAP SII de la AEAT. "
        "Requiere MTLS (AEAT_CERTIFICATE_PATH / AEAT_CERTIFICATE_PASSWORD). "
        "[PENDIENTE DE IMPLEMENTACION — bloqueado por gap AuthMode.MTLS en mcp-einvoicing-core]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "records": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Lista de cadenas XML de es__build_sii_invoice_record.",
            },
            "record_type": {
                "type": "string",
                "enum": ["issued", "received"],
                "description": "Dirección del lote.",
            },
            "fiscal_year": {
                "type": "integer",
                "description": "Ejercicio fiscal (YYYY).",
            },
        },
        "required": ["records", "record_type", "fiscal_year"],
    },
)

TOOL_ES_QUERY_SII_STATUS = types.Tool(
    name="es__query_sii_status",
    description=(
        "Consulta el estado de un lote SII enviado mediante ConsultaFactInformadasEmitidas "
        "o ConsultaFactInformadasRecibidas según el record_type. "
        "[PENDIENTE DE IMPLEMENTACION]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "batch_id": {
                "type": "string",
                "description": "Referencia del lote devuelta por es__submit_sii_batch.",
            },
            "record_type": {
                "type": "string",
                "enum": ["issued", "received"],
                "description": "Dirección del lote consultado.",
            },
        },
        "required": ["batch_id", "record_type"],
    },
)

TOOL_ES_GENERATE_SII_CORRECTION = types.Tool(
    name="es__generate_sii_correction",
    description=(
        "Genera un registro de modificación SII (A1) o baja (A4) que referencia la factura "
        "original mediante IDFactura. El constructor de facturas rectificativas es candidato "
        "a mcp-einvoicing-core (puntuación 3/3). "
        "[PENDIENTE DE IMPLEMENTACION]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "original_invoice": {
                "type": "object",
                "description": "Factura que se rectifica.",
            },
            "corrected_invoice": {
                "type": "object",
                "description": "Datos corregidos (null para A4 — baja).",
            },
            "correction_type": {
                "type": "string",
                "enum": ["A1", "A4"],
                "description": "Tipo de comunicación rectificativa.",
            },
            "record_type": {
                "type": "string",
                "enum": ["issued", "received"],
                "description": "Dirección del registro original.",
            },
        },
        "required": ["original_invoice", "correction_type", "record_type"],
    },
)

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

_NOT_IMPLEMENTED = (
    "[NEED: implement] Esta herramienta está especificada pero no implementada aún. "
    "Consulte el backlog de implementación en el README."
)


async def handle_es_build_sii_invoice_record(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__build_sii_invoice_record called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]


async def handle_es_submit_sii_batch(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__submit_sii_batch called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]


async def handle_es_query_sii_status(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__query_sii_status called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]


async def handle_es_generate_sii_correction(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__generate_sii_correction called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]
