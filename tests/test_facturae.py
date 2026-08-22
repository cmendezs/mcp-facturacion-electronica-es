"""Tests for Facturae tools: XML generation, signing (cert-gated), validation."""

from __future__ import annotations

import json

import pytest
from lxml import etree

from mcp_facturacion_electronica_es.tools.facturae import build_facturae_xml

# ES-SC-1: correct namespace confirmed from specs/facturae/xsd/Facturaev3_2_2.xml targetNamespace
_FACTURAE_NS = "http://www.facturae.gob.es/formato/Versiones/Facturaev3_2_2.xml"


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
    assert seller_nif.text == "B12345674"


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
    from mcp_facturacion_electronica_es.tools.facturae import es__generate_facturae_xml

    data = await es__generate_facturae_xml(invoice=minimal_invoice.model_dump())
    assert "error" not in data
    assert "xml" in data
    assert "3.2.2" in data["xml"]
    assert data["schema_version"] == "3.2.2"
    assert data["invoice_number"] == "2025-0001"


@pytest.mark.asyncio
async def test_handle_generate_facturae_xml_missing_invoice() -> None:
    from mcp_facturacion_electronica_es.tools.facturae import es__generate_facturae_xml

    data = await es__generate_facturae_xml(invoice={})
    assert "error" in data


@pytest.mark.asyncio
async def test_handle_validate_facturae_schema_valid(minimal_facturae_xml) -> None:
    from mcp_facturacion_electronica_es.tools.facturae import es__validate_facturae_schema

    data = await es__validate_facturae_schema(xml=minimal_facturae_xml)
    assert data["valid"] is True
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_handle_validate_facturae_schema_missing_elements() -> None:
    from mcp_facturacion_electronica_es.tools.facturae import es__validate_facturae_schema

    minimal_xml = '<?xml version="1.0" encoding="UTF-8"?><Facturae xmlns="http://www.facturae.gob.es/formato/Versiones/Facturaev3_2_2.xml"><FileHeader/></Facturae>'
    data = await es__validate_facturae_schema(xml=minimal_xml)
    # Missing required elements — must flag errors
    assert data["valid"] is False


@pytest.mark.asyncio
async def test_handle_validate_facturae_schema_invalid_xml() -> None:
    from mcp_facturacion_electronica_es.tools.facturae import es__validate_facturae_schema

    data = await es__validate_facturae_schema(xml="<bad xml <<<")
    assert data["valid"] is False
    assert len(data["errors"]) > 0


# ---------------------------------------------------------------------------
# Batch 2: Decimal precision in line tax amounts
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Batch 3: InvoiceIssuerType, IRPF withholding, AccountToBeCredited, policy hash
# ---------------------------------------------------------------------------


def test_facturae_invoice_issuer_type_em(minimal_invoice) -> None:
    xml_bytes = build_facturae_xml(minimal_invoice, invoice_issuer_type="EM")
    root = etree.fromstring(xml_bytes)
    ns = {"fe": _FACTURAE_NS}
    iit = root.find(".//fe:InvoiceIssuerType", ns)
    assert iit is not None
    assert iit.text == "EM"


def test_facturae_invoice_issuer_type_te(minimal_invoice) -> None:
    xml_bytes = build_facturae_xml(minimal_invoice, invoice_issuer_type="TE")
    root = etree.fromstring(xml_bytes)
    ns = {"fe": _FACTURAE_NS}
    iit = root.find(".//fe:InvoiceIssuerType", ns)
    assert iit is not None
    assert iit.text == "TE"


def test_facturae_irpf_withholding(minimal_invoice) -> None:
    from decimal import Decimal as D

    xml_bytes = build_facturae_xml(minimal_invoice, irpf_amount=D("150.00"))
    root = etree.fromstring(xml_bytes)
    ns = {"fe": _FACTURAE_NS}
    withheld = root.find(".//fe:TotalTaxesWithheld", ns)
    assert withheld is not None
    assert withheld.text == "150.00"
    invoice_total = root.find(".//fe:InvoiceTotal", ns)
    assert invoice_total is not None
    assert D(invoice_total.text) == D("1060.00")


def test_facturae_resolution_reference(minimal_invoice) -> None:
    xml_bytes = build_facturae_xml(
        minimal_invoice,
        resolution_reference="RES-2025-001",
        receiver_transaction_reference="RTR-2025-001",
    )
    root = etree.fromstring(xml_bytes)
    ns = {"fe": _FACTURAE_NS}
    rr = root.find(".//fe:ResolutionReference", ns)
    assert rr is not None
    assert rr.text == "RES-2025-001"
    rtr = root.find(".//fe:ReceiverTransactionReference", ns)
    assert rtr is not None
    assert rtr.text == "RTR-2025-001"


