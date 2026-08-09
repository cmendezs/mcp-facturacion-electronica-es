"""Tests for VERI*FACTU tools: record generation, QR, cancellation, validation."""

from __future__ import annotations

import hashlib
import json

import pytest

from mcp_facturacion_electronica_es.tools.verifactu import (
    _compute_huella,
    _compute_huella_anulacion,
)

# ---------------------------------------------------------------------------
# Huella computation (pure Python): ES-SC-10 keyed canonical form
# ---------------------------------------------------------------------------


def test_compute_huella_deterministic() -> None:
    """Same inputs must always produce the same Huella."""
    huella1 = _compute_huella(
        emisor_nif="B12345678",
        num_serie="2025-0001",
        fecha_es="15-03-2025",
        tipo_factura="F1",
        cuota_total="210.00",
        importe_total="1210.00",
        fecha_hora_gen="2025-03-15T10:30:00+01:00",
        huella_anterior=None,
    )
    huella2 = _compute_huella(
        emisor_nif="B12345678",
        num_serie="2025-0001",
        fecha_es="15-03-2025",
        tipo_factura="F1",
        cuota_total="210.00",
        importe_total="1210.00",
        fecha_hora_gen="2025-03-15T10:30:00+01:00",
        huella_anterior=None,
    )
    assert huella1 == huella2


def test_compute_huella_format() -> None:
    """Huella must be 64 uppercase hex characters (SHA-256)."""
    huella = _compute_huella(
        emisor_nif="B12345678",
        num_serie="2025-0001",
        fecha_es="15-03-2025",
        tipo_factura="F1",
        cuota_total="210.00",
        importe_total="1210.00",
        fecha_hora_gen="2025-03-15T10:30:00+01:00",
        huella_anterior=None,
    )
    assert len(huella) == 64
    assert huella == huella.upper()
    # Must be valid hex
    int(huella, 16)


def test_compute_huella_chain_differs() -> None:
    """First-record Huella must differ from a chained one."""
    h_first = _compute_huella(
        emisor_nif="B12345678",
        num_serie="2025-0002",
        fecha_es="16-03-2025",
        tipo_factura="F1",
        cuota_total="210.00",
        importe_total="1210.00",
        fecha_hora_gen="2025-03-16T10:00:00+01:00",
        huella_anterior=None,
    )
    h_chained = _compute_huella(
        emisor_nif="B12345678",
        num_serie="2025-0002",
        fecha_es="16-03-2025",
        tipo_factura="F1",
        cuota_total="210.00",
        importe_total="1210.00",
        fecha_hora_gen="2025-03-16T10:00:00+01:00",
        huella_anterior="AABBCC" * 10 + "AABB",  # 64-char previous hash
    )
    assert h_first != h_chained


def test_compute_huella_algorithm() -> None:
    """Verify Huella matches the confirmed AEAT keyed campo=valor& canonical form
    (specs/verifactu/documentation/verifactu-technical-reference.md s1), for a
    chained (non-genesis) record."""
    prev_hash = "AABBCC" * 10 + "AABB"
    raw = (
        "IDEmisorFactura=B12345678&NumSerieFactura=2025-0001&"
        "FechaExpedicionFactura=15-03-2025&TipoFactura=F1&CuotaTotal=210.00&"
        f"ImporteTotal=1210.00&Huella={prev_hash}&"
        "FechaHoraHusoGenRegistro=2025-03-15T10:30:00+01:00"
    )
    expected = hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
    result = _compute_huella(
        emisor_nif="B12345678",
        num_serie="2025-0001",
        fecha_es="15-03-2025",
        tipo_factura="F1",
        cuota_total="210.00",
        importe_total="1210.00",
        fecha_hora_gen="2025-03-15T10:30:00+01:00",
        huella_anterior=prev_hash,
    )
    assert result == expected


def test_compute_huella_algorithm_genesis_record() -> None:
    """First (genesis) record: Huella= is present with an empty value, not omitted."""
    raw = (
        "IDEmisorFactura=B12345678&NumSerieFactura=2025-0001&"
        "FechaExpedicionFactura=15-03-2025&TipoFactura=F1&CuotaTotal=210.00&"
        "ImporteTotal=1210.00&Huella=&"
        "FechaHoraHusoGenRegistro=2025-03-15T10:30:00+01:00"
    )
    expected = hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
    result = _compute_huella(
        emisor_nif="B12345678",
        num_serie="2025-0001",
        fecha_es="15-03-2025",
        tipo_factura="F1",
        cuota_total="210.00",
        importe_total="1210.00",
        fecha_hora_gen="2025-03-15T10:30:00+01:00",
        huella_anterior=None,
    )
    assert result == expected


