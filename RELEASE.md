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
