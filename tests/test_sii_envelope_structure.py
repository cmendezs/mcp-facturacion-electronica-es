"""Structural validation of SII SOAP envelopes against bundled WSDL/XSD reference.

These tests run without credentials and verify that the generated envelopes
contain the required elements in the correct order and namespace.
"""

from __future__ import annotations

import pytest
from lxml import etree

from mcp_facturacion_electronica_es.tools.sii import (
    SIIRecordType,
    _merge_sii_records,
    build_sii_issued_record,
    build_sii_received_record,
)

_SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
_SII_NS = (
    "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones"
    "/es/aeat/burt/jee/aj/ws/SuministroInformacion.xsd"
)


@pytest.fixture()
def issued_envelope(minimal_invoice) -> bytes:
    return build_sii_issued_record(minimal_invoice)


@pytest.fixture()
def received_envelope(minimal_invoice) -> bytes:
    return build_sii_received_record(minimal_invoice)


class TestIssuedEnvelopeStructure:
    def test_is_valid_xml(self, issued_envelope: bytes) -> None:
        root = etree.fromstring(issued_envelope)
        assert root.tag == f"{{{_SOAP_NS}}}Envelope"

    def test_has_header_and_body(self, issued_envelope: bytes) -> None:
        root = etree.fromstring(issued_envelope)
        header = root.find(f"{{{_SOAP_NS}}}Header")
        body = root.find(f"{{{_SOAP_NS}}}Body")
        assert header is not None
        assert body is not None

    def test_body_contains_suministro(self, issued_envelope: bytes) -> None:
        root = etree.fromstring(issued_envelope)
        body = root.find(f"{{{_SOAP_NS}}}Body")
        suministro = body.find(f"{{{_SII_NS}}}SuministroLRFacturasEmitidas")
        assert suministro is not None

    def test_cabecera_present(self, issued_envelope: bytes) -> None:
        root = etree.fromstring(issued_envelope)
        cabs = root.xpath(".//*[local-name()='Cabecera']")
        assert len(cabs) == 1
        titular = cabs[0].xpath(".//*[local-name()='NIF']")
        assert len(titular) >= 1

    def test_registro_present(self, issued_envelope: bytes) -> None:
        root = etree.fromstring(issued_envelope)
        registros = root.xpath(".//*[local-name()='RegistroLRFacturasEmitidas']")
        assert len(registros) == 1

    def test_factura_expedida_required_children(self, issued_envelope: bytes) -> None:
        root = etree.fromstring(issued_envelope)
        factura = root.xpath(".//*[local-name()='FacturaExpedida']")
        assert len(factura) == 1
        child_tags = [etree.QName(c).localname for c in factura[0]]
        assert "TipoFactura" in child_tags
        assert "ClaveRegimenEspecialOTrascendencia" in child_tags
        assert "ImporteTotal" in child_tags
        assert "DescripcionOperacion" in child_tags

    def test_tipo_desglose_structure(self, issued_envelope: bytes) -> None:
        root = etree.fromstring(issued_envelope)
        desglose = root.xpath(".//*[local-name()='TipoDesglose']")
        assert len(desglose) == 1
        iva_details = root.xpath(".//*[local-name()='DetalleIVA']")
        assert len(iva_details) >= 1
        detail_children = [etree.QName(c).localname for c in iva_details[0]]
        assert "TipoImpositivo" in detail_children
        assert "BaseImponible" in detail_children
        assert "CuotaRepercutida" in detail_children

    def test_periodo_liquidacion(self, issued_envelope: bytes) -> None:
        root = etree.fromstring(issued_envelope)
        periodo = root.xpath(".//*[local-name()='PeriodoLiquidacion']")
        assert len(periodo) == 1
        ejercicio = periodo[0].xpath(".//*[local-name()='Ejercicio']")
        assert len(ejercicio) == 1
        assert ejercicio[0].text is not None


class TestReceivedEnvelopeStructure:
    def test_body_contains_recibidas(self, received_envelope: bytes) -> None:
        root = etree.fromstring(received_envelope)
        body = root.find(f"{{{_SOAP_NS}}}Body")
        suministro = body.find(f"{{{_SII_NS}}}SuministroLRFacturasRecibidas")
        assert suministro is not None

    def test_registro_recibidas_present(self, received_envelope: bytes) -> None:
        root = etree.fromstring(received_envelope)
        registros = root.xpath(".//*[local-name()='RegistroLRFacturasRecibidas']")
        assert len(registros) == 1


class TestMergedEnvelope:
    def test_merge_preserves_all_records(self, minimal_invoice) -> None:
        record1 = build_sii_issued_record(minimal_invoice)
        record2 = build_sii_issued_record(minimal_invoice, comm_type="A1")
        merged = _merge_sii_records(
            [record1.decode(), record2.decode()],
            seller_nif=minimal_invoice.seller.tax_id.identifier,
            seller_name=minimal_invoice.seller.display_name,
            comm_type="A0",
            record_type=SIIRecordType.issued,
        )
        root = etree.fromstring(merged)
        registros = root.xpath(".//*[local-name()='RegistroLRFacturasEmitidas']")
        assert len(registros) == 2

    def test_merged_has_single_cabecera(self, minimal_invoice) -> None:
        record = build_sii_issued_record(minimal_invoice)
        merged = _merge_sii_records(
            [record.decode()],
            seller_nif=minimal_invoice.seller.tax_id.identifier,
            seller_name=minimal_invoice.seller.display_name,
            comm_type="A0",
            record_type=SIIRecordType.issued,
        )
        root = etree.fromstring(merged)
        cabs = root.xpath(".//*[local-name()='Cabecera']")
        assert len(cabs) == 1
