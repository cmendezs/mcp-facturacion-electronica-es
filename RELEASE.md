# Release Process for mcp-facturacion-electronica-es

This document describes how to release a new version of `mcp-facturacion-electronica-es` to PyPI and the official MCP registry.

## One-Time Setup Requirements

**PyPI Trusted Publishing:**
PyPI publishing is fully automated via OIDC (no token stored). The Trusted Publisher is configured on PyPI under `cmendezs/mcp-facturacion-electronica-es`, workflow `publish.yml`, environment `pypi`. No `.env` or secret needed.

**MCP Publisher CLI:**
Binary installed at `~/.local/bin/mcp-publisher` (already in `PATH`). To update:
```bash
curl -L "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_darwin_arm64.tar.gz" \
  | tar xzf - -C ~/.local/bin/
```

**MCP Registry Authentication:**
Authenticate once with GitHub (device flow):
```bash
mcp-publisher login github
```

## Release Steps

**Step 1 — Version bump:** update `version` in `pyproject.toml` and `server.json` (top-level and `packages[].version`).

**Step 2 — Commit, tag and push:**
```bash
git add pyproject.toml server.json
git commit -m "release: v{VERSION} — {summary}"
git push origin main
git tag v{VERSION}
git push origin v{VERSION}
```
GitHub Actions publishes to PyPI automatically on tag push.

**Step 3 — MCP registry:**
```bash
mcp-publisher publish
```

## Changelog

### [0.6.0] - 2026-08-09
#### Added
- **[ES-LC-10]** `es__query_verifactu_status` tool: queries `EstadoRegistro` for an
  already-submitted VERI\*FACTU record (`ConsultaFactuSistemaFacturacion` /
  `ConsultaLR.xsd`), for use after a `deferred` result from
  `es__submit_verifactu_to_aeat`.
- **[ES-TL-9]** `tax_type` (IVA/IPSI/IGIC) derivation for Facturae generation.
- **[ES-TL-10]** Recargo de Equivalencia support in Facturae (`recargo_equivalencia_rate`
  / `recargo_equivalencia_amount`).
- **[ES-TL-11]** IRPF withholding emitted in `TaxesWithheld` (`irpf_rate`).
- QR response (`es__generate_qr_verifactu`) now includes physical-spec metadata
  (`error_correction`, `size`).

#### Fixed
- **[ES-LC-14]** FACe submission and status tools rewritten from an incorrect OAuth2
  client-credentials flow to JWS-signed JWT auth (RS256, `x5c` header), per
  `FACe-manual-api-integradores.pdf` s2.3. Reuses the existing AEAT certificate; no
  separate FACe credentials required. Depends on core v1.16.0's new `AuthMode.JWS`.
