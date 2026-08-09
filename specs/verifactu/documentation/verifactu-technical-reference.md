# VeriFactu technical reference: transcribed provenance record

**Status:** `[Inference]`, transcribed from a technical reference supplied by the
project owner during the 2026-08 v0.6.0 fix cycle (ES-SC-10 / ES-SC-11 / ES-SC-12).
Not an official AEAT PDF or WSDL binary. Treat every value below as `[Unverified]`
until validated against a live AEAT sandbox acknowledgement, per the closing note
in `audit/2026-07-audit-es.md`.

This file exists so the huella (fingerprint) canonical string, the QR physical
spec, and the WSDL operation names used by this package have a recorded source,
per the `specs/README.md` provenance convention. When the official AEAT huella
generation note (PDF) and the VeriFactu WSDL binary are obtained, add them as
new rows in `specs/README.md`'s provenance table and supersede this file as the
primary record: do not delete it, keep it as historical context.

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

| Operation | Purpose |
|---|---|
| `RegFactuSistemaFacturacionAlta` | Submit a new invoice record (`RegistroAlta`) |
| `RegFactuSistemaFacturacionAnulacion` | Submit a cancellation record (`RegistroAnulacion`) |
| `ConsultaLRFacturasEmitidas` | Query previously submitted records and their `EstadoRegistro` |

**Note on ES-LC-10 implementation:** the bundled XSDs (`specs/verifactu/xsd/ConsultaLR.xsd`,
`RespuestaConsultaLR.xsd`) name the query request/response root elements
`ConsultaFactuSistemaFacturacion` / `RespuestaConsultaFactuSistemaFacturacion`
rather than `ConsultaLRFacturasEmitidas`. The implementation in
`tools/verifactu.py` (`_build_consulta_lr` / `_parse_consulta_lr_response`)
follows the bundled XSD element names, since they are the more authoritative,
machine-checkable primary source (the request was validated against
`ConsultaLR.xsd` locally). This reference's operation name for the query call
is recorded here as-supplied for provenance; the two are believed to refer to
the same underlying AEAT service.

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