def test_compute_huella_anulacion_algorithm() -> None:
    """ES-SC-11: anulación huella uses the dedicated reduced field set (no
    TipoFactura, no CuotaTotal)."""
    prev_hash = "AABBCC" * 10 + "AABB"
    raw = (
        "IDEmisorFactura=B12345678&NumSerieFactura=2025-0001&"
        "FechaExpedicionFactura=15-03-2025&"
        f"Huella={prev_hash}&"
        "FechaHoraHusoGenRegistro=2025-03-16T09:00:00+01:00"
    )
    expected = hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
    result = _compute_huella_anulacion(
        emisor_nif="B12345678",
        num_serie="2025-0001",
        fecha_es="15-03-2025",
        fecha_hora_gen="2025-03-16T09:00:00+01:00",
        huella_anterior=prev_hash,
    )
    assert result == expected


def test_compute_huella_anulacion_differs_from_alta() -> None:
    """Same identity fields must not collide between alta and anulación huellas."""
    h_alta = _compute_huella(
        emisor_nif="B12345678",
        num_serie="2025-0001",
        fecha_es="15-03-2025",
        tipo_factura="F1",
        cuota_total="210.00",
        importe_total="1210.00",
        fecha_hora_gen="2025-03-15T10:30:00+01:00",
        huella_anterior=None,
    )
    h_anulacion = _compute_huella_anulacion(
        emisor_nif="B12345678",
        num_serie="2025-0001",
        fecha_es="15-03-2025",
        fecha_hora_gen="2025-03-15T10:30:00+01:00",
        huella_anterior=None,
    )
    assert h_alta != h_anulacion


# ---------------------------------------------------------------------------
# Tool handler integration (no network)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_generate_verifactu_record(minimal_invoice) -> None:
    from mcp_facturacion_electronica_es.tools.verifactu import handle_es_generate_verifactu_record

    result = await handle_es_generate_verifactu_record(
        {
            "invoice": minimal_invoice.model_dump(),
            "invoice_type": "F1",
            "software_id": "SW-001",
            "software_nif": "B87654321",
        }
    )
    data = json.loads(result[0].text)
    assert "error" not in data
    assert "xml" in data
    assert "huella" in data
    assert len(data["huella"]) == 64
    # XML must contain required elements
    assert "IDEmisorFactura" in data["xml"]
    assert "NombreRazonEmisor" in data["xml"]
    assert "TipoFactura" in data["xml"]
    assert "Huella" in data["xml"]


@pytest.mark.asyncio
async def test_handle_generate_verifactu_record_chained(minimal_invoice) -> None:
    from mcp_facturacion_electronica_es.tools.verifactu import handle_es_generate_verifactu_record

    prev_hash = "A" * 64
    result = await handle_es_generate_verifactu_record(
        {
            "invoice": minimal_invoice.model_dump(),
            "invoice_type": "F1",
            "software_id": "SW-001",
            "software_nif": "B87654321",
            "previous_hash": prev_hash,
        }
    )
    data = json.loads(result[0].text)
    assert "error" not in data
    assert len(data["huella"]) == 64
    # RegistroAnterior must reference the previous hash
    assert prev_hash in data["xml"]


@pytest.mark.asyncio
async def test_handle_generate_verifactu_record_missing_invoice() -> None:
    from mcp_facturacion_electronica_es.tools.verifactu import handle_es_generate_verifactu_record

    result = await handle_es_generate_verifactu_record(
        {
            "invoice_type": "F1",
            "software_id": "SW-001",
            "software_nif": "B87654321",
        }
    )
    data = json.loads(result[0].text)
    assert "error" in data


