"""Tests for utility tools: regime detection, compliance status, mandate applicability."""

from __future__ import annotations

import pytest

from mcp_facturacion_electronica_es._helpers import fmt_amount
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


# ---------------------------------------------------------------------------
# fmt_amount: HALF_UP rounding (ES-TL-8)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2.665", "2.67"),
        ("1.005", "1.01"),
        ("0.125", "0.13"),
        ("2.664", "2.66"),
        ("100", "100.00"),
        (0, "0.00"),
        ("-1.005", "-1.01"),
    ],
)
def test_fmt_amount_half_up(value: str | int, expected: str) -> None:
    assert fmt_amount(value) == expected


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

    # RD 238/2026: syntaxes confirmed, public solution still pending on the OM.
    assert data["b2b_syntaxes_confirmed"] == ["CII", "UBL", "EDIFACT", "Facturae"]
    assert data["b2b_syntaxes_implemented"] == ["UBL", "Facturae"]
    assert data["b2b_public_solution_pending"] is True

    # Turnover (10M) exceeds the 8M€ B2B threshold (distinct from the 6M€ SII
    # threshold above) -> 12-month post-OM timeline.
    timeline = data["b2b_mandate_timeline"]
    assert timeline["this_taxpayer_months_after_om"] == 12
    assert timeline["over_8m_turnover_months_after_om"] == 12
    assert timeline["other_taxpayers_months_after_om"] == 24
    assert timeline["om_entry_into_force_date"] == "[Unverified]"
    # No absolute mandate dates should be emitted anywhere in the payload.
    assert "2026-10" not in json.dumps(data)
    assert "2027" not in json.dumps(data["b2b_mandate_timeline"])


@pytest.mark.asyncio
async def test_handle_check_b2b_mandate_applicability_below_8m_threshold() -> None:
    from mcp_facturacion_electronica_es.tools.b2b import handle_es_check_b2b_mandate_applicability

    result = await handle_es_check_b2b_mandate_applicability(
        {
            "annual_turnover_eur": 1_000_000,
            "tax_address_province_code": "28",
            "enrolled_in_sii": False,
            "entity_type": "IS",
        }
    )
    import json

    data = json.loads(result[0].text)
    timeline = data["b2b_mandate_timeline"]
    assert timeline["this_taxpayer_months_after_om"] == 24


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
    assert FACE_BASE_URLS["sandbox"] == "https://se-api-face.redsara.es"
    assert FACE_BASE_URLS["production"] == "https://api.face.gob.es"


def test_sii_endpoints_match_bundled_wsdl() -> None:
    """"sello" (www10/prewww10) is the company-seal-certificate variant of the
    same operation per the bundled WSDL's own port names
    (SuministroFactEmitidasSello / SuministroFactRecibidasSello) — not a
    primary/secondary failover pair. Renamed from "secondary" after the same
    mislabeling was found and fixed on the VeriFactu endpoint map."""
    from mcp_facturacion_electronica_es._helpers import (
        SII_ISSUED_ENDPOINTS,
        SII_RECEIVED_ENDPOINTS,
    )

    assert SII_ISSUED_ENDPOINTS["production"]["primary"] == (
        "https://www1.agenciatributaria.gob.es/wlpl/SSII-FACT/ws/fe/SiiFactFEV1SOAP"
    )
    assert SII_ISSUED_ENDPOINTS["production"]["sello"] == (
        "https://www10.agenciatributaria.gob.es/wlpl/SSII-FACT/ws/fe/SiiFactFEV1SOAP"
    )
    assert SII_ISSUED_ENDPOINTS["sandbox"]["primary"] == (
        "https://prewww1.aeat.es/wlpl/SSII-FACT/ws/fe/SiiFactFEV1SOAP"
    )
    assert SII_RECEIVED_ENDPOINTS["production"]["primary"] == (
        "https://www1.agenciatributaria.gob.es/wlpl/SSII-FACT/ws/fr/SiiFactFRV1SOAP"
    )
    assert SII_RECEIVED_ENDPOINTS["sandbox"]["primary"] == (
        "https://prewww1.aeat.es/wlpl/SSII-FACT/ws/fr/SiiFactFRV1SOAP"
    )
    for env in ("sandbox", "production"):
        assert "primary" in SII_ISSUED_ENDPOINTS[env]
        assert "sello" in SII_ISSUED_ENDPOINTS[env]
        assert "primary" in SII_RECEIVED_ENDPOINTS[env]
        assert "sello" in SII_RECEIVED_ENDPOINTS[env]
