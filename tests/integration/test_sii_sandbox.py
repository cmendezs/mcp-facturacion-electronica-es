"""Live SII sandbox integration tests.

Skipped unless SII_TEST_CERT_PATH is set. See tests/integration/README.md.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("SII_TEST_CERT_PATH"),
        reason="SII_TEST_CERT_PATH not set",
    ),
]


@pytest.mark.asyncio
async def test_sii_sandbox_submit_issued(minimal_invoice) -> None:
    """Submit a minimal issued-invoice envelope to the SII sandbox."""
    from mcp_facturacion_electronica_es.tools.sii import build_sii_issued_record

    envelope = build_sii_issued_record(minimal_invoice)
    assert len(envelope) > 0
    # [NEED: complete with actual SOAP submission once sandbox cert is available]


@pytest.mark.asyncio
async def test_sii_sandbox_query_issued() -> None:
    """Query issued invoices from SII sandbox."""
    # [NEED: complete with actual SOAP query once sandbox cert is available]