@pytest.mark.asyncio
async def test_handle_generate_qr_verifactu() -> None:
    from mcp_facturacion_electronica_es.tools.verifactu import handle_es_generate_qr_verifactu

    result = await handle_es_generate_qr_verifactu(
        {
            "nif": "B12345678",
            "invoice_number": "2025-0001",
            "invoice_date": "2025-03-15",
            "total_amount": 1210.00,
            "size_px": 150,
        }
    )
    data = json.loads(result[0].text)
    assert "error" not in data
    assert "qr_png_base64" in data
    assert len(data["qr_png_base64"]) > 100  # non-empty base64
    assert "verification_url" in data
    assert "B12345678" in data["verification_url"]
    assert "2025-0001" in data["verification_url"]
    # Date must be in DD-MM-YYYY format in the URL
    assert "15-03-2025" in data["verification_url"]


@pytest.mark.asyncio
async def test_handle_cancel_verifactu_record() -> None:
    from mcp_facturacion_electronica_es.tools.verifactu import handle_es_cancel_verifactu_record

    result = await handle_es_cancel_verifactu_record(
        {
            "original_invoice_number": "2025-0001",
            "original_invoice_date": "2025-03-15",
            "issuer_nif": "B12345678",
            "issuer_name": "Empresa de Prueba SL",
            "previous_hash": "A" * 64,
        }
    )
    data = json.loads(result[0].text)
    assert "error" not in data
    assert "xml" in data
    assert "RegistroAnulacion" in data["xml"]
    assert len(data["huella"]) == 64


@pytest.mark.asyncio
async def test_handle_validate_verifactu_record_valid(minimal_verifactu_xml) -> None:
    from mcp_facturacion_electronica_es.tools.verifactu import handle_es_validate_verifactu_record

    result = await handle_es_validate_verifactu_record({"xml": minimal_verifactu_xml})
    data = json.loads(result[0].text)
    assert "error" not in data
    assert data["valid"] is True
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_handle_validate_verifactu_record_invalid_xml() -> None:
    from mcp_facturacion_electronica_es.tools.verifactu import handle_es_validate_verifactu_record

    result = await handle_es_validate_verifactu_record({"xml": "<broken xml <<<"})
    data = json.loads(result[0].text)
    assert data["valid"] is False
    assert len(data["errors"]) > 0


# ---------------------------------------------------------------------------
# Batch 2: parameterized clave_regimen, impuesto, calificacion_operacion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verifactu_non_default_clave_regimen_impuesto(minimal_invoice) -> None:
    from mcp_facturacion_electronica_es.tools.verifactu import handle_es_generate_verifactu_record

    result = await handle_es_generate_verifactu_record(
        {
            "invoice": minimal_invoice.model_dump(),
            "invoice_type": "F1",
            "software_id": "SW-001",
            "software_nif": "B87654321",
            "clave_regimen": "02",
            "impuesto": "02",
            "calificacion_operacion": "N1",
        }
    )
    data = json.loads(result[0].text)
    assert "error" not in data
    xml = data["xml"]
    assert "ClaveRegimen>02</" in xml
    assert "Impuesto>02</" in xml
    assert "CalificacionOperacion>N1</" in xml


# ---------------------------------------------------------------------------
# Batch 4: TiempoEsperaEnvio deferral detection
# ---------------------------------------------------------------------------


def test_verifactu_response_tiempo_espera() -> None:
    from mcp_facturacion_electronica_es.tools.verifactu import _parse_verifactu_response

    raw = """<?xml version="1.0" encoding="UTF-8"?>
    <Respuesta>
        <EstadoEnvio>Aceptado</EstadoEnvio>
        <TiempoEsperaEnvio>120</TiempoEsperaEnvio>
    </Respuesta>"""
    parsed = _parse_verifactu_response(raw)
    assert parsed["status"] == "deferred"
    assert parsed["retry_after_seconds"] == 120


def test_verifactu_response_no_espera() -> None:
    from mcp_facturacion_electronica_es.tools.verifactu import _parse_verifactu_response

    raw = """<?xml version="1.0" encoding="UTF-8"?>
    <Respuesta>
        <EstadoEnvio>Correcto</EstadoEnvio>
        <CSV>XYZ789</CSV>
    </Respuesta>"""
    parsed = _parse_verifactu_response(raw)
    assert "status" not in parsed
    assert parsed["CSV"] == "XYZ789"