def test_facturae_policy_hash_set() -> None:
    from mcp_facturacion_electronica_es._helpers import (
        FACTURAE_POLICY_HASH,
        FACTURAE_POLICY_HASH_ALGORITHM,
    )

    assert FACTURAE_POLICY_HASH is not None
    assert len(FACTURAE_POLICY_HASH) > 0
    assert "sha1" in FACTURAE_POLICY_HASH_ALGORITHM


# ---------------------------------------------------------------------------
# ES-TL-9 / ES-TL-10 / ES-TL-11: tax type, Recargo de Equivalencia, IRPF
# ---------------------------------------------------------------------------


def test_facturae_tax_type_igic(minimal_invoice) -> None:
    xml_bytes = build_facturae_xml(minimal_invoice, tax_type="IGIC")
    root = etree.fromstring(xml_bytes)
    ns = {"fe": _FACTURAE_NS}
    codes = root.findall(".//fe:TaxTypeCode", ns)
    assert len(codes) >= 1
    assert all(c.text == "03" for c in codes)


def test_facturae_tax_type_ipsi(minimal_invoice) -> None:
    xml_bytes = build_facturae_xml(minimal_invoice, tax_type="IPSI")
    root = etree.fromstring(xml_bytes)
    ns = {"fe": _FACTURAE_NS}
    codes = root.findall(".//fe:TaxTypeCode", ns)
    assert all(c.text == "02" for c in codes)


def test_facturae_tax_type_default_iva(minimal_invoice) -> None:
    xml_bytes = build_facturae_xml(minimal_invoice)
    root = etree.fromstring(xml_bytes)
    ns = {"fe": _FACTURAE_NS}
    code = root.find(".//fe:TaxesOutputs/fe:Tax/fe:TaxTypeCode", ns)
    assert code is not None
    assert code.text == "01"


def test_facturae_recargo_equivalencia(minimal_invoice) -> None:
    from decimal import Decimal as D

    xml_bytes = build_facturae_xml(
        minimal_invoice, recargo_equivalencia_rate=D("5.2")
    )
    root = etree.fromstring(xml_bytes)
    ns = {"fe": _FACTURAE_NS}
    rate = root.find(".//fe:EquivalenceSurcharge", ns)
    amount = root.find(".//fe:EquivalenceSurchargeAmount/fe:TotalAmount", ns)
    assert rate is not None and rate.text == "5.20"
    assert amount is not None and amount.text == "52.00"
    total_tax_outputs = root.find(".//fe:TotalTaxOutputs", ns)
    assert total_tax_outputs.text == "262.00"
    invoice_total = root.find(".//fe:InvoiceTotal", ns)
    assert invoice_total.text == "1262.00"


def test_facturae_irpf_rate_taxes_withheld_block(minimal_invoice) -> None:
    from decimal import Decimal as D

    xml_bytes = build_facturae_xml(
        minimal_invoice, irpf_amount=D("150.00"), irpf_rate=D("15.00")
    )
    root = etree.fromstring(xml_bytes)
    ns = {"fe": _FACTURAE_NS}
    withheld = root.find(".//fe:TaxesWithheld/fe:Tax", ns)
    assert withheld is not None
    assert withheld.find("fe:TaxTypeCode", ns).text == "04"
    assert withheld.find("fe:TaxRate", ns).text == "15.00"
    assert withheld.find("fe:TaxableBase/fe:TotalAmount", ns).text == "1000.00"
    assert withheld.find("fe:TaxAmount/fe:TotalAmount", ns).text == "150.00"


def test_facturae_no_taxes_withheld_block_without_irpf(minimal_invoice) -> None:
    xml_bytes = build_facturae_xml(minimal_invoice)
    root = etree.fromstring(xml_bytes)
    ns = {"fe": _FACTURAE_NS}
    assert root.find(".//fe:TaxesWithheld", ns) is None


