"""MCP tools: Crea y Crece / B2B — factura electrónica B2B y comprobación de mandato.

Ley 18/2022 'Crea y Crece':
    Mandates e-invoicing for all companies in B2B transactions.
    Format: UBL 2.1 or Facturae 3.2.2 (EN 16931 compliant).
    Implementing decree: PENDING as of 2026-05.

Mutual exclusion RD 254/2025:
    SII-enrolled taxpayers are exempt from VERI*FACTU.
    Call es__check_b2b_mandate_applicability before generating any records.

[NEED: confirm final format requirements once implementing decree is published]
[NEED: promote corrective invoice builder to mcp-einvoicing-core (score 3/3)]
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

TOOL_ES_GENERATE_B2B_EINVOICE_ES = types.Tool(
    name="es__generate_b2b_einvoice_es",
    description=(
        "Genera una factura B2B conforme a EN 16931 en formato UBL 2.1 o Facturae 3.2.2 "
        "según la Ley 18/2022 'Crea y Crece'. El formato definitivo queda pendiente del "
        "reglamento de desarrollo. "
        "[PENDIENTE DE IMPLEMENTACION — reglamento de desarrollo sin publicar]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "invoice": {
                "type": "object",
                "description": "Datos de la factura según el modelo de core.",
            },
            "format": {
                "type": "string",
                "enum": ["ubl", "facturae"],
                "description": "Formato de salida: 'ubl' (por defecto) o 'facturae'.",
                "default": "ubl",
            },
        },
        "required": ["invoice"],
    },
)

TOOL_ES_CHECK_B2B_MANDATE_APPLICABILITY = types.Tool(
    name="es__check_b2b_mandate_applicability",
    description=(
        "Determina el régimen de facturación electrónica aplicable (VERI*FACTU, SII, TicketBAI, "
        "NaTicket) a partir del volumen de operaciones, código de provincia y enrolamiento en SII. "
        "Aplica la lógica de exclusión mutua del Real Decreto 254/2025. "
        "Debe llamarse antes de generar cualquier registro. "
        "[PENDIENTE DE IMPLEMENTACION]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "annual_turnover_eur": {
                "type": "number",
                "description": "Volumen anual de operaciones IVA en EUR.",
            },
            "tax_address_province_code": {
                "type": "string",
                "description": "Código de provincia INE de dos dígitos (p. ej., '28' Madrid).",
            },
            "enrolled_in_sii": {
                "type": "boolean",
                "description": "Inscripción en el SII (por defecto: false).",
                "default": False,
            },
            "entity_type": {
                "type": "string",
                "enum": ["IS", "IRPF"],
                "description": "Tipo de obligado: 'IS' (Impuesto sobre Sociedades) o 'IRPF'.",
            },
        },
        "required": ["annual_turnover_eur", "tax_address_province_code"],
    },
)

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

_NOT_IMPLEMENTED = (
    "[NEED: implement] Esta herramienta está especificada pero no implementada aún. "
    "Consulte el backlog de implementación en el README."
)


async def handle_es_generate_b2b_einvoice_es(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__generate_b2b_einvoice_es called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]


async def handle_es_check_b2b_mandate_applicability(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__check_b2b_mandate_applicability called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]
