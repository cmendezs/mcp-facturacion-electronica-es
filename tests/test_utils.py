"""Tests for utility tools: regime detection, compliance status, mandate applicability."""

from __future__ import annotations

import pytest

from mcp_facturacion_electronica_es.models.es import EntityType, SpanishRegime
from mcp_facturacion_electronica_es.tools.utils import (
    _SII_TURNOVER_THRESHOLD_EUR,
    _detect_regime,
    _is_out_of_scope_territory,
)

# ---------------------------------------------------------------------------
# _detect_regime (pure Python — no network, no XML)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "province_code, enrolled, expected",
    [
        # Basque provinces and Navarre — foral systems out of scope;
        # _detect_regime now returns VERIFACTU (territory check is via _is_out_of_scope_territory)
        ("01", False, SpanishRegime.VERIFACTU),  # Alava — TicketBAI out of scope
        ("01", True, SpanishRegime.VERIFACTU_SII),
        ("20", False, SpanishRegime.VERIFACTU),  # Gipuzkoa — TicketBAI out of scope
        ("48", False, SpanishRegime.VERIFACTU),  # Bizkaia — TicketBAI out of scope
        ("31", False, SpanishRegime.VERIFACTU),  # Navarre — NaTicket out of scope
        ("31", True, SpanishRegime.VERIFACTU_SII),
        # All others, enrolled in SII → VERIFACTU_SII
        ("28", True, SpanishRegime.VERIFACTU_SII),  # Madrid
        ("08", True, SpanishRegime.VERIFACTU_SII),  # Barcelona
        # All others, not enrolled → VERIFACTU
        ("28", False, SpanishRegime.VERIFACTU),
        ("46", False, SpanishRegime.VERIFACTU),  # Valencia
    ],
)
def test_detect_regime(province_code: str, enrolled: bool, expected: SpanishRegime) -> None:
    assert _detect_regime(province_code, enrolled) == expected


def test_out_of_scope_territory_basque() -> None:
    """Basque provinces should be flagged as out of scope."""
    for code in ["01", "20", "48"]:
        note = _is_out_of_scope_territory(code)
        assert note is not None
        assert "TicketBAI" in note
        assert "out of scope" in note


def test_out_of_scope_territory_navarre() -> None:
    note = _is_out_of_scope_territory("31")
    assert note is not None
    assert "NaTicket" in note


def test_out_of_scope_territory_none_for_aeat() -> None:
    """AEAT-scope provinces should return None."""
    assert _is_out_of_scope_territory("28") is None  # Madrid
    assert _is_out_of_scope_territory("08") is None  # Barcelona


def test_detect_regime_high_turnover_no_sii() -> None:
    """High turnover alone does not trigger VERIFACTU_SII; formal enrolment is required."""
    regime = _detect_regime(
        "28", enrolled_in_sii=False, annual_turnover_eur=_SII_TURNOVER_THRESHOLD_EUR + 1
    )
    assert regime == SpanishRegime.VERIFACTU


def test_detect_regime_high_turnover_with_sii() -> None:
    regime = _detect_regime(
        "28", enrolled_in_sii=True, annual_turnover_eur=_SII_TURNOVER_THRESHOLD_EUR + 1
    )
    assert regime == SpanishRegime.VERIFACTU_SII


# ---------------------------------------------------------------------------
# Tool handler integration (async, pure logic — no network, no XML)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_detect_regional_regime_madrid() -> None:
    from mcp_facturacion_electronica_es.tools.utils import handle_es_detect_regional_regime

    result = await handle_es_detect_regional_regime({"province_code": "28"})
    assert len(result) == 1
    import json

    data = json.loads(result[0].text)
    assert data["regime"] == SpanishRegime.VERIFACTU
    assert data["province_code"] == "28"
    assert data["enrolled_in_sii"] is False


@pytest.mark.asyncio
async def test_handle_detect_regional_regime_araba() -> None:
    """Araba uses TicketBAI (out of scope) — tool returns VERIFACTU + out_of_scope_warning."""
    from mcp_facturacion_electronica_es.tools.utils import handle_es_detect_regional_regime

    result = await handle_es_detect_regional_regime({"province_code": "01"})
    import json

    data = json.loads(result[0].text)
    assert data["regime"] == SpanishRegime.VERIFACTU
    assert "out_of_scope_warning" in data
    assert "TicketBAI" in data["out_of_scope_warning"]


