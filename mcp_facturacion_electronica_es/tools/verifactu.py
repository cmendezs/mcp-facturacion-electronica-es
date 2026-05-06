"""MCP tools: VERI*FACTU — registro, validación, envío, QR y anulación.

VERI*FACTU (Real Decreto 1007/2023, Orden HAC/1177/2024):
    XSD v1.0: BOE-A-2024-22138
    Sandbox:  https://prewww2.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/...
    Production: https://www2.agenciatributaria.gob.es/...

[NEED: download and validate XSD v1.0 from BOE-A-2024-22138 before implementing]
[NEED: AuthMode.MTLS — blocked on mcp-einvoicing-core gap (CONFIRMED GAP)]
[NEED: promote SHA-256 Huella chain logic to mcp-einvoicing-core (score 2/3)]
[NEED: promote QR generation to mcp-einvoicing-core (score 3/3)]
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

TOOL_ES_GENERATE_VERIFACTU_RECORD = types.Tool(
    name="es__generate_verifactu_record",
    description=(
        "Genera un registro de factura VERI*FACTU (Orden HAC/1177/2024) con encadenamiento "
        "SHA-256 Huella. El campo previous_hash debe ser la Huella del registro anterior en "
        "la cadena (null para el primero). El invoice_type debe corresponder al tipo de "
        "operación: F1 factura estándar, R1-R5 rectificativas. "
        "[PENDIENTE DE IMPLEMENTACION]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "invoice": {
                "type": "object",
                "description": "Datos de la factura (vendedor, comprador, líneas, IVA).",
            },
            "previous_hash": {
                "type": "string",
                "description": "SHA-256 Huella del registro precedente (null = primero en cadena).",
            },
            "software_id": {
                "type": "string",
                "description": "IDSistemaInformatico del software certificado.",
            },
            "software_nif": {
                "type": "string",
                "description": "NIF del fabricante del software.",
            },
            "invoice_type": {
                "type": "string",
                "enum": ["F1", "F2", "F3", "R1", "R2", "R3", "R4", "R5"],
                "description": "TipoFactura según HAC/1177/2024.",
            },
        },
        "required": ["invoice", "software_id", "software_nif", "invoice_type"],
    },
)

TOOL_ES_VALIDATE_VERIFACTU_RECORD = types.Tool(
    name="es__validate_verifactu_record",
    description=(
        "Valida un registro VERI*FACTU XML contra el XSD oficial publicado con la Orden "
        "HAC/1177/2024 (BOE-A-2024-22138). Devuelve errores de validación con ubicaciones. "
        "[PENDIENTE DE IMPLEMENTACION]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "xml": {
                "type": "string",
                "description": "Registro VERI*FACTU XML en crudo.",
            },
            "schema_version": {
                "type": "string",
                "description": "Versión del esquema XSD (por defecto: '1.0').",
                "default": "1.0",
            },
        },
        "required": ["xml"],
    },
)

TOOL_ES_SUBMIT_VERIFACTU_TO_AEAT = types.Tool(
    name="es__submit_verifactu_to_aeat",
    description=(
        "Envía un registro VERI*FACTU firmado al endpoint en tiempo real de la AEAT mediante "
        "MTLS (certificado FNMT-RCM Clase 1). Requiere AEAT_ENV, AEAT_CERTIFICATE_PATH y "
        "AEAT_CERTIFICATE_PASSWORD. "
        "[PENDIENTE DE IMPLEMENTACION — bloqueado por gap AuthMode.MTLS en mcp-einvoicing-core]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "xml": {
                "type": "string",
                "description": "Registro VERI*FACTU XML firmado.",
            },
            "nif": {
                "type": "string",
                "description": "NIF del remitente.",
            },
        },
        "required": ["xml", "nif"],
    },
)

TOOL_ES_GENERATE_QR_VERIFACTU = types.Tool(
    name="es__generate_qr_verifactu",
    description=(
        "Genera el código QR obligatorio VERI*FACTU (HAC/1177/2024 Art. 10) como PNG en "
        "base64. Codifica la URL de verificación de la AEAT con el texto reglamentario. "
        "Candidato a promoción a mcp-einvoicing-core (puntuación 3/3). "
        "[PENDIENTE DE IMPLEMENTACION]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "nif": {
                "type": "string",
                "description": "NIF del emisor.",
            },
            "invoice_number": {
                "type": "string",
                "description": "NumSerieFactura.",
            },
            "invoice_date": {
                "type": "string",
                "description": "FechaExpedicionFactura en formato YYYY-MM-DD.",
            },
            "total_amount": {
                "type": "number",
                "description": "Total de la factura con IVA incluido.",
            },
            "size_px": {
                "type": "integer",
                "description": "Tamaño del QR en píxeles (por defecto: 200).",
                "default": 200,
            },
        },
        "required": ["nif", "invoice_number", "invoice_date", "total_amount"],
    },
)

TOOL_ES_CANCEL_VERIFACTU_RECORD = types.Tool(
    name="es__cancel_verifactu_record",
    description=(
        "Genera un registro de anulación VERI*FACTU (IndicadorAnulacion=S, TipoHuella=01) "
        "encadenado a la secuencia de huellas actual. "
        "[PENDIENTE DE IMPLEMENTACION]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "original_invoice_number": {
                "type": "string",
                "description": "NumSerieFactura a anular.",
            },
            "original_invoice_date": {
                "type": "string",
                "description": "FechaExpedicionFactura (YYYY-MM-DD).",
            },
            "issuer_nif": {
                "type": "string",
                "description": "NIF del emisor.",
            },
            "previous_hash": {
                "type": "string",
                "description": "Huella del último registro en la cadena.",
            },
        },
        "required": [
            "original_invoice_number",
            "original_invoice_date",
            "issuer_nif",
            "previous_hash",
        ],
    },
)

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

_NOT_IMPLEMENTED = (
    "[NEED: implement] Esta herramienta está especificada pero no implementada aún. "
    "Consulte el backlog de implementación en el README."
)


async def handle_es_generate_verifactu_record(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__generate_verifactu_record called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]


async def handle_es_validate_verifactu_record(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__validate_verifactu_record called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]


async def handle_es_submit_verifactu_to_aeat(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__submit_verifactu_to_aeat called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]


async def handle_es_generate_qr_verifactu(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__generate_qr_verifactu called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]


async def handle_es_cancel_verifactu_record(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__cancel_verifactu_record called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]
