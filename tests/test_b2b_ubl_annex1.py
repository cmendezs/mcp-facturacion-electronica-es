"""UBL output of the B2B generator against Annex I and the OASIS UBL 2.5 schema.

The UBL 2.5 XSDs are reference material under specs/ (not shipped in the wheel), so
the schema tests skip when a checkout without specs/ runs them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from mcp_facturacion_electronica_es.tools.b2b import (
    AEAT_B2B_PROFILE_ID,
    AEAT_CUSTOMIZATION_ID,
    build_ubl_invoice,
)

_SPECS = Path(__file__).resolve().parents[1] / "specs" / "crea-y-crece"
_UBL_INVOICE_XSD = (
    _SPECS / "schemas" / "PRE" / "xsd" / "ubl-2.5" / "maindoc" / "UBL-Invoice-2.5.xsd"
)
_AEAT_SAMPLE = _SPECS / "examples" / "factura.xml"

_NS = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "in": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
}

needs_ubl_xsd = pytest.mark.skipif(
    not _UBL_INVOICE_XSD.exists(), reason="UBL 2.5 XSDs not present under specs/"
)


@pytest.fixture(scope="module")
def ubl_schema() -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(_UBL_INVOICE_XSD)))


def _text(root: etree._Element, path: str) -> str | None:
    found = root.find(path, _NS)
    return found.text if found is not None else None


@needs_ubl_xsd
def test_generated_ubl_validates_against_ubl_2_5(minimal_invoice, ubl_schema) -> None:
    root = etree.fromstring(build_ubl_invoice(minimal_invoice))
    assert ubl_schema.validate(root), [e.message for e in ubl_schema.error_log]


@needs_ubl_xsd
def test_generated_copy_validates_against_ubl_2_5(minimal_invoice, ubl_schema) -> None:
    root = etree.fromstring(build_ubl_invoice(minimal_invoice, is_copy=True))
    assert ubl_schema.validate(root), [e.message for e in ubl_schema.error_log]


@needs_ubl_xsd
@pytest.mark.skipif(not _AEAT_SAMPLE.exists(), reason="AEAT sample invoice not present")
def test_aeat_sample_invoice_validates_against_ubl_2_5(ubl_schema) -> None:
    """Anchors the schema choice: the invoice AEAT itself supplies is valid UBL 2.5."""
    assert ubl_schema.validate(etree.parse(str(_AEAT_SAMPLE)))


def test_bt23_bt24_carry_the_annex_i_values(minimal_invoice) -> None:
    root = etree.fromstring(build_ubl_invoice(minimal_invoice))
    assert _text(root, "cbc:CustomizationID") == AEAT_CUSTOMIZATION_ID
    assert _text(root, "cbc:ProfileID") == AEAT_B2B_PROFILE_ID
    assert AEAT_CUSTOMIZATION_ID == (
        "urn:cen.eu:en16931:2026#conformant#urn:aeat.es:spfe:1.0.0:extended"
    )
    assert AEAT_B2B_PROFILE_ID == "urn:aeat:names:specification:schema:profile:B2B"


def test_matches_aeat_sample_header_values(minimal_invoice) -> None:
    if not _AEAT_SAMPLE.exists():
        pytest.skip("AEAT sample invoice not present")
    sample = etree.parse(str(_AEAT_SAMPLE)).getroot()
    root = etree.fromstring(build_ubl_invoice(minimal_invoice))
    for path in ("cbc:CustomizationID", "cbc:ProfileID"):
        assert _text(root, path) == _text(sample, path)


def test_copy_indicator_bt_es_1(minimal_invoice) -> None:
    original = etree.fromstring(build_ubl_invoice(minimal_invoice))
    copy = etree.fromstring(build_ubl_invoice(minimal_invoice, is_copy=True))
    assert _text(original, "cbc:CopyIndicator") == "false"
    assert _text(copy, "cbc:CopyIndicator") == "true"


def test_spanish_parties_use_loc_scheme_with_fc_attribute(minimal_invoice) -> None:
    root = etree.fromstring(build_ubl_invoice(minimal_invoice))
    for party in ("AccountingSupplierParty", "AccountingCustomerParty"):
        scheme = root.find(f"cac:{party}/cac:Party/cac:PartyTaxScheme", _NS)
        assert scheme.find("cbc:CompanyID", _NS).get("schemeID") == "FC"
        assert scheme.find("cac:TaxScheme/cbc:ID", _NS).text == "LOC"


def test_postal_address_present_for_both_parties(minimal_invoice) -> None:
    """BR-ES-8 and BR-ES-10: street and country code are mandatory."""
    root = etree.fromstring(build_ubl_invoice(minimal_invoice))
    for party in ("AccountingSupplierParty", "AccountingCustomerParty"):
        address = root.find(f"cac:{party}/cac:Party/cac:PostalAddress", _NS)
        assert address.find("cbc:StreetName", _NS).text == "Calle Mayor 1"
        assert address.find("cac:Country/cbc:IdentificationCode", _NS).text == "ES"


def test_no_peppol_identifiers_remain(minimal_invoice) -> None:
    xml = build_ubl_invoice(minimal_invoice).decode()
    assert "peppol" not in xml.lower()
    assert "EndpointID" not in xml