@pytest.mark.asyncio
async def test_handle_detect_regional_regime_missing_param() -> None:
    from mcp_facturacion_electronica_es.tools.utils import handle_es_detect_regional_regime

    result = await handle_es_detect_regional_regime({})
    import json

    data = json.loads(result[0].text)
    assert "error" in data


@pytest.mark.asyncio
async def test_handle_get_compliance_status_is_madrid() -> None:
    from mcp_facturacion_electronica_es.tools.utils import handle_es_get_compliance_status

    result = await handle_es_get_compliance_status({"entity_type": "IS", "province_code": "28"})
    import json

    data = json.loads(result[0].text)
    assert data["entity_type"] == EntityType.IS
    assert data["detected_regime"] == SpanishRegime.VERIFACTU
    assert len(data["applicable_systems"]) >= 1
    # VERI*FACTU for IS → deadline January 2027
    deadlines = [s.get("deadline", "") for s in data["applicable_systems"]]
    assert "2027-01-01" in deadlines


@pytest.mark.asyncio
async def test_handle_get_compliance_status_basque_out_of_scope() -> None:
    """Gipuzkoa uses TicketBAI (out of scope) — tool returns VERIFACTU + out_of_scope_warning."""
    from mcp_facturacion_electronica_es.tools.utils import handle_es_get_compliance_status

    result = await handle_es_get_compliance_status(
        {"entity_type": "IS", "province_code": "20"}  # Gipuzkoa
    )
    import json

    data = json.loads(result[0].text)
    assert data["detected_regime"] == SpanishRegime.VERIFACTU
    assert "out_of_scope_warning" in data


@pytest.mark.asyncio
async def test_handle_check_b2b_mandate_applicability_sii_exclusion() -> None:
    from mcp_facturacion_electronica_es.tools.b2b import handle_es_check_b2b_mandate_applicability

    result = await handle_es_check_b2b_mandate_applicability(
        {
            "annual_turnover_eur": 10_000_000,
            "tax_address_province_code": "28",
            "enrolled_in_sii": True,
            "entity_type": "IS",
        }
    )
    import json

    data = json.loads(result[0].text)
    assert data["primary_regime"] == SpanishRegime.VERIFACTU_SII
    assert data["sii_exclusion_applies"] is True


@pytest.mark.asyncio
async def test_handle_parse_aeat_response_verifactu() -> None:
    from mcp_facturacion_electronica_es.tools.utils import handle_es_parse_aeat_response

    xml = """<?xml version="1.0" encoding="UTF-8"?>
<RespuestaRegFactuSistemaFacturacion>
  <EstadoEnvio>Correcto</EstadoEnvio>
  <CSV>ABC123XYZ</CSV>
</RespuestaRegFactuSistemaFacturacion>"""

    result = await handle_es_parse_aeat_response({"xml": xml, "response_type": "verifactu"})
    import json

    data = json.loads(result[0].text)
    assert data["success"] is True
    assert data["estado_envio"] == "Correcto"
    assert data["csv"] == "ABC123XYZ"


@pytest.mark.asyncio
async def test_handle_parse_aeat_response_invalid_xml() -> None:
    from mcp_facturacion_electronica_es.tools.utils import handle_es_parse_aeat_response

    result = await handle_es_parse_aeat_response({"xml": "not xml at all <<<"})
    import json

    data = json.loads(result[0].text)
    assert "error" in data


# ---------------------------------------------------------------------------
# Batch 2: FACe URL constants
# ---------------------------------------------------------------------------


def test_face_base_urls_verified() -> None:
    from mcp_facturacion_electronica_es._helpers import FACE_BASE_URLS

    assert "sandbox" in FACE_BASE_URLS
    assert "production" in FACE_BASE_URLS
    assert "face" in FACE_BASE_URLS["sandbox"].lower()
    assert "face" in FACE_BASE_URLS["production"].lower()
