# Integration tests

These tests submit real requests to AEAT (SII) and FACe sandbox environments.
They are skipped by default and require credentials via environment variables.

## SII sandbox (test_sii_sandbox.py)

| Variable | Description |
|---|---|
| `SII_TEST_CERT_PATH` | Path to PKCS#12 (.p12) test certificate |
| `SII_TEST_CERT_PASSWORD` | Certificate password |
| `AEAT_ENV` | Must be `sandbox` (default) |

## FACe sandbox (test_face_sandbox.py)

| Variable | Description |
|---|---|
| `FACE_TEST_PKCS12_PATH` | Path to PKCS#12 (.p12) integrator certificate registered with FACe |
| `FACE_TEST_PKCS12_PASSWORD` | Certificate password |
| `FACE_ENV` | Must be `sandbox` (default) |

## Running

```bash
# Unit tests only (default)
uv run --package mcp-facturacion-electronica-es pytest

# Include integration tests
SII_TEST_CERT_PATH=/path/to/cert.p12 SII_TEST_CERT_PASSWORD=secret \
  uv run --package mcp-facturacion-electronica-es pytest -m integration
```
