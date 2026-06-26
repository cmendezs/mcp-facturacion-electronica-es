"""Tests for VERI*FACTU tools: record generation, QR, cancellation, validation."""

from __future__ import annotations

import hashlib
import json

import pytest

from mcp_facturacion_electronica_es.tools.verifactu import (
    _compute_huella,
)

# ---------------------------------------------------------------------------
# Huella computation (pure Python)
# ---------------------------------------------------------------------------


def test_compute_huella_deterministic() -> None:
    """Same inputs must always produce the same Huella."""
    huella1 = _compute_huella(
        emisor_nif="B12345678",
        num_serie="2025-0001",
        fecha_es="15-03-2025",
        tipo_factura="F1",
        cuota_total="210.00",
        fecha_hora_gen="2025-03-15T10:30:00+01:00",
        huella_anterior=None,
    )
    huella2 = _compute_huella(
        emisor_nif="B12345678",
        num_serie="2025-0001",
        fecha_es="15-03-2025",
        tipo_factura="F1",
        cuota_total="210.00",
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
        fecha_hora_gen="2025-03-16T10:00:00+01:00",
        huella_anterior=None,
    )
    h_chained = _compute_huella(
        emisor_nif="B12345678",
        num_serie="2025-0002",
        fecha_es="16-03-2025",
        tipo_factura="F1",
        cuota_total="210.00",
        fecha_hora_gen="2025-03-16T10:00:00+01:00",
        huella_anterior="AABBCC" * 10 + "AABB",  # 64-char previous hash
    )
    assert h_first != h_chained


def test_compute_huella_algorithm() -> None:
    """Verify Huella matches the expected SHA-256 of the concatenated fields."""
    raw = "B12345678&2025-0001&15-03-2025&F1&210.00&2025-03-15T10:30:00+01:00"
    expected = hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
    result = _compute_huella(
        emisor_nif="B12345678",
        num_serie="2025-0001",
        fecha_es="15-03-2025",
        tipo_factura="F1",
        cuota_total="210.00",
        fecha_hora_gen="2025-03-15T10:30:00+01:00",
        huella_anterior=None,
    )
    assert result == expected


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
