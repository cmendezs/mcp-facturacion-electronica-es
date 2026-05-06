"""MCP tools: Facturae / FACe — generación XML, firma XAdES, envío y consulta.

Facturae 3.2.2:  https://www.facturae.gob.es/formato/Paginas/version-3-2.aspx
FACe REST API:   https://face.gob.es/es/facturas/api-face
XAdES-EPES:      ETSI EN 319 132-1

[NEED: download Facturae 3.2.2 XSD from facturae.gob.es into specs/]
[NEED: promote XAdES-EPES signature to mcp-einvoicing-core (CONFIRMED GAP, score 3/3)]
[NEED: promote sandbox/production URL router to mcp-einvoicing-core (score 3/3)]
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

TOOL_ES_GENERATE_FACTURAE_XML = types.Tool(
    name="es__generate_facturae_xml",
    description=(
        "Genera una factura XML conforme a Facturae 3.2.2 para envío B2G al portal FACe. "
        "Utiliza InvoiceDocument de mcp-einvoicing-core. "
        "[PENDIENTE DE IMPLEMENTACION]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "invoice": {
                "type": "object",
                "description": "Datos de la factura según el modelo de core.",
            },
            "schema_version": {
                "type": "string",
                "description": "Versión del esquema Facturae (por defecto: '3.2.2').",
                "default": "3.2.2",
            },
        },
        "required": ["invoice"],
    },
)

TOOL_ES_SIGN_FACTURAE_XADES = types.Tool(
    name="es__sign_facturae_xades",
    description=(
        "Aplica una firma digital XAdES-EPES (ETSI EN 319 132-1) a un documento Facturae XML. "
        "Candidato a promoción a mcp-einvoicing-core (puntuación 3/3). "
        "[PENDIENTE DE IMPLEMENTACION — bloqueado en gap XAdES de core]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "xml": {
                "type": "string",
                "description": "XML Facturae sin firmar.",
            },
            "cert_path": {
                "type": "string",
                "description": "Ruta al certificado PKCS#12 (.p12 / .pfx).",
            },
            "cert_password": {
                "type": "string",
                "description": "Contraseña del certificado.",
            },
            "signature_policy_id": {
                "type": "string",
                "description": "OID de la política de firma (por defecto: estándar Facturae).",
            },
        },
        "required": ["xml", "cert_path", "cert_password"],
    },
)

TOOL_ES_SUBMIT_TO_FACE = types.Tool(
    name="es__submit_to_face",
    description=(
        "Envía un XML Facturae firmado con XAdES a FACe (Punto General de Entrada de Facturas "
        "Electrónicas) a través de la API REST B2B de FACe v2. Requiere OAuth2 "
        "(FACE_CLIENT_ID / FACE_CLIENT_SECRET). "
        "[PENDIENTE DE IMPLEMENTACION]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "xml": {
                "type": "string",
                "description": "XML Facturae con firma XAdES.",
            },
            "administrative_unit": {
                "type": "string",
                "description": "Código UnidadTramitadora de FACe.",
            },
            "accounting_office": {
                "type": "string",
                "description": "Código OficinasContables de FACe.",
            },
            "management_body": {
                "type": "string",
                "description": "Código OrganoGestor de FACe.",
            },
        },
        "required": ["xml", "administrative_unit", "accounting_office", "management_body"],
    },
)

TOOL_ES_GET_FACE_INVOICE_STATUS = types.Tool(
    name="es__get_face_invoice_status",
    description=(
        "Consulta el estado de tramitación de una factura en FACe. Devuelve los códigos "
        "estándar: 1200 (Registrada), 2400 (Reconocida), 3100 (Rechazada), 4100 (Pagada). "
        "[PENDIENTE DE IMPLEMENTACION]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "invoice_id": {
                "type": "string",
                "description": "Número de registro FACe.",
            },
        },
        "required": ["invoice_id"],
    },
)

TOOL_ES_VALIDATE_FACTURAE_SCHEMA = types.Tool(
    name="es__validate_facturae_schema",
    description=(
        "Valida un XML Facturae contra el XSD oficial de Facturae 3.2.2 mediante lxml. "
        "Devuelve errores estructurados con ubicaciones XPath. "
        "[PENDIENTE DE IMPLEMENTACION]"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "xml": {
                "type": "string",
                "description": "XML Facturae a validar.",
            },
            "schema_version": {
                "type": "string",
                "description": "Versión del esquema (por defecto: '3.2.2').",
                "default": "3.2.2",
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


async def handle_es_generate_facturae_xml(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__generate_facturae_xml called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]


async def handle_es_sign_facturae_xades(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__sign_facturae_xades called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]


async def handle_es_submit_to_face(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__submit_to_face called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]


async def handle_es_get_face_invoice_status(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__get_face_invoice_status called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]


async def handle_es_validate_facturae_schema(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    logger.debug("es__validate_facturae_schema called with %r", arguments)
    return [types.TextContent(type="text", text=json.dumps({"error": _NOT_IMPLEMENTED}))]
