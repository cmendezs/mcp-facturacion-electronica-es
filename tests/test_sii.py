"""Tests for SII tools: record building, batch merge, response parsing."""

from __future__ import annotations

from mcp_facturacion_electronica_es.models.es import SIIRecordType
from mcp_facturacion_electronica_es.tools.sii import (
    _mask_nif,
    _merge_sii_records,
    _parse_sii_response,
    build_sii_issued_record,
)


def test_sii_issued_record_clave_regimen(minimal_invoice) -> None:
    xml_bytes = build_sii_issued_record(
        minimal_invoice,
        comm_type="A0",
        clave_regimen="12",
    )
    xml_str = xml_bytes.decode("utf-8")
    assert "<ClaveRegimenEspecialOTrascendencia>12</ClaveRegimenEspecialOTrascendencia>" in xml_str


def test_sii_issued_record_default_clave_regimen(minimal_invoice) -> None:
    xml_bytes = build_sii_issued_record(minimal_invoice)
    xml_str = xml_bytes.decode("utf-8")
    assert "<ClaveRegimenEspecialOTrascendencia>01</ClaveRegimenEspecialOTrascendencia>" in xml_str


# ---------------------------------------------------------------------------
# Batch 4: NIF masking
# ---------------------------------------------------------------------------


def test_mask_nif_long() -> None:
    assert _mask_nif("B12345674") == "B123****4"


def test_mask_nif_short() -> None:
    assert _mask_nif("AB") == "A***B"


# ---------------------------------------------------------------------------
# Batch 4: SII batch merge
# ---------------------------------------------------------------------------


def test_merge_sii_records(minimal_invoice) -> None:
    rec1 = build_sii_issued_record(minimal_invoice)
    rec2 = build_sii_issued_record(minimal_invoice)
    merged = _merge_sii_records(
        records_xml=[rec1.decode(), rec2.decode()],
        seller_nif="B12345674",
        seller_name="Test SL",
        comm_type="A0",
        record_type=SIIRecordType.issued,
    )
    xml_str = merged.decode("utf-8")
    assert "SuministroLRFacturasEmitidas" in xml_str
    assert xml_str.count("RegistroLRFacturasEmitidas") >= 2


# ---------------------------------------------------------------------------
# Batch 4: SII structured response parsing
# ---------------------------------------------------------------------------


def test_parse_sii_response_correcto() -> None:
    raw = """<?xml version="1.0" encoding="UTF-8"?>
    <RespuestaLRFacturasEmitidas xmlns="https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/RespuestaSuministro.xsd">
        <CSV>ABC123</CSV>
        <EstadoEnvio>Correcto</EstadoEnvio>
        <RespuestaLinea>
            <IDFactura><NIF>B12345674</NIF></IDFactura>
            <EstadoRegistro>Correcto</EstadoRegistro>
        </RespuestaLinea>
    </RespuestaLRFacturasEmitidas>"""
    parsed = _parse_sii_response(raw)
    assert parsed["estado_envio"] == "Correcto"
    assert parsed["csv"] == "ABC123"
    assert len(parsed["accepted"]) == 1
    assert parsed["accepted"][0]["nif_masked"] == "B123****4"
    assert len(parsed["rejected"]) == 0


def test_parse_sii_response_incorrecto() -> None:
    raw = """<?xml version="1.0" encoding="UTF-8"?>
    <RespuestaLRFacturasEmitidas xmlns="https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/RespuestaSuministro.xsd">
        <EstadoEnvio>Incorrecto</EstadoEnvio>
        <RespuestaLinea>
            <IDFactura><NIF>A98765431</NIF></IDFactura>
            <EstadoRegistro>Incorrecto</EstadoRegistro>
            <CodigoErrorRegistro>1234</CodigoErrorRegistro>
            <DescripcionErrorRegistro>NIF desconocido</DescripcionErrorRegistro>
        </RespuestaLinea>
    </RespuestaLRFacturasEmitidas>"""
    parsed = _parse_sii_response(raw)
    assert parsed["estado_envio"] == "Incorrecto"
    assert len(parsed["rejected"]) == 1
    assert parsed["rejected"][0]["error_code"] == "1234"
    assert parsed["rejected"][0]["nif_masked"] == "A987****1"


def test_parse_sii_response_empty() -> None:
    parsed = _parse_sii_response("")
    assert parsed["estado_envio"] is None
    assert parsed["accepted"] == []
