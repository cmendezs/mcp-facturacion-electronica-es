"""Live FACe sandbox integration tests.

Skipped unless FACE_TEST_PKCS12_PATH is set. See tests/integration/README.md.

FACe uses JWS-signed JWT authentication (RS256, x5c header).
Source: specs/facturae/documentation/FACe-manual-api-integradores.pdf s2.3.
"""

from __future__ import annotations

import base64
import hashlib
import json
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
    """Verify JWS token construction matches FACe manual s2.3 contract."""
    from joserfc import jwt as jose_jwt
    from joserfc._rfc7515.registry import JWSRegistry
    from joserfc.jwk import RSAKey
    from mcp_einvoicing_core.digital_signature import _load_pkcs12, load_certificate_der
    from mcp_einvoicing_core.http_client import AuthMode, BaseEInvoicingClient, JWSConfig

    cert_path = os.environ["FACE_TEST_PKCS12_PATH"]
    cert_password = os.environ.get("FACE_TEST_PKCS12_PASSWORD") or None

    clean_pem = base64.b64encode(load_certificate_der(cert_path, cert_password))
    username_claim = hashlib.sha1(clean_pem).hexdigest()

    jws_config = JWSConfig(
        cert_path=cert_path,
        cert_password=cert_password,
        ttl_seconds=300,
        extra_claims={"username": username_claim},
    )
    client = BaseEInvoicingClient(
        base_url="https://se-api-face.redsara.es",
        auth_mode=AuthMode.JWS,
        jws_config=jws_config,
    )
    token, ttl = await client._mint_jws_token()
    assert ttl == 300

    cert_info = _load_pkcs12(cert_path, cert_password)
    registry = JWSRegistry(algorithms=["RS256"])
    registry.max_header_length = 8192  # x5c embeds the full cert; default cap is 512 bytes
    decoded = jose_jwt.decode(
        token, RSAKey.import_key(cert_info.private_key.public_key()), registry=registry
    )
    assert decoded.header["alg"] == "RS256"
    assert decoded.header["typ"] == "JWT"
    assert decoded.header["x5c"] == [clean_pem.decode("ascii")]
    assert decoded.claims["username"] == username_claim
    assert decoded.claims["exp"] - decoded.claims["iat"] == 300


@pytest.mark.asyncio
async def test_face_sandbox_submit_invoice(
    minimal_invoice, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Submit a minimal signed Facturae XML to FACe sandbox.

    Requires FACE_TEST_ADMIN_UNIT / FACE_TEST_ACCOUNTING_OFFICE /
    FACE_TEST_MANAGEMENT_BODY (valid FACe sandbox unit codes for the test
    organization) in addition to FACE_TEST_PKCS12_PATH.
    """
    admin_unit = os.environ.get("FACE_TEST_ADMIN_UNIT")
    accounting_office = os.environ.get("FACE_TEST_ACCOUNTING_OFFICE")
    management_body = os.environ.get("FACE_TEST_MANAGEMENT_BODY")
    if not (admin_unit and accounting_office and management_body):
        pytest.skip("FACE_TEST_ADMIN_UNIT/ACCOUNTING_OFFICE/MANAGEMENT_BODY not set")

    from mcp_facturacion_electronica_es.config import aeat_settings
    from mcp_facturacion_electronica_es.tools.facturae import (
        build_facturae_xml,
        handle_es_submit_to_face,
    )

    monkeypatch.setattr(aeat_settings, "certificate_path", os.environ["FACE_TEST_PKCS12_PATH"])
    monkeypatch.setattr(
        aeat_settings, "certificate_password", os.environ.get("FACE_TEST_PKCS12_PASSWORD")
    )

    xml_bytes = build_facturae_xml(minimal_invoice)
    args = {
        "xml": xml_bytes.decode("utf-8"),
        "administrative_unit": admin_unit,
        "accounting_office": accounting_office,
        "management_body": management_body,
    }

    first = await handle_es_submit_to_face(args)
    pending = json.loads(first[0].text)
    token = pending.get("token")
    assert token, f"Expected a pending-confirmation response, got: {pending}"

    args["confirmation_token"] = token
    result = await handle_es_submit_to_face(args)
    data = json.loads(result[0].text)
    assert "error" not in data, data
