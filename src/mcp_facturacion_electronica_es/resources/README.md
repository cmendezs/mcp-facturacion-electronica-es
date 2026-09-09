# mcp-facturacion-electronica-es — Runtime resources (shipped in the wheel)

XSD schemas this package loads at import/call time. Moved here from the repo-root `specs/`
directory 2026-09-09 (CORE-1, `audit/2026-09-audit-core.md`): the previous locations resolved
outside the installed package once pip-installed from a wheel (or, for `facturae/`, resolved
incorrectly even in a source checkout — see below), since only
`src/mcp_facturacion_electronica_es/` is packaged
(`[tool.hatch.build.targets.wheel]` in `pyproject.toml`). `specs/` (repo root) still holds the
reference-only material (documentation, examples, WSDLs) that nothing in `src/` reads at
runtime — see [`../../../specs/README.md`](../../../specs/README.md).

Provenance (authority URL, retrieval date) for both files is recorded in `specs/README.md`'s
"Sources and versions" table, not duplicated here.

| File | Loaded by | Note |
|---|---|---|
| `verifactu/SuministroLR.xsd` | `tools/verifactu.py::es__validate_verifactu_record` | Root schema for VeriFactu submissions. The old four-`.parent`-hop path only broke once packaged into a wheel — CORE-1's "silent downgrade" instance, `validation_mode` fell back to `"structural"` with no test catching it. |
| `facturae/Facturaev3_2_2.xml` | `tools/facturae.py::es__validate_facturae` | Factura-e 3.2.2 root schema (`.xml` extension is correct — the file's own `targetNamespace` URI ends in `Facturaev3_2_2.xml`). The old three-`.parent`-hop path landed on `src/` and never resolved under any layout, checkout or installed — found and fixed in the same CORE-1 pass, not previously reported. |

## Update process

When AEAT or the Facturae maintainers publish a new schema version, replace the file here
directly (not in `specs/`) and update `specs/README.md`'s version/retrieval columns to match.