# ---------------------------------------------------------------------------
# Batch 5: QR URL uses provisional AEAT base, mandatory legends
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_qr_url_uses_provisional_base() -> None:
    from mcp_facturacion_electronica_es.tools.verifactu import handle_es_generate_qr_verifactu

    result = await handle_es_generate_qr_verifactu(
        {
            "nif": "B12345678",
            "invoice_number": "2025-0001",
            "invoice_date": "2025-03-15",
            "total_amount": 1210.00,
        }
    )
    data = json.loads(result[0].text)
    assert "prewww2.aeat.es" in data["verification_url"]
    assert "mandatory_legends" in data
    assert len(data["mandatory_legends"]) == 2
    assert "VERIFACTU" in data["mandatory_legends"]


@pytest.mark.asyncio
async def test_qr_verifactu_includes_physical_spec() -> None:
    """QR physical spec (min size, ISO 18004, ECC level M) must be surfaced."""
    from mcp_facturacion_electronica_es.tools.verifactu import handle_es_generate_qr_verifactu

    result = await handle_es_generate_qr_verifactu(
        {
            "nif": "B12345678",
            "invoice_number": "2025-0001",
            "invoice_date": "2025-03-15",
            "total_amount": 1210.00,
        }
    )
    data = json.loads(result[0].text)
    assert data["physical_spec"]["min_size_mm"] == "30x40"
    assert data["physical_spec"]["symbology"] == "ISO/IEC 18004"
    assert data["physical_spec"]["error_correction_level"] == "M"


# ---------------------------------------------------------------------------
# ES-LC-10: es__query_verifactu_status (ConsultaLR)
# ---------------------------------------------------------------------------

_RESPUESTA_CONSULTA_LR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<sfLRRC:RespuestaConsultaFactuSistemaFacturacion
    xmlns:sfLRRC="https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/RespuestaConsultaLR.xsd"
    xmlns:sf="https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SuministroInformacion.xsd">
  <sf:Cabecera/>
  <sfLRRC:PeriodoImputacion><sf:Ejercicio>2025</sf:Ejercicio><sf:Periodo>03</sf:Periodo></sfLRRC:PeriodoImputacion>
  <sfLRRC:IndicadorPaginacion>N</sfLRRC:IndicadorPaginacion>
  <sfLRRC:ResultadoConsulta>ConDatos</sfLRRC:ResultadoConsulta>
  <sfLRRC:RegistroRespuestaConsultaFactuSistemaFacturacion>
    <sf:IDFactura>
      <sf:IDEmisorFactura>B12345678</sf:IDEmisorFactura>
      <sf:NumSerieFactura>2025-0001</sf:NumSerieFactura>
      <sf:FechaExpedicionFactura>15-03-2025</sf:FechaExpedicionFactura>
    </sf:IDFactura>
    <sfLRRC:DatosRegistroFacturacion/>
    <sfLRRC:EstadoRegistro>
      <sfLRRC:TimestampUltimaModificacion>2025-03-15T10:31:00+01:00</sfLRRC:TimestampUltimaModificacion>
      <sfLRRC:EstadoRegistro>Correcto</sfLRRC:EstadoRegistro>
    </sfLRRC:EstadoRegistro>
  </sfLRRC:RegistroRespuestaConsultaFactuSistemaFacturacion>