@pytest.mark.asyncio
async def test_facturae_igic_recargo_irpf_xsd_valid(minimal_invoice) -> None:
    """Combined IGIC + Recargo + IRPF output must still XSD-validate."""
    from decimal import Decimal as D

    from mcp_facturacion_electronica_es.tools.facturae import (
        es__validate_facturae_schema,
    )

    xml_bytes = build_facturae_xml(
        minimal_invoice,
        tax_type="IGIC",
        recargo_equivalencia_rate=D("5.2"),
        irpf_amount=D("150.00"),
        irpf_rate=D("15.00"),
    )
    data = await es__validate_facturae_schema(xml=xml_bytes.decode("utf-8"))
    assert data["valid"] is True, data["errors"]


def test_facturae_line_tax_decimal_precision(minimal_invoice) -> None:
    """Tax amount must use Decimal division, not float."""
    from decimal import Decimal as D

    from mcp_facturacion_electronica_es.tools.facturae import build_facturae_xml

    xml_bytes = build_facturae_xml(minimal_invoice)
    root = etree.fromstring(xml_bytes)
    ns = {"fe": _FACTURAE_NS}
    tax_amounts = root.findall(".//fe:InvoiceLine//fe:TaxAmount/fe:TotalAmount", ns)
    assert len(tax_amounts) >= 1
    for ta in tax_amounts:
        val = D(ta.text)
        assert val == val.quantize(D("0.01"))


# ---------------------------------------------------------------------------
# ES-LC-14: FACe JWS authentication, ES-SH-7: masked FACe responses
# ---------------------------------------------------------------------------


def test_build_face_client_missing_cert_path_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_facturacion_electronica_es.config import aeat_settings
    from mcp_facturacion_electronica_es.tools.facturae import _build_face_client

    monkeypatch.setattr(aeat_settings, "certificate_path", None)
    with pytest.raises(Exception, match="AEAT_CERTIFICATE_PATH"):
        _build_face_client("https://se-api-face.redsara.es")


def test_build_face_client_uses_jws_auth(p12_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import base64
    import hashlib

    from mcp_einvoicing_core.digital_signature import load_certificate_der
    from mcp_einvoicing_core.http_client import AuthMode

    from mcp_facturacion_electronica_es.config import aeat_settings
    from mcp_facturacion_electronica_es.tools.facturae import _build_face_client

    monkeypatch.setattr(aeat_settings, "certificate_path", str(p12_path))
    monkeypatch.setattr(aeat_settings, "certificate_password", "test")

    client = _build_face_client("https://se-api-face.redsara.es")
    assert client._auth_mode == AuthMode.JWS
    assert client._jws_config is not None
    assert client._jws_config.ttl_seconds == 300

    expected_username = hashlib.sha1(
        base64.b64encode(load_certificate_der(str(p12_path), "test"))
    ).hexdigest()
    assert client._jws_config.extra_claims["username"] == expected_username


def test_parse_face_response_masks_raw_body() -> None:
    from mcp_facturacion_electronica_es.tools.facturae import _parse_face_response

    class _FakeResponse:
        status_code = 201
        headers = {"content-type": "application/json"}

        def json(self):
            return {
                "codigo": "1200",
                "descripcion": "Registrada",
                "numeroRegistro": "REG-123",
                "internalSecret": "should-never-appear",
            }

    result = _parse_face_response(_FakeResponse())
    assert result == {
        "status_code": 201,
        "codigo": "1200",
        "descripcion": "Registrada",
        "numeroRegistro": "REG-123",
    }
    assert "internalSecret" not in result
    assert "internalSecret" not in json.dumps(result)


@pytest.mark.asyncio
async def test_handle_submit_to_face_masks_response(
    minimal_facturae_xml, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mcp_einvoicing_core.confirmation as confirmation_module

    from mcp_facturacion_electronica_es.tools import facturae as facturae_module

    monkeypatch.setattr(confirmation_module, "_HITL_DISABLED", True)

    class _FakeResponse:
        status_code = 201
        headers = {"content-type": "application/json"}

        def json(self):
            return {
                "codigo": "1200",
                "descripcion": "Registrada",
                "numeroRegistro": "REG-123",
                "secretToken": "should-never-leak",
            }

    class _FakeClient:
        async def _request(self, *args, **kwargs):
            return _FakeResponse()

    monkeypatch.setattr(facturae_module, "_build_face_client", lambda base_url: _FakeClient())

    data = await facturae_module.es__submit_to_face(
        xml=minimal_facturae_xml,
        administrative_unit="U001",
        accounting_office="O001",
        management_body="G001",
    )
    assert "error" not in data
    assert data["codigo"] == "1200"
    assert "secretToken" not in json.dumps(data)
