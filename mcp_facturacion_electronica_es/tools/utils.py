"""MCP tools: utilidades — detección de régimen, estado de cumplimiento y análisis AEAT.

Province routing (INE codes):
    Álava:     01  (TicketBAI)
    Gipuzkoa:  20  (TicketBAI)
    Bizkaia:   48  (TicketBAI)
    Navarra:   31  (NaTicket)
    All others:    VERIFACTU (or VERIFACTU+SII if enrolled)

[NEED: promote es__detect_regional_regime to mcp-einvoicing-core once use-case
       confirmed across >=3 packages (currently ES-only, score 1/3)]
[NEED: promote mandate deadline registry to mcp-einvoicing-core (score 2/3, FR+ES)]
[NEED: promote AEAT response parser to mcp-einvoicing-core (score 2/3, FR+ES)]
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

TOOL_ES_DETECT_REGIONAL_REGIME = types.Tool(
    name="es__detect_regional_regime",
    description=(
        "Detecta el régimen de facturación electrónica aplicable a partir del código de provincia "
        "INE de dos dígitos. Devuelve VERIFACTU, TICKETBAI, NATICKET o VERIFACTU+SII. "
        "Provincias vascas: 01 Álava, 20 Gipuzkoa, 48 Bizkaia. Navarra: 31. "
        "Usar siempre antes de llamar a cualquier otra herramienta de este servidor. "
        "[PENDIENTE DE IMPLEMENTACION]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "province_code": {
                "type": "string",
                "description": "Código de provincia INE de dos dígitos (p. ej., '28', '01', '31').",
                "pattern": "^[0-9]{2}$",
            },
            "enrolled_in_sii": {
                "type": "boolean",
                "description": "Inscripción en el SII (por defecto: false).",
                "default": False,
            },
        },
        "required": ["province_code"],
    },
)

TOOL_ES_GET_COMPLIANCE_STATUS = types.Tool(
    name="es__get_compliance_status",
    description=(
        "Devuelve los plazos de mandato vigentes y el sistema operativo para un perfil de "
        "empresa. Refleja el RD-ley 15/2025 — sujeto a cambios por legislación posterior. "
        "Candidato a promoción a mcp-einvoicing-core (registro genérico de plazos). "
        "[PENDIENTE DE IMPLEMENTACION]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "entity_type": {
                "type": "string",
                "enum": ["IS", "IRPF"],
                "description": "Tipo de obligado tributario.",
            },
            "province_code": {
                "type": "string",
                "description": "Código de provincia INE de dos dígitos.",
                "pattern": "^[0-9]{2}$",
            },
            "annual_turnover_eur": {
                "type": "number",
                "description": "Volumen anual de operaciones IVA en EUR (para verificar umbral SII > EUR 6M).",
            },
            "enrolled_in_sii": {
                "type": "boolean",
                "description": "Inscripción en el SII.",
                "default": False,
            },
        },
        "required": ["entity_type", "province_code"],
    },
)

TOOL_ES_PARSE_AEAT_RESPONSE = types.Tool(
    name="es__parse_aeat_response",
    description=(
        "Analiza y normaliza una respuesta XML de la AEAT (VERI*FACTU o SII) a JSON "
        "estructurado. Extrae EstadoEnvio (Correcto / AceptadoConErrores / Incorrecto), "
        "CSV (código seguro de verificación) y detalle de errores. "
        "Candidato a promoción a mcp-einvoicing-core (puntuación 2/3). "
        "[PENDIENTE DE IMPLEMENTACION]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "xml": {
                "type": "string",
                "description": "Respuesta XML de la AEAT en crudo.",
            },
            "response_type": {
                "type": "string",
                "enum": ["verifactu", "sii"],
                "description": "Tipo de respuesta a analizar (por defecto: 'verifactu').",
                "default": "verifactu",
            },
        },
        "required": ["xml"],
    },
)

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

_NOT_IMPLEMENTED = (
    "[NEED: implement] Esta herramienta está especificada pero no implementada aún. "
    "Consulte el backlog de implementación en el README."
)


async def handle_es_detect_regional_regime(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__detect_regional_regime called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]


async def handle_es_get_compliance_status(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__get_compliance_status called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]


async def handle_es_parse_aeat_response(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__parse_aeat_response called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]
