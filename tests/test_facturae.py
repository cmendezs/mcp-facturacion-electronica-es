"""Tests for Facturae tools: XML generation, signing (cert-gated), validation."""

from __future__ import annotations

import json

import pytest
from lxml import etree

from mcp_facturacion_electronica_es.tools.facturae import build_facturae_xml

_FACTURAE_NS = "http://www.facturae.gob.es/formato/Version3.2.2/Facturae32.xsd"


# ---------------------------------------------------------------------------
# XML builder (no network, no certificate)
# ---------------------------------------------------------------------------


def test_build_facturae_xml_structure(minimal_invoice) -> None:
    xml_bytes = build_facturae_xml(minimal_invoice)
    root = etree.fromstring(xml_bytes)

    # Root element must be Facturae in the correct namespace
    assert root.tag == f"{{{_FACTURAE_NS}}}Facturae"

    def _one(tag: str) -> str | None:
        found = root.find(f".//{{{_FACTURAE_NS}}}{tag}")
        return found.text if found is not None else None

    assert _one("SchemaVersion") == "3.2.2"
    assert _one("InvoiceNumber") == "2025-0001"
    assert _one("IssueDate") == "2025-03-15"
    assert _one("InvoiceCurrencyCode") == "EUR"


def test_build_facturae_xml_seller_buyer(minimal_invoice) -> None:
    xml_bytes = build_facturae_xml(minimal_invoice)
    root = etree.fromstring(xml_bytes)

    seller = root.find(f".//{{{_FACTURAE_NS}}}SellerParty")
    buyer = root.find(f".//{{{_FACTURAE_NS}}}BuyerParty")
    assert seller is not None
    assert buyer is not None

    seller_nif = seller.find(f".//{{{_FACTURAE_NS}}}TaxIdentificationNumber")
    assert seller_nif is not None
    assert seller_nif.text == "B12345678"


def test_build_facturae_xml_vat(minimal_invoice) -> None:
    xml_bytes = build_facturae_xml(minimal_invoice)
    root = etree.fromstring(xml_bytes)

    tax_rate = root.find(f".//{{{_FACTURAE_NS}}}TaxRate")
    assert tax_rate is not None
    assert tax_rate.text == "21.00"

    grand_total = root.find(f".//{{{_FACTURAE_NS}}}InvoiceTotal")
    assert grand_total is not None
    assert grand_total.text == "1210.00"


def test_build_facturae_xml_is_valid_xml(minimal_invoice) -> None:
    xml_bytes = build_facturae_xml(minimal_invoice)
    # Must parse without error
    root = etree.fromstring(xml_bytes)
    assert root is not None


# ---------------------------------------------------------------------------
# Tool handler integration (no network, no certificate)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_generate_facturae_xml(minimal_invoice) -> None:
    from mcp_facturacion_electronica_es.tools.facturae import handle_es_generate_facturae_xml

    result = await handle_es_generate_facturae_xml({"invoice": minimal_invoice.model_dump()})
    data = json.loads(result[0].text)
    assert "error" not in data
    assert "xml" in data
    assert "3.2.2" in data["xml"]
    assert data["schema_version"] == "3.2.2"
    assert data["invoice_number"] == "2025-0001"


@pytest.mark.asyncio
async def test_handle_generate_facturae_xml_missing_invoice() -> None:
    from mcp_facturacion_electronica_es.tools.facturae import handle_es_generate_facturae_xml

    result = await handle_es_generate_facturae_xml({})
    data = json.loads(result[0].text)
    assert "error" in data


@pytest.mark.asyncio
async def test_handle_validate_facturae_schema_valid(minimal_facturae_xml) -> None:
    from mcp_facturacion_electronica_es.tools.facturae import handle_es_validate_facturae_schema

    result = await handle_es_validate_facturae_schema({"xml": minimal_facturae_xml})
    data = json.loads(result[0].text)
    assert data["valid"] is True
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_handle_validate_facturae_schema_missing_elements() -> None:
    from mcp_facturacion_electronica_es.tools.facturae import handle_es_validate_facturae_schema

    minimal_xml = '<?xml version="1.0" encoding="UTF-8"?><Facturae xmlns="http://www.facturae.gob.es/formato/Version3.2.2/Facturae32.xsd"><FileHeader/></Facturae>'
    result = await handle_es_validate_facturae_schema({"xml": minimal_xml})
    data = json.loads(result[0].text)
    # Missing required elements — must flag errors
    assert data["valid"] is False


@pytest.mark.asyncio
async def test_handle_validate_facturae_schema_invalid_xml() -> None:
    from mcp_facturacion_electronica_es.tools.facturae import handle_es_validate_facturae_schema

    result = await handle_es_validate_facturae_schema({"xml": "<bad xml <<<"})
    data = json.loads(result[0].text)
    assert data["valid"] is False
    assert len(data["errors"]) > 0
