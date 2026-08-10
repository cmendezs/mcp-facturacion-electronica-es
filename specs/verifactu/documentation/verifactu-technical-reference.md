# VeriFactu technical reference: transcribed provenance record (SUPERSEDED)

**Status: SUPERSEDED (2026-08-09).** The official AEAT documents this file was
a stand-in for are now bundled at `specs/verifactu/documentation/` (huella spec,
QR spec, web service description) and `specs/verifactu/schemas/` (WSDL). Code
now cites those documents directly; do not use this file as a source for new
work. Kept for historical context only — see the two `⚠ WRONG, see below`
callouts inline for the two places this transcription turned out to be
incorrect once checked against the primary source.

**Original status (superseded):** `[Inference]`, transcribed from a technical
reference supplied by the project owner during the 2026-08 v0.6.0 fix cycle
(ES-SC-10 / ES-SC-11 / ES-SC-12). Not an official AEAT PDF or WSDL binary.

---

## 1. Huella (RegistroAlta): hash chaining and canonical string

- Algorithm: SHA-256, hex-encoded, **uppercase**, 64 characters.
- The canonical string is a **keyed** `campo=valor` form, fields joined by `&`,
  in this exact order:

  ```
  IDEmisorFactura=<nif>&NumSerieFactura=<serie>&FechaExpedicionFactura=<DD-MM-YYYY>&
  TipoFactura=<tipo>&CuotaTotal=<importe>&ImporteTotal=<importe>&Huella=<hex-or-empty>&
  FechaHoraHusoGenRegistro=<iso8601-with-offset>
  ```

  (Shown wrapped for readability; no line breaks in the actual string.)

- `Huella=` carries the **previous** record's huella hex string, positioned
  immediately before `FechaHoraHusoGenRegistro`. For the first (genesis) record
  in a chain, the field is still present with an **empty value**
  (`...&Huella=&FechaHoraHusoGenRegistro=...`), not omitted.
- Both `CuotaTotal` and `ImporteTotal` are included (a prior implementation
  omitted `ImporteTotal`; ES-SC-10 fixes this).

### Normalization rules

| Field | Rule |
|---|---|
| `FechaExpedicionFactura` | `DD-MM-YYYY` |
| `CuotaTotal`, `ImporteTotal` | Dot decimal separator, 2 decimals, `ROUND_HALF_UP` (see `fmt_amount` in `_helpers.py`, ES-TL-8) |
| `FechaHoraHusoGenRegistro` | ISO 8601 with timezone offset, e.g. `2025-03-15T10:30:00+01:00` |
| Concatenation | Strip stray whitespace from each value before joining |
| Encoding | UTF-8 |
| Output | Uppercase 64-character hex (SHA-256 digest) |

## 2. Huella (RegistroAnulacion): dedicated field set

> **⚠ WRONG, see below.** This transcription reused the *alta* field names
> (`IDEmisorFactura`/`NumSerieFactura`/`FechaExpedicionFactura`) for the
> anulación record. The official spec
> (`Veri-Factu_especificaciones_huella_hash_registros.pdf` v0.1.2 s3.b) uses
> **different** field names: `IDEmisorFacturaAnulada`, `NumSerieFacturaAnulada`,
> `FechaExpedicionFacturaAnulada`. A huella built with the field names below
> would fail AEAT's server-side hash check ("Aceptado con errores"). Fixed in
> `tools/verifactu.py::_compute_huella_anulacion`; golden vectors from the
> spec's own worked example (s6.3) are in `tests/test_verifactu.py`.

The anulación (cancellation) record uses a **reduced** input set over the same
keyed `campo=valor&` layout and normalization rules: it does **not** carry
`TipoFactura` or `CuotaTotal`:

```
IDEmisorFactura=<nif>&NumSerieFactura=<serie>&FechaExpedicionFactura=<DD-MM-YYYY>&
Huella=<prev-hex>&FechaHoraHusoGenRegistro=<iso8601-with-offset>
```

A prior implementation computed the anulación huella by reusing the alta
canonical string with `TipoFactura="ANULACION"` and `CuotaTotal="0.00"`, both
values that do not exist in the real field set. ES-SC-11 replaces this with a
dedicated builder.

## 3. QR code: physical and content spec

- Minimum physical size: **30mm x 40mm**.
- Symbology: **ISO/IEC 18004** (QR code).
- Error-correction level: **M**.
- Content: a URL to the AEAT verification endpoint carrying query parameters
  `nif`, `numserie`, `fecha` (as `DD-MM-YYYY`), `importe`.

## 4. WSDL operations (service namespace `.../aeat/tike/cont/ws/`)

> **⚠ WRONG, see below.** The operation names below do not match the official
> `SistemaFacturacion.wsdl`. Superseded by
> `specs/verifactu/schemas/SistemaFacturacion.wsdl` — see `specs/README.md`
> for the confirmed operation names and endpoint URLs.

| Operation | Purpose |
|---|---|
| `RegFactuSistemaFacturacionAlta` | Submit a new invoice record (`RegistroAlta`) |
| `RegFactuSistemaFacturacionAnulacion` | Submit a cancellation record (`RegistroAnulacion`) |
| `ConsultaLRFacturasEmitidas` | Query previously submitted records and their `EstadoRegistro` |

**Note on ES-LC-10 implementation (now confirmed correct):** the official WSDL
confirms a single operation, `RegFactuSistemaFacturacion`, handles both
`RegistroAlta` and `RegistroAnulacion` submissions (the XML body's root element
determines which), and `ConsultaFactuSistemaFacturacion` is the query
operation — both operations belong to the same `sfVerifactu` binding and share
one SOAP endpoint (`.../SistemaFacturacion/VerifactuSOAP`), confirming the
`tools/verifactu.py` implementation's choice of element names against the
bundled XSDs was correct, and that `VERIFACTU_CONSULTA_ENDPOINTS` should be the
*same* URL as `VERIFACTU_ENDPOINTS` rather than a separate `/ConsultaLR` path
(fixed in `_helpers.py`).

## 5. Authentication

mTLS with a **Certificado de Sello Electrónico** or **Firma Electrónica
Avanzada**, consistent with the existing `AuthMode.MTLS` usage in
`tools/verifactu.py` and `_helpers.VERIFACTU_ENDPOINTS`.

---

## Confirmed serialization decision (2026-08)

The user confirmed the huella serialization is the **keyed** `campo=valor&`
form (section 1 above), including both `CuotaTotal` and `ImporteTotal`, prior
hash immediately before the timestamp, and an empty `Huella=` value for the
genesis record. This resolved the ambiguity flagged in ES-SC-10 / ES-SC-11 of
`audit/2026-07-audit-es.md`, where the pre-fix implementation joined raw
values (no `campo=` keys) and omitted `ImporteTotal`.
