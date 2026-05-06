"""MCP tools: TicketBAI — generación XML, envío provincial y validación de esquema.

TicketBAI (País Vasco):
    Álava (Araba):   XSD v1.2 — https://batuz.eus/es/documentacion-tecnica
    Gipuzkoa:        XSD v1.2 — https://www.gipuzkoa.eus/ticketbai
    Bizkaia:         XSD v2.1 — https://www.bizkaia.eus/ticketbai

IMPORTANT: The three provincial XSDs are NOT interchangeable. Do not cross-validate
between provinces. Each province has its own software certification process and
submission endpoint.

[NEED: download the three provincial XSDs into specs/ticketbai/{araba,gipuzkoa,bizkaia}/]
[NEED: promote XAdES-EPES signature to mcp-einvoicing-core (score 3/3, also needed here)]
[NEED: verify current endpoint URLs for each province's sandbox environment]
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

TOOL_ES_GENERATE_TICKETBAI_XML = types.Tool(
    name="es__generate_ticketbai_xml",
    description=(
        "Genera una factura XML TicketBAI con firma XAdES y cadena HuellaTBAI. "
        "Selecciona automáticamente el XSD provincial: Álava v1.2, Gipuzkoa v1.2, Bizkaia v2.1. "
        "Los XSDs provinciales NO son intercambiables. "
        "[PENDIENTE DE IMPLEMENTACION]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "invoice": {
                "type": "object",
                "description": "Datos de la factura según el modelo de core.",
            },
            "province": {
                "type": "string",
                "enum": ["araba", "gipuzkoa", "bizkaia"],
                "description": "Provincia vasca que determina el XSD y endpoint.",
            },
            "previous_hash": {
                "type": "string",
                "description": "HuellaTBAI del registro precedente (null = primero en cadena).",
            },
            "software_license": {
                "type": "string",
                "description": "Clave de licencia del software TicketBAI certificado.",
            },
            "cert_path": {
                "type": "string",
                "description": "Ruta del certificado de firma PKCS#12.",
            },
            "cert_password": {
                "type": "string",
                "description": "Contraseña del certificado.",
            },
        },
        "required": ["invoice", "province", "software_license", "cert_path", "cert_password"],
    },
)

TOOL_ES_SUBMIT_TICKETBAI = types.Tool(
    name="es__submit_ticketbai",
    description=(
        "Envía un registro TicketBAI XML a la autoridad provincial vasca correspondiente. "
        "El endpoint se enruta automáticamente: Álava (batuz.eus), "
        "Gipuzkoa (tbai.egoitza.gipuzkoa.eus), Bizkaia (www.bizkaia.eus/ogasun). "
        "[PENDIENTE DE IMPLEMENTACION]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "xml": {
                "type": "string",
                "description": "XML TicketBAI firmado.",
            },
            "province": {
                "type": "string",
                "enum": ["araba", "gipuzkoa", "bizkaia"],
                "description": "Provincia vasca destinataria.",
            },
            "nif": {
                "type": "string",
                "description": "NIF del remitente.",
            },
        },
        "required": ["xml", "province", "nif"],
    },
)

TOOL_ES_VALIDATE_TICKETBAI_SCHEMA = types.Tool(
    name="es__validate_ticketbai_schema",
    description=(
        "Valida un documento XML TicketBAI contra el XSD correcto para la provincia indicada. "
        "Los esquemas NO son intercambiables entre provincias. "
        "[PENDIENTE DE IMPLEMENTACION]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "xml": {
                "type": "string",
                "description": "XML TicketBAI a validar.",
            },
            "province": {
                "type": "string",
                "enum": ["araba", "gipuzkoa", "bizkaia"],
                "description": "Provincia que determina el XSD a usar.",
            },
        },
        "required": ["xml", "province"],
    },
)

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

_NOT_IMPLEMENTED = (
    "[NEED: implement] Esta herramienta está especificada pero no implementada aún. "
    "Consulte el backlog de implementación en el README."
)


async def handle_es_generate_ticketbai_xml(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__generate_ticketbai_xml called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]


async def handle_es_submit_ticketbai(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__submit_ticketbai called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]


async def handle_es_validate_ticketbai_schema(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__validate_ticketbai_schema called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]