- **[ES-TL-8]** `fmt_amount` now rounds HALF_UP (was Python's default HALF_EVEN),
  matching the Factura-e/VeriFactu spec.
- **[ES-SC-10]** VeriFactu Huella (`RegistroAlta`) rebuilt to the confirmed keyed
  canonical-string form.
- **[ES-SC-11]** VeriFactu Huella (`RegistroAnulacion`) now uses a dedicated field set
  instead of reusing the `RegistroAlta` canonical string.

#### Security
- **[ES-SH-6]** `cert_password` removed as a `es__sign_facturae_xades` tool argument;
  the certificate password is read from `AEAT_CERTIFICATE_PASSWORD` instead, avoiding
  plaintext credential exposure in LLM context/logs.
- **[ES-SH-7]** FACe responses are parsed to a structured, non-sensitive subset before
  reaching the LLM, instead of echoing the raw response.

#### Docs
- **[ES-SC-12]** VeriFactu technical reference (huella, QR, WSDL ops) transcribed into
  `specs/verifactu/documentation/` with provenance.

#### Dependencies
- Core pin raised to `mcp-einvoicing-core>=1.16.0,<2.0.0`.

### [0.5.0] - 2026-06-26
#### Endpoint verification and sandbox scaffolding (Sprint 4)
- **[ES-LC-10]** Full SII endpoint rewrite from bundled WSDLs: old wrong URLs (www7, BURT-JDIT)
  replaced with canonical primary/secondary failover pairs from `SuministroFactEmitidas.wsdl`
  and `SuministroFactRecibidas.wsdl`.
- **[ES-LC-11]** Structural SII envelope validation (`test_sii_envelope_structure.py`, 12 tests).
  Integration test stubs for SII and FACe sandbox (auto-skip without credentials).
- **[ES-LC-12]** FACe base URLs rewritten from integrator manual: sandbox =
  `se-api-face.redsara.es`, production = `api.face.gob.es`.
- **[ES-LC-13]** FACe auth investigation: confirmed JWS-signed JWT (RS256, x5c header),
  not OAuth2. Filed ES-LC-14 for the auth rewrite.
- **[ES-LC-8/9]** VeriFactu endpoints: namespace-consistent with bundled XSDs but
  unverified from authoritative source (AEAT technical guide not in bundled specs).

#### Audit hardening (Sprint 5)
- **[ES-AUD-1]** Refreshed `_INTENTIONAL_OVERRIDES` and `_ES_MODULES` in
  `audit/audit_vs_core.py`: 107 CHECK 1 warnings reduced to 0.
- **[ES-AUD-2]** Resolved-stale: no hand-rolled PEP 440 version parser found.
- **[ES-CYC-1]** Added `b2b_format_resolved: false` flag to mandate applicability response.

#### CI fix
- Fixed `publish.yml` ruff/mypy paths for `src/` layout (was causing E902 on every CI run).

### [0.2.0] - 2026-06-02
#### Fixed / Added
- **[ES-LC-4] BLOCKING:** `RegistroAnterior` in VeriFactu now emits all 4 required
  `EncadenamientoFacturaAnteriorType` fields (`IDEmisorFactura`, `NumSerieFactura`,
  `FechaExpedicionFactura`, `Huella`). New optional params `previous_emisor_nif`,
  `previous_num_serie`, `previous_fecha` added to the generate/cancel tools.
- **[ES-LC-2] BLOCKING:** `handle_es_query_sii_status` replaced non-functional REST GET
  stub with a proper SOAP `ConsultaFactInformadasEmitidas` / `ConsultaLRFacturasRecibidas`
  envelope builder.
- **[ES-SC-1] HIGH:** `_FACTURAE_NS` corrected to
  `http://www.facturae.gob.es/formato/Versiones/Facturaev3_2_2.xml`. XSD validation path
  updated to `specs/facturae/xsd/Facturaev3_2_2.xml`.
- **[ES-SC-7] HIGH:** VeriFactu namespaces applied to all XML elements.
  `TipoHuella="01"` (SHA-256) added to `RegistroAlta` and `RegistroAnulacion`.
  `IdSistemaInformatico` capped to 2 chars (`TextMax2Type`).
- **[ES-SC-3] MEDIUM:** Explicit `logger.warning` emitted before signing when
  `FACTURAE_POLICY_HASH` is `None`.
- **[ES-SH-4] HIGH:** `call_tool` redacts `cert_password`, `certificate_password`,
  `client_secret`, and other credential keys before debug logging.
- **[ES-SH-2] HIGH partial:** `handle_es_submit_verifactu_to_aeat` returns structured
  fields (`EstadoEnvio`, `CSV`, etc.) instead of raw XML.
- TicketBAI removed (out of scope, confirmed 2026-05-31): `tools/ticketbai.py` deleted;
  `TicketBAISettings`, `TicketBAIProvince`, `SpanishRegime.TICKETBAI/NATICKET`,
  `TICKETBAI_ENDPOINTS`, `TICKETBAI_POLICY_IDS`, `ticketbai_env()` removed;
  `server.json` TicketBAI env vars removed.

### [0.1.0]
#### Added
- Initial release: Factura-e and VeriFactu support; joined uv workspace as a formal member.

---

## Notes

- The MCP registry does **not** sync automatically with PyPI or GitHub — step 3 is required for every release.
- The `server.json` description field must be **≤ 100 characters**.
- PyPI rejects re-uploads of the same version — always bump before tagging.