</sfLRRC:RespuestaConsultaFactuSistemaFacturacion>"""


def test_build_consulta_lr_valid_against_bundled_xsd() -> None:
    """The generated request must validate against specs/verifactu/xsd/ConsultaLR.xsd
    (once xmldsig-core-schema.xsd is resolvable; here we only check namespace/shape
    since the bundled schema's remote xmldsig import cannot be fetched offline)."""
    from lxml import etree

    from mcp_facturacion_electronica_es.tools.verifactu import (
        _VF_CONSULTA_NS,
        _VF_SF_NS,
        _build_consulta_lr,
    )

    xml_bytes = _build_consulta_lr(
        nif="B12345678",
        name="Empresa de Prueba SL",
        fiscal_year=2025,
        period="03",
        num_serie_factura="2025-0001",
    )
    root = etree.fromstring(xml_bytes)
    assert root.tag == f"{{{_VF_CONSULTA_NS}}}ConsultaFactuSistemaFacturacion"

    cab = root.find(f"{{{_VF_CONSULTA_NS}}}Cabecera")
    assert cab is not None
    assert cab.find(f"{{{_VF_SF_NS}}}IDVersion").text == "1.0"
    oblig = cab.find(f"{{{_VF_SF_NS}}}ObligadoEmision")
    assert oblig.find(f"{{{_VF_SF_NS}}}NIF").text == "B12345678"
    assert oblig.find(f"{{{_VF_SF_NS}}}NombreRazon").text == "Empresa de Prueba SL"

    filtro = root.find(f"{{{_VF_CONSULTA_NS}}}FiltroConsulta")
    assert filtro is not None
    periodo = filtro.find(f"{{{_VF_CONSULTA_NS}}}PeriodoImputacion")
    assert periodo.find(f"{{{_VF_SF_NS}}}Ejercicio").text == "2025"
    assert periodo.find(f"{{{_VF_SF_NS}}}Periodo").text == "03"
    assert filtro.find(f"{{{_VF_CONSULTA_NS}}}NumSerieFactura").text == "2025-0001"


def test_build_consulta_lr_without_num_serie_factura() -> None:
    from lxml import etree

    from mcp_facturacion_electronica_es.tools.verifactu import (
        _VF_CONSULTA_NS,
        _build_consulta_lr,
    )

    xml_bytes = _build_consulta_lr(
        nif="B12345678", name="Empresa de Prueba SL", fiscal_year=2025, period="03"
    )
    root = etree.fromstring(xml_bytes)
    filtro = root.find(f"{{{_VF_CONSULTA_NS}}}FiltroConsulta")
    assert filtro.find(f"{{{_VF_CONSULTA_NS}}}NumSerieFactura") is None


def test_parse_consulta_lr_response_extracts_estado_registro() -> None:
    from mcp_facturacion_electronica_es.tools.verifactu import _parse_consulta_lr_response

    parsed = _parse_consulta_lr_response(_RESPUESTA_CONSULTA_LR_XML)
    assert parsed["resultado_consulta"] == "ConDatos"
    assert len(parsed["registros"]) == 1
    registro = parsed["registros"][0]
    assert registro["IDEmisorFactura"] == "B12345678"
    assert registro["NumSerieFactura"] == "2025-0001"
    assert registro["EstadoRegistro"] == "Correcto"
    assert registro["TimestampUltimaModificacion"] == "2025-03-15T10:31:00+01:00"
    # Never echo the raw XML string itself
    assert "<sfLRRC:" not in json.dumps(parsed)


def test_parse_consulta_lr_response_empty() -> None:
    from mcp_facturacion_electronica_es.tools.verifactu import _parse_consulta_lr_response

    assert _parse_consulta_lr_response("") == {}


@pytest.mark.asyncio
async def test_handle_query_verifactu_status_masks_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcp_facturacion_electronica_es.tools import verifactu as verifactu_module

    monkeypatch.setattr(
        verifactu_module.SignerClient, "is_configured", staticmethod(lambda: False)
    )
    from mcp_facturacion_electronica_es.config import aeat_settings

    monkeypatch.setattr(aeat_settings, "certificate_path", "/fake/cert.p12")
    monkeypatch.setattr(aeat_settings, "certificate_password", "test")

    class _FakeResponse:
        status_code = 200
        text = _RESPUESTA_CONSULTA_LR_XML

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def _request(self, *args, **kwargs):
            return _FakeResponse()

    monkeypatch.setattr(
        "mcp_einvoicing_core.http_client.BaseEInvoicingClient", _FakeClient
    )

    result = await verifactu_module.handle_es_query_verifactu_status(
        {
            "nif": "B12345678",
            "name": "Empresa de Prueba SL",
            "invoice_date": "2025-03-15",
            "num_serie_factura": "2025-0001",
        }
    )
    data = json.loads(result[0].text)
    assert "error" not in data
    assert data["parsed_response"]["resultado_consulta"] == "ConDatos"
    assert data["parsed_response"]["registros"][0]["EstadoRegistro"] == "Correcto"
    assert "sfLRRC:" not in result[0].text


@pytest.mark.asyncio
async def test_handle_query_verifactu_status_missing_params() -> None:
    from mcp_facturacion_electronica_es.tools.verifactu import (
        handle_es_query_verifactu_status,
    )

    result = await handle_es_query_verifactu_status({})
    data = json.loads(result[0].text)
    assert "error" in data
