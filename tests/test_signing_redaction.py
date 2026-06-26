"""Tests for PKCS#12 password log redaction (ES-SH-3).

Verifies that loading a PKCS#12 with a wrong password does not leak the
password string into log records.
"""

from __future__ import annotations

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
