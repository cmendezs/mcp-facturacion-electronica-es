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
    """ES-SC-11: anulación huella uses the dedicated *Anulada field set (no
    TipoFactura, no CuotaTotal, and IDEmisorFacturaAnulada/NumSerieFacturaAnulada/
    FechaExpedicionFacturaAnulada — not the alta field names)."""
    prev_hash = "AABBCC" * 10 + "AABB"
    raw = (
        "IDEmisorFacturaAnulada=B12345678&NumSerieFacturaAnulada=2025-0001&"
        "FechaExpedicionFacturaAnulada=15-03-2025&"
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


# ---------------------------------------------------------------------------
# Golden vectors from the official AEAT huella spec (worked examples s6.1-6.3 of
# Veri-Factu_especificaciones_huella_hash_registros.pdf v0.1.2, bundled at
# specs/verifactu/documentation/). These pin the exact field order/naming
# independently of the implementation, so a regression to the pre-fix field
# names (or any reordering) fails immediately.
# ---------------------------------------------------------------------------


def test_compute_huella_alta_official_vector_genesis() -> None:
    """Spec s6.1: first (genesis) RegistroAlta."""
    result = _compute_huella(
        emisor_nif="89890001K",
        num_serie="12345678/G33",
        fecha_es="01-01-2024",
        tipo_factura="F1",
        cuota_total="12.35",
        importe_total="123.45",
        fecha_hora_gen="2024-01-01T19:20:30+01:00",
        huella_anterior=None,
    )
    assert result == "3C464DAF61ACB827C65FDA19F352A4E3BDC2C640E9E9FC4CC058073F38F12F60"


def test_compute_huella_alta_official_vector_chained() -> None:
    """Spec s6.2: second RegistroAlta, chained to s6.1's huella."""
    result = _compute_huella(
        emisor_nif="89890001K",
        num_serie="12345679/G34",
        fecha_es="01-01-2024",
        tipo_factura="F1",
        cuota_total="12.35",
        importe_total="123.45",
        fecha_hora_gen="2024-01-01T19:20:35+01:00",
        huella_anterior="3C464DAF61ACB827C65FDA19F352A4E3BDC2C640E9E9FC4CC058073F38F12F60",
    )
    assert result == "F7B94CFD8924EDFF273501B01EE5153E4CE8F259766F88CF6ACB8935802A2B97"


def test_compute_huella_anulacion_official_vector() -> None:
    """Spec s6.3: RegistroAnulacion chained to s6.2's huella."""
    result = _compute_huella_anulacion(
        emisor_nif="89890001K",
        num_serie="12345679/G34",
        fecha_es="01-01-2024",
        fecha_hora_gen="2024-01-01T19:20:40+01:00",
        huella_anterior="F7B94CFD8924EDFF273501B01EE5153E4CE8F259766F88CF6ACB8935802A2B97",
    )
    assert result == "177547C0D57AC74748561D054A9CEC14B4C4EA23D1BEFD6F2E69E3A388F90C68"


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
async def test_handle_cancel_verifactu_record_uses_anulada_id_factura_names() -> None:
    """The top-level <IDFactura> block inside RegistroAnulacion must use the
    "*Anulada" element names (IDFacturaExpedidaBajaType in
    SuministroInformacion.xsd), not the RegistroAlta names — a prior
    implementation reused _build_id_factura (the alta builder) here, which is
    structurally invalid against the XSD."""
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
    xml = data["xml"]

    idf_start = xml.index("<sf:IDFactura>")
    idf_end = xml.index("</sf:IDFactura>")
    id_factura_block = xml[idf_start:idf_end]

    assert "IDEmisorFacturaAnulada" in id_factura_block
    assert "NumSerieFacturaAnulada" in id_factura_block
    assert "FechaExpedicionFacturaAnulada" in id_factura_block
    # The alta-only (unsuffixed) names must not appear inside this specific
    # block — they legitimately appear elsewhere, in <RegistroAnterior>.
    assert "sf:IDEmisorFactura>" not in id_factura_block
    assert "sf:NumSerieFactura>" not in id_factura_block
    assert "sf:FechaExpedicionFactura>" not in id_factura_block


@pytest.mark.asyncio
async def test_handle_validate_verifactu_record_anulacion_no_false_positives() -> None:
    """A valid RegistroAnulacion has no TipoFactura/CuotaTotal/ImporteTotal —
    those are RegistroAlta-only fields. The structural checklist must not
    require them for an anulación document (regression: it previously
    reported all three as "missing" on every valid anulación)."""
    from mcp_facturacion_electronica_es.tools.verifactu import (
        handle_es_cancel_verifactu_record,
        handle_es_validate_verifactu_record,
    )

    gen_result = await handle_es_cancel_verifactu_record(
        {
            "original_invoice_number": "2025-0001",
            "original_invoice_date": "2025-03-15",
            "issuer_nif": "B12345678",
            "issuer_name": "Empresa de Prueba SL",
            "previous_hash": "A" * 64,
        }
    )
    xml = json.loads(gen_result[0].text)["xml"]

    val_result = await handle_es_validate_verifactu_record({"xml": xml})
    val_data = json.loads(val_result[0].text)
    assert val_data["errors"] == []
    assert val_data["valid"] is True


def test_validate_verifactu_xsd_path_resolves_to_bundled_schema() -> None:
    """Regression: the XSD path in handle_es_validate_verifactu_record used
    three .parent hops (landing on src/, one level short of the package
    root), silently degrading every call to structural-only validation
    forever. Four hops are required to reach specs/."""
    import pathlib

    import mcp_facturacion_electronica_es.tools.verifactu as verifactu_module

    xsd_path = (
        pathlib.Path(verifactu_module.__file__).parent.parent.parent.parent
        / "specs"
        / "verifactu"
        / "xsd"
        / "SuministroLR.xsd"
    )
    assert xsd_path.exists(), f"expected bundled XSD at {xsd_path}"


# ---------------------------------------------------------------------------
# ES-LC-12: accepted-only chain contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_chain_identity_from_registro_alta(minimal_invoice) -> None:
    from mcp_facturacion_electronica_es.tools.verifactu import (
        _extract_chain_identity,
        handle_es_generate_verifactu_record,
    )

    result = await handle_es_generate_verifactu_record(
        {
            "invoice": minimal_invoice.model_dump(),
            "software_id": "SW-001",
            "software_nif": "B87654321",
        }
    )
    data = json.loads(result[0].text)
    identity = _extract_chain_identity(data["xml"].encode())

    assert identity is not None
    assert identity["emisor_nif"] == minimal_invoice.seller.tax_id.identifier
    assert identity["num_serie"] == minimal_invoice.number
    assert identity["huella"] == data["huella"]


@pytest.mark.asyncio
async def test_extract_chain_identity_from_registro_anulacion() -> None:
    from mcp_facturacion_electronica_es.tools.verifactu import (
        _extract_chain_identity,
        handle_es_cancel_verifactu_record,
    )

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
    identity = _extract_chain_identity(data["xml"].encode())

    assert identity is not None
    assert identity["emisor_nif"] == "B12345678"
    assert identity["num_serie"] == "2025-0001"
    assert identity["huella"] == data["huella"]
    # Must not be confused with RegistroAnterior's identity (previous_hash="A"*64)
    assert identity["huella"] != "A" * 64


def test_extract_chain_identity_ignores_registro_anterior_fields() -> None:
    """Regression: RegistroAnterior carries the *same* local-names
    (IDEmisorFactura/NumSerieFactura/FechaExpedicionFactura/Huella) as the
    top-level RegistroAlta identity — extraction must not accidentally pick
    up the predecessor's identity instead of this record's own."""
    from mcp_facturacion_electronica_es.tools.verifactu import _extract_chain_identity

    xml = (
        b"<sfLR:RegFactuSistemaFacturacion "
        b'xmlns:sfLR="urn:lr" xmlns:sf="urn:sf">'
        b"<sfLR:RegistroFactura><sf:RegistroAlta>"
        b"<sf:IDFactura><sf:IDEmisorFactura>B12345678</sf:IDEmisorFactura>"
        b"<sf:NumSerieFactura>2025-0002</sf:NumSerieFactura>"
        b"<sf:FechaExpedicionFactura>16-03-2025</sf:FechaExpedicionFactura>"
        b"</sf:IDFactura>"
        b"<sf:Encadenamiento><sf:RegistroAnterior>"
        b"<sf:IDEmisorFactura>B12345678</sf:IDEmisorFactura>"
        b"<sf:NumSerieFactura>2025-0001</sf:NumSerieFactura>"
        b"<sf:FechaExpedicionFactura>15-03-2025</sf:FechaExpedicionFactura>"
        b"<sf:Huella>" + b"A" * 64 + b"</sf:Huella>"
        b"</sf:RegistroAnterior></sf:Encadenamiento>"
        b"<sf:Huella>" + b"B" * 64 + b"</sf:Huella>"
        b"</sf:RegistroAlta></sfLR:RegistroFactura></sfLR:RegFactuSistemaFacturacion>"
    )
    identity = _extract_chain_identity(xml)
    assert identity is not None
    assert identity["num_serie"] == "2025-0002"
    assert identity["fecha"] == "16-03-2025"
    assert identity["huella"] == "B" * 64


def test_build_chain_result_accepted_correcto() -> None:
    from mcp_facturacion_electronica_es.tools.verifactu import _build_chain_result

    xml = (
        b"<sfLR:RegFactuSistemaFacturacion "
        b'xmlns:sfLR="urn:lr" xmlns:sf="urn:sf">'
        b"<sfLR:RegistroFactura><sf:RegistroAlta>"
        b"<sf:IDFactura><sf:IDEmisorFactura>B12345678</sf:IDEmisorFactura>"
        b"<sf:NumSerieFactura>2025-0001</sf:NumSerieFactura>"
        b"<sf:FechaExpedicionFactura>15-03-2025</sf:FechaExpedicionFactura>"
        b"</sf:IDFactura>"
        b"<sf:Huella>" + b"A" * 64 + b"</sf:Huella>"
        b"</sf:RegistroAlta></sfLR:RegistroFactura></sfLR:RegFactuSistemaFacturacion>"
    )
    result = _build_chain_result({"EstadoRegistro": "Correcto"}, xml)
    assert result["accepted"] is True
    assert result["safe_to_chain_from"]["huella"] == "A" * 64


def test_build_chain_result_accepted_con_errores_still_chainable() -> None:
    """Per the AEAT huella spec s7: a huella mismatch alone produces
    AceptadoConErrores, not Incorrecto — the record is still stored under its
    Huella, so it remains safe to chain from."""
    from mcp_facturacion_electronica_es.tools.verifactu import _build_chain_result

    xml = (
        b"<sfLR:RegFactuSistemaFacturacion "
        b'xmlns:sfLR="urn:lr" xmlns:sf="urn:sf">'
        b"<sfLR:RegistroFactura><sf:RegistroAlta>"
        b"<sf:IDFactura><sf:IDEmisorFactura>B12345678</sf:IDEmisorFactura>"
        b"<sf:NumSerieFactura>2025-0001</sf:NumSerieFactura>"
        b"<sf:FechaExpedicionFactura>15-03-2025</sf:FechaExpedicionFactura>"
        b"</sf:IDFactura>"
        b"<sf:Huella>" + b"B" * 64 + b"</sf:Huella>"
        b"</sf:RegistroAlta></sfLR:RegistroFactura></sfLR:RegFactuSistemaFacturacion>"
    )
    result = _build_chain_result({"EstadoRegistro": "AceptadoConErrores"}, xml)
    assert result["accepted"] is True
    assert result["safe_to_chain_from"] is not None


def test_build_chain_result_rejected_incorrecto_blocks_chaining() -> None:
    from mcp_facturacion_electronica_es.tools.verifactu import _build_chain_result

    result = _build_chain_result({"EstadoRegistro": "Incorrecto"}, b"<x/>")
    assert result["accepted"] is False
    assert result["safe_to_chain_from"] is None
    assert "warning" in result


def test_build_chain_result_deferred_blocks_chaining() -> None:
    from mcp_facturacion_electronica_es.tools.verifactu import _build_chain_result

    result = _build_chain_result({"status": "deferred", "retry_after_seconds": 30}, b"<x/>")
    assert result["accepted"] is None
    assert result["safe_to_chain_from"] is None
    assert "note" in result


def test_build_chain_result_no_estado_blocks_chaining() -> None:
    """Transport-level failure or unparseable response: no EstadoRegistro at
    all must not be treated as accepted."""
    from mcp_facturacion_electronica_es.tools.verifactu import _build_chain_result

    result = _build_chain_result({}, b"<x/>")
    assert result["accepted"] is False
    assert result["safe_to_chain_from"] is None


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
# Batch 5: QR URL matches the confirmed AEAT ValidarQR spec, mandatory legends
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_qr_url_uses_sandbox_base_by_default() -> None:
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
    assert data["verification_url"].startswith(
        "https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?"
    )
    assert data["environment"] == "sandbox"
    assert "mandatory_legends" in data
    assert len(data["mandatory_legends"]) == 2
    assert "VERIFACTU" in data["mandatory_legends"]


@pytest.mark.asyncio
async def test_qr_url_switches_to_production(monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_facturacion_electronica_es.tools.verifactu import handle_es_generate_qr_verifactu

    monkeypatch.setenv("AEAT_ENV", "production")
    result = await handle_es_generate_qr_verifactu(
        {
            "nif": "B12345678",
            "invoice_number": "2025-0001",
            "invoice_date": "2025-03-15",
            "total_amount": 1210.00,
        }
    )
    data = json.loads(result[0].text)
    assert data["verification_url"].startswith(
        "https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR?"
    )
    assert data["environment"] == "production"


@pytest.mark.asyncio
async def test_qr_url_official_worked_example() -> None:
    """DetalleEspecificacTecnCodigoQRfactura.pdf s8.1: exact query string for a
    known nif/numserie/fecha/importe combination (no special characters)."""
    from mcp_facturacion_electronica_es.tools.verifactu import handle_es_generate_qr_verifactu

    result = await handle_es_generate_qr_verifactu(
        {
            "nif": "89890001K",
            "invoice_number": "12345678-G33",
            "invoice_date": "2024-09-01",
            "total_amount": 241.4,
        }
    )
    data = json.loads(result[0].text)
    assert data["verification_url"] == (
        "https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR"
        "?nif=89890001K&numserie=12345678-G33&fecha=01-09-2024&importe=241.40"
    )


@pytest.mark.asyncio
async def test_qr_url_encodes_special_characters_in_numserie() -> None:
    """s4 of the spec: an unencoded "&" inside numserie would truncate the
    query string; it must come out as "%26" (the doc's own worked example)."""
    from mcp_facturacion_electronica_es.tools.verifactu import handle_es_generate_qr_verifactu

    result = await handle_es_generate_qr_verifactu(
        {
            "nif": "89890001K",
            "invoice_number": "12345678&G33",
            "invoice_date": "2024-01-01",
            "total_amount": 241.4,
        }
    )
    data = json.loads(result[0].text)
    assert "numserie=12345678%26G33" in data["verification_url"]
    # Exactly 3 "&" separators for 4 params — an unencoded "&" in numserie would
    # add a bogus 5th "param" and break the query string.
    assert data["verification_url"].split("?", 1)[1].count("&") == 3


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
