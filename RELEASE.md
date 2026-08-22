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

### [0.8.0] - 2026-08-22

ARCH-CONVERGE-ES: server-wiring convergence to `EInvoicingMCPServer`, the fourth and final
convergence item after BE/PL/DE. Pure internal wiring refactor; no functional or regulatory
behavior changed.

#### Changed
- `server.py` rewritten from the raw `mcp.server.Server` protocol API (hand-rolled
  `types.Tool` JSON schemas, `handle_es_*` functions taking `arguments: dict` and returning
  `list[types.TextContent]`) to `EInvoicingMCPServer`/`register_plugin`.
- All 20 tools across `tools/{verifactu,facturae,sii,b2b,utils}.py` converted from
  `TOOL_ES_*`/`handle_es_*` pairs to typed FastMCP functions taking direct keyword
  parameters and returning plain dicts. Tool names are unchanged
  (`es__generate_verifactu_record`, etc.): the Python function names were set identically
  to the published tool names to protect the existing public tool-name surface. Docstrings
  kept in Spanish, matching this package's established convention.
- `_helpers.py`'s `ok()`/`err()` now return plain dicts instead of wrapping in
  `list[types.TextContent]`.
- `audit/audit_vs_core.py`: `EInvoicingMCPServer` removed from the "unused" override list
  (now genuinely used); CHECK 2 rewritten from `TOOL_ES_*.name` lookups to plain-function
  `hasattr` checks; CHECK 5's `_ALL_TOOLS`/`_TOOL_HANDLERS` dict-sync check replaced with
  the `server.mcp` `EInvoicingMCPServer`-instance check.

#### Not changed
- No Peppol tool plugin mounted, unlike BE/PL/DE. ES has no Peppol involvement
  (SII/VeriFactu/FACe are domestic AEAT systems only); documented in the audit script's
  own `_INTENTIONAL_OVERRIDES` rationale.

#### Fixed
- Two pre-existing, unrelated audit warnings closed, surfaced by the core 1.16.2 to 1.19.0
  version installed in the dev venv: `Union` (`pdf` module re-export) and `resolve_naptr`
  (`peppol` module).

146 tests passing / 4 skipped, ruff clean, audit gate PASS 0 blocking / 0 warnings. Server
boot-checked directly (`mcp.mcp.list_tools()`): all 20 tools registered under their
original names.

### [0.7.0] - 2026-08-13

RD 238/2026 (BOE-A-2026-7295), the reglamento developing the Ley 18/2022 "Crea y Crece"
B2B e-invoicing mandate, was published 2026-03-31 and entered into force 2026-04-20. This
release wires the now-confirmable parts of it into `tools/b2b.py`; the public-solution
technical package (XSD/WSDL/API, unique-code insertion, UBL usage terms) remains deferred
to the still-pending Orden Ministerial (Hacienda) per Disp. final tercera.

#### Changed
- **[ES-CYC-1]** `es__check_b2b_mandate_applicability` no longer returns the flat
  `b2b_format_resolved: False` / `b2b_format_note` pair. It now returns:
  - `b2b_syntaxes_confirmed`: the four EN 16931 syntaxes admitted by RD 238/2026 art. 7.1
    (CII, UBL, EDIFACT, Facturae).
  - `b2b_syntaxes_implemented`: `["UBL", "Facturae"]` — this package's actual emitters.
  - `b2b_public_solution_pending: true` — the AEAT public solution still awaits the OM.
  - `b2b_mandate_timeline`: an OM-relative 12/24-month timeline keyed off the 8M EUR
    turnover threshold (art. 121 Ley 37/1992, RD 238/2026 Disp. final cuarta) — distinct
    from the 6M EUR SII threshold used elsewhere in this handler. No absolute dates are
    emitted; the OM's own entry-into-force date is unverified.
  - `b2b_format_note` now cites the confirmed UBL faithful-copy obligation (art. 6.2),
    advanced-signature requirement (art. 7.3), and unique invoice-code rule (art. 7.5).
- `es__generate_b2b_einvoice_es` description and response `disclaimer` updated to cite
  RD 238/2026 instead of "reglamento pendiente de publicación".
- `build_ubl_invoice`: added a comment flagging `CustomizationID`/`ProfileID` as
  `[Inference: Peppol BIS 3.0]` pending the OM's UBL usage terms — no emitter rewrite yet.
- `B2BFormat` enum comment notes CII/EDIFACT are legally admitted (art. 7.1) but have no
  emitter in this package.

