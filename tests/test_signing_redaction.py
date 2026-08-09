"""Tests for PKCS#12 password log redaction (ES-SH-3).

Verifies that loading a PKCS#12 with a wrong password does not leak the
password string into log records.
"""

from __future__ import annotations

import json
import logging
import tempfile

import pytest


def test_pkcs12_wrong_password_not_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    """Load a PKCS#12 with wrong password; assert password never appears in logs."""
    from mcp_einvoicing_core.digital_signature import XAdESEPESSigner, XAdESSignerConfig

    secret_password = "s3cr3t_P@ssw0rd_N3v3r_L34k"

    with tempfile.NamedTemporaryFile(suffix=".p12") as tmp:
        tmp.write(b"\x00" * 64)
        tmp.flush()

        with caplog.at_level(logging.DEBUG):
            try:
                config = XAdESSignerConfig(
                    pkcs12_path=tmp.name,
                    pkcs12_password=secret_password,
                )
                XAdESEPESSigner(config)
            except Exception:
                pass

    for record in caplog.records:
        msg = record.getMessage()
        assert secret_password not in msg, f"Password leaked in log message: {msg!r}"
        if record.exc_info and record.exc_info[1]:
            exc_str = str(record.exc_info[1])
            assert secret_password not in exc_str, f"Password leaked in exception: {exc_str!r}"


def test_sign_facturae_xades_schema_has_no_cert_password() -> None:
    """ES-SH-6: cert_password must never be an LLM-facing tool argument.

    Direct-mode signing reads the password only from AEATSettings
    (AEAT_CERTIFICATE_PASSWORD), not from MCP tool arguments.
    """
    from mcp_facturacion_electronica_es.tools.facturae import TOOL_ES_SIGN_FACTURAE_XADES

    assert "cert_password" not in TOOL_ES_SIGN_FACTURAE_XADES.inputSchema["properties"]


@pytest.mark.asyncio
async def test_handle_sign_facturae_xades_ignores_cert_password_argument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even if a caller passes cert_password, direct-mode signing must source
    the password only from AEATSettings, never from the tool argument."""
    import mcp_einvoicing_core.confirmation as confirmation_module

    from mcp_facturacion_electronica_es.config import aeat_settings
    from mcp_facturacion_electronica_es.tools import facturae as facturae_module

    monkeypatch.setattr(confirmation_module, "_HITL_DISABLED", True)
    monkeypatch.setattr(aeat_settings, "certificate_password", "from-settings-only")
    monkeypatch.setattr(
        facturae_module.SignerClient, "is_configured", staticmethod(lambda: False)
    )

    captured_configs: list = []

    class _FakeSigner:
        def __init__(self, config):
            captured_configs.append(config)

        def sign(self, xml_bytes: bytes) -> bytes:
            return b'<Facturae Signed="true"/>'

    monkeypatch.setattr(facturae_module, "XAdESEPESSigner", _FakeSigner)

    result = await facturae_module.handle_es_sign_facturae_xades(
        {
            "xml": "<Facturae/>",
            "cert_path": "/nonexistent/cert.p12",
            "cert_password": "should-be-ignored",
        }
    )
    data = json.loads(result[0].text)
    assert "error" not in data
    assert len(captured_configs) == 1
    assert captured_configs[0].cert_password == "from-settings-only"
