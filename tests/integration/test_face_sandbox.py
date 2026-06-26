"""Live FACe sandbox integration tests.

Skipped unless FACE_TEST_PKCS12_PATH is set. See tests/integration/README.md.

FACe uses JWS-signed JWT authentication (RS256, x5c header).
Source: specs/facturae/documentation/FACe-manual-api-integradores.pdf s2.3.
[NEED: ES-LC-14 — implement JWS token minting before these tests can run]
"""

from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("FACE_TEST_PKCS12_PATH"),
        reason="FACE_TEST_PKCS12_PATH not set",
    ),
]


@pytest.mark.asyncio
async def test_face_sandbox_jws_token_structure() -> None:
    """Verify JWS token construction matches FACe manual contract."""
    # [NEED: ES-LC-14 — test JWS token minting (header with x5c, payload with
    #  username=SHA1(PEM), iat, exp; RS256 signature)]


@pytest.mark.asyncio
async def test_face_sandbox_submit_invoice() -> None:
    """Submit a minimal Facturae XML to FACe sandbox."""
    # [NEED: ES-LC-14 — requires JWS auth implementation]