#### Added
- Bundled `specs/crea-y-crece/documentation/BOE-A-2026-7295-consolidado.pdf` (the
  consolidated RD 238/2026 text), alongside the existing Ley 18/2022 primary-law PDF.
- Two new tests covering the confirmed-syntax response shape and both branches of the
  8M EUR-threshold mandate timeline.

All article citations verified directly against the consolidated BOE-A-2026-7295 text.
146 tests passing / 4 skipped, ruff clean, audit gate PASS 0 blocking / 0 warnings.

### [0.6.1] - 2026-08-09

The project owner supplied the official AEAT VeriFactu documents (huella spec, QR spec, web
service description, WSDL, XSDs) that ES-SC-12/ES-LC-8/ES-LC-9 had been waiting on. Verifying the
already-published v0.6.0 against them confirmed the RegistroAlta huella (ES-SC-10) byte-for-byte
correct, but found several regressions/gaps, all confirmed against the official documents rather
than inference.

#### Fixed
- **[ES-SC-14] (HIGH)** Anulación huella now uses the official `*Anulada` field names
  (`IDEmisorFacturaAnulada`/`NumSerieFacturaAnulada`/`FechaExpedicionFacturaAnulada`), not the
  RegistroAlta field names — a regression within the earlier ES-SC-11 fix. Golden vectors from the
  huella spec's own worked examples added to `test_verifactu.py`.
- **[ES-SC-16] (HIGH)** `RegistroAnulacion`'s top-level `<IDFactura>` block used the RegistroAlta
  element names instead of the XSD-required `*Anulada` names (`IDFacturaExpedidaBajaType`) — every
  `es__cancel_verifactu_record` output was structurally XSD-invalid, independent of ES-SC-14. New
  `_build_id_factura_anulada()` builder.
- **[ES-SC-15] (MEDIUM)** `es__generate_qr_verifactu` hardcoded the sandbox host and did not
  URL-encode parameter values; now switches sandbox/production via `AEAT_ENV` and encodes with
  `quote_plus`.
- **[ES-LC-8] / [ES-LC-9] (MEDIUM)** VeriFactu SOAP endpoint paths were guessed. The official WSDL
  confirms both `RegFactuSistemaFacturacion` and `ConsultaFactuSistemaFacturacion` share one
  endpoint (`.../SistemaFacturacion/VerifactuSOAP`), and that `www10`/`prewww10` are the
  Sello-certificate (not failover-secondary) variant.
- **[ES-LC-12] (LOW)** Re-chaining on rejected huella now enforced, not just documented.
  `es__submit_verifactu_to_aeat` returns a new `chain` block: `safe_to_chain_from` is only
  populated when `EstadoRegistro` is `Correcto`/`AceptadoConErrores` (per AEAT huella spec s7);
  otherwise `None` with an explicit warning, or a note to poll `es__query_verifactu_status` for a
  deferred result.
- **[ES-LC-15] (MEDIUM)** `es__validate_verifactu_record`'s XSD path used 3 `.parent` hops (landed
  on `src/`, not the package root) — silently degraded to structural-only validation on every
  call, which is why ES-SC-16 was never caught. Fixed to 4 hops.
- **[ES-SC-17] (LOW)** The same handler's structural-only checklist was RegistroAlta-only,
  false-flagging `TipoFactura`/`CuotaTotal`/`ImporteTotal` as missing on every valid
  RegistroAnulacion. Now branches on registro type.
- **[ES-LC-16] (LOW)** `SII_ISSUED_ENDPOINTS`/`SII_RECEIVED_ENDPOINTS` `"secondary"` key renamed
  to `"sello"`. The www10/prewww10 host is not a failover secondary for www1/prewww1: the bundled
  WSDLs name its ports `SuministroFactEmitidasSello` / `SuministroFactRecibidasSello`, i.e. the
  company-seal-certificate variant of the same operation. Documentation/labeling only — `sii.py`
  only ever reads `endpoints[env]["primary"]`, so there is no behavior change.
- **[ES-LC-11] (LOW)** Real gap was in core, not ES: `signer_service.py` had no 429/503 retry,
  unlike `BaseEInvoicingClient._request`. Fixed in `mcp-einvoicing-core` v1.16.2 (no ES-side code
  change); core floor pin raised to `>=1.16.2`.

Official AEAT documents bundled into `specs/verifactu/` (`documentation/`, `schemas/`,
`examples/`) with full provenance in `specs/README.md`; the prior user-supplied transcription
marked superseded with inline callouts.

145 tests passing (134 + 11 new) / 4 skipped, ruff clean, audit gate PASS 0 blocking / 0 warnings.

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
