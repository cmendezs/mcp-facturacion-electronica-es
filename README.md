# mcp-facturacion-electronica-es

[![PyPI version](https://img.shields.io/pypi/v/mcp-facturacion-electronica-es.svg)](https://pypi.org/project/mcp-facturacion-electronica-es/)
[![Python](https://img.shields.io/pypi/pyversions/mcp-facturacion-electronica-es.svg)](https://pypi.org/project/mcp-facturacion-electronica-es/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-brightgreen.svg)](https://modelcontextprotocol.io)
[![Audit status](https://img.shields.io/badge/audit-PENDING%20IMPLEMENTATION-orange.svg)](#phase-1-audit-summary)

---

## Introducción

**mcp-facturacion-electronica-es** es un servidor MCP (Model Context Protocol) especializado
en facturación electrónica española. Proporciona herramientas para generar, validar y enviar
facturas electrónicas bajo los seis sistemas coexistentes en España: VERI\*FACTU, Facturae/FACe,
SII, TicketBAI (País Vasco), NaTicket (Navarra) y las obligaciones B2B de la Ley 18/2022
"Crea y Crece". El servidor está construido sobre `mcp-einvoicing-core`, la librería base
compartida con `mcp-facture-electronique-fr` (Francia, XP Z12-013) y `mcp-einvoicing-be`
(Bélgica, Peppol BIS 3.0).

**For non-Spanish developers:** Spain operates one of the most complex e-invoicing landscapes
in Europe — six overlapping systems apply depending on taxpayer size, sector, and region.
VERI\*FACTU (Royal Decree 1007/2023, Order HAC/1177/2024) is the forthcoming mandatory
real-time invoice registry for non-SII taxpayers, with hard deadlines in January and July 2027
(RD-ley 15/2025). SII (Suministro Inmediato de Información — Immediate Information Supply)
already applies to large taxpayers (>€6M turnover). The Basque Country runs TicketBAI and
Navarre runs NaTicket, both independent of the national AEAT framework. B2G invoicing via
Facturae XML on the FACe portal has been mandatory since 2015 (Ley 25/2013).

---

## Overview

Spain's e-invoicing ecosystem has **six coexisting systems** with distinct scopes, formats,
and timelines. VERI\*FACTU introduces tamper-proof chained invoice records submitted in real
time to AEAT (Agencia Estatal de Administración Tributaria — Spanish Tax Agency), applying to
most businesses from 2027 (RD-ley 15/2025). SII is already mandatory for large taxpayers
under a 4-day reporting window. Facturae XML with XAdES-EPES signature covers all B2G
invoicing through the FACe portal. The Basque Country enforces TicketBAI independently,
with three provincial authorities each maintaining separate XSD schemas and endpoints.
Navarre operates NaTicket. The Crea y Crece law mandates B2B e-invoicing for all companies,
format TBD pending implementing decree. Regime detection from tax address and turnover is
a prerequisite to all other operations — use `es__detect_regional_regime` first.

---

## Regulatory Coverage

| System | Scope | Format | Mandatory from | Status |
|---|---|---|---|---|
| **VERI\*FACTU** | All non-SII businesses | Proprietary XML (HAC/1177/2024 XSD v1.0) | IS: Jan 2027 / Others: Jul 2027 (RD-ley 15/2025) | ⚠️ Pending |
| **Facturae / FACe** | B2G (public sector) | Facturae 3.2.2 + XAdES-EPES | Mandatory since 2015 (Ley 25/2013) | ⚠️ Pending |
| **SII** | Turnover >€6M, VAT groups, REDEME | AEAT SOAP/REST XML | Already mandatory (RD 596/2016) | ⚠️ Pending |
| **TicketBAI** | Álava, Gipuzkoa, Bizkaia | Provincial XML + XAdES + QR | Province-dependent, 2022–2023 | ⚠️ Pending |
| **Crea y Crece (B2B)** | All companies (threshold TBD) | UBL 2.1 or Facturae 3.2.2 (EN 16931) | Implementing decree pending | ⚠️ Pending |
| **NaTicket** | Navarre | Foral XML + signature | Foral mandate (rolling) | Partial (via `es__detect_regional_regime`) |

> **SII / VERI\*FACTU mutual exclusion (Royal Decree 254/2025):** Taxpayers enrolled in SII
> are exempt from VERI\*FACTU. Use `es__check_b2b_mandate_applicability` before generating
> any records.

---

## Tools

### VERI\*FACTU

#### `es__generate_verifactu_record`

Generate a tamper-proof invoice record (Order HAC/1177/2024) with SHA-256 `Huella`
chain linking it to the previous record.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `invoice` | `InvoiceDocument` | Yes | Core invoice model (seller, buyer, lines, VAT) |
| `previous_hash` | `string` | No | SHA-256 `Huella` of preceding record (`null` = first in chain) |
| `software_id` | `string` | Yes | `IDSistemaInformatico` of certified software |
| `software_nif` | `string` | Yes | NIF of the software developer |
| `invoice_type` | `string` | Yes | `F1`, `F2`, `R1`–`R5`, or `F3` |

```json
{
  "tool": "es__generate_verifactu_record",
  "arguments": {
    "invoice": { "date": "2025-03-15", "number": "2025-0042", "currency": "EUR",
      "seller": { "tax_id": { "country_code": "ES", "identifier": "B12345678" }, "name": "Empresa SL" },
      "buyer":  { "tax_id": { "country_code": "ES", "identifier": "A98765432" }, "name": "Cliente SA" },
      "lines": [{ "line_number": 1, "description": "Servicios", "quantity": 10, "unit_price": 100.00, "vat_rate": 21.0 }]
    },
    "previous_hash": "3C4A9B...", "software_id": "SW-001", "software_nif": "B87654321", "invoice_type": "F1"
  }
}
```

> ⚠️ Pending regulatory confirmation — XSD v1.0 (HAC/1177/2024) not yet validated against live AEAT test environment.

---

#### `es__validate_verifactu_record`

Validate a VERI\*FACTU XML record against the official XSD published with HAC/1177/2024
(BOE-A-2024-22138).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `xml` | `string` | Yes | Raw VERI\*FACTU XML record |
| `schema_version` | `string` | No | Schema version (default: `"1.0"`) |

```json
{ "tool": "es__validate_verifactu_record", "arguments": { "xml": "<RegistroFacturacion>...</RegistroFacturacion>" } }
```

> ⚠️ Pending regulatory confirmation

---

#### `es__submit_verifactu_to_aeat`

Submit a signed VERI\*FACTU record to the AEAT real-time endpoint using MTLS
(FNMT-RCM Class 1 certificate). Respects `AEAT_ENV=sandbox|production`.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `xml` | `string` | Yes | Signed VERI\*FACTU XML |
| `nif` | `string` | Yes | Submitter NIF |

```json
{ "tool": "es__submit_verifactu_to_aeat", "arguments": { "xml": "<RegistroFacturacion>...</RegistroFacturacion>", "nif": "B12345678" } }
```

> ⚠️ Pending regulatory confirmation — `AuthMode.MTLS` not yet implemented in `mcp-einvoicing-core`; tracked in core gap backlog.

---

#### `es__generate_qr_verifactu`

Generate the mandatory VERI\*FACTU QR code (HAC/1177/2024 Art. 10) as base64 PNG.
Encodes the AEAT verification URL with "Factura verificable en la sede electrónica de
la AEAT". Candidate for promotion to `mcp-einvoicing-core` (QR generation).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `nif` | `string` | Yes | Issuer NIF |
| `invoice_number` | `string` | Yes | `NumSerieFactura` |
| `invoice_date` | `string` | Yes | `FechaExpedicionFactura` (YYYY-MM-DD) |
| `total_amount` | `number` | Yes | Invoice total including VAT |
| `size_px` | `integer` | No | QR size in pixels (default: 200) |

```json
{ "tool": "es__generate_qr_verifactu", "arguments": { "nif": "B12345678", "invoice_number": "2025-0042", "invoice_date": "2025-03-15", "total_amount": 1210.00 } }
```

> ⚠️ Pending regulatory confirmation

---

#### `es__cancel_verifactu_record`

Generate a VERI\*FACTU cancellation record (`IndicadorAnulacion=S`, `TipoHuella=01`)
chained to the current hash sequence.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `original_invoice_number` | `string` | Yes | `NumSerieFactura` to cancel |
| `original_invoice_date` | `string` | Yes | `FechaExpedicionFactura` (YYYY-MM-DD) |
| `issuer_nif` | `string` | Yes | Issuer NIF |
| `previous_hash` | `string` | Yes | `Huella` of the last record in chain |

```json
{ "tool": "es__cancel_verifactu_record", "arguments": { "original_invoice_number": "2025-0042", "original_invoice_date": "2025-03-15", "issuer_nif": "B12345678", "previous_hash": "3C4A9B..." } }
```

> ⚠️ Pending regulatory confirmation

---

### Facturae / FACe

#### `es__generate_facturae_xml`

Generate a Facturae 3.2.2-compliant XML invoice for B2G submission. Uses
`InvoiceDocument` from `mcp-einvoicing-core`.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `invoice` | `InvoiceDocument` | Yes | Core invoice model |
| `schema_version` | `string` | No | Facturae schema version (default: `"3.2.2"`) |

```json
{ "tool": "es__generate_facturae_xml", "arguments": { "invoice": { "date": "2025-03-15", "number": "2025-0042", "seller": { "tax_id": { "country_code": "ES", "identifier": "B12345678" }, "name": "Proveedor SL" }, "buyer": { "tax_id": { "country_code": "ES", "identifier": "S2800000D" }, "name": "Ayuntamiento de Madrid" }, "lines": [{ "line_number": 1, "description": "Suministro", "quantity": 5, "unit_price": 200.00, "vat_rate": 21.0 }] } } }
```

> ⚠️ Pending regulatory confirmation

---

#### `es__sign_facturae_xades`

Apply an XAdES-EPES digital signature (ETSI EN 319 132-1) to a Facturae XML document.
Candidate for promotion to `mcp-einvoicing-core` (XAdES signature — score 3/3).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `xml` | `string` | Yes | Unsigned Facturae XML |
| `cert_path` | `string` | Yes | Path to PKCS#12 certificate (`.p12` / `.pfx`) |
| `cert_password` | `string` | Yes | Certificate passphrase |
| `signature_policy_id` | `string` | No | OID of the signature policy (default: Facturae standard) |

```json
{ "tool": "es__sign_facturae_xades", "arguments": { "xml": "<Facturae>...</Facturae>", "cert_path": "/certs/empresa.p12", "cert_password": "s3cr3t" } }
```

> ⚠️ Pending regulatory confirmation

---

#### `es__submit_to_face`

Submit a signed Facturae XML to FACe (Punto General de Entrada de Facturas Electrónicas)
via the FACe B2B REST API v2. Requires OAuth2 (`FACE_CLIENT_ID` / `FACE_CLIENT_SECRET`).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `xml` | `string` | Yes | XAdES-signed Facturae XML |
| `administrative_unit` | `string` | Yes | FACe `UnidadTramitadora` code |
| `accounting_office` | `string` | Yes | FACe `OficinasContables` code |
| `management_body` | `string` | Yes | FACe `OrganoGestor` code |

```json
{ "tool": "es__submit_to_face", "arguments": { "xml": "<Facturae>...</Facturae>", "administrative_unit": "U00000038", "accounting_office": "U00000038", "management_body": "U00000038" } }
```

> ⚠️ Pending regulatory confirmation

---

#### `es__get_face_invoice_status`

Query a FACe invoice's processing status. Returns standard codes: 1200 (Registered),
2400 (Acknowledged), 3100 (Rejected), 4100 (Paid).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `invoice_id` | `string` | Yes | FACe registration number |

```json
{ "tool": "es__get_face_invoice_status", "arguments": { "invoice_id": "FAC-2025-00012345" } }
```

> ⚠️ Pending regulatory confirmation

---

#### `es__validate_facturae_schema`

Validate Facturae XML against the official Facturae 3.2.2 XSD using `lxml`. Returns
structured errors with XPath locations.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `xml` | `string` | Yes | Facturae XML to validate |
| `schema_version` | `string` | No | Schema version (default: `"3.2.2"`) |

```json
{ "tool": "es__validate_facturae_schema", "arguments": { "xml": "<Facturae>...</Facturae>" } }
```

> ⚠️ Pending regulatory confirmation

---

### SII (Suministro Inmediato de Información)

#### `es__build_sii_invoice_record`

Build an AEAT SII XML record (issuance `FacturaExpedida` or receipt `FacturaRecibida`)
per AEAT SII technical guide v3.0 (April 2024). Supports `TipoComunicacion` A0/A1/A4.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `invoice` | `InvoiceDocument` | Yes | Core invoice model |
| `record_type` | `string` | Yes | `"issued"` or `"received"` |
| `communication_type` | `string` | No | `"A0"` new (default), `"A1"` modification, `"A4"` removal |

```json
{ "tool": "es__build_sii_invoice_record", "arguments": { "invoice": { "date": "2025-03-15", "number": "2025-0042" }, "record_type": "issued", "communication_type": "A0" } }
```

> ⚠️ Pending regulatory confirmation

---

#### `es__submit_sii_batch`

Submit an invoice batch (max 10,000 records) to the AEAT SII SOAP endpoint. Requires MTLS.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `records` | `array` | Yes | List of XML record strings from `es__build_sii_invoice_record` |
| `record_type` | `string` | Yes | `"issued"` or `"received"` |
| `fiscal_year` | `integer` | Yes | Fiscal year (YYYY) |

```json
{ "tool": "es__submit_sii_batch", "arguments": { "records": ["<RegistroLRFacturasEmitidas>...</RegistroLRFacturasEmitidas>"], "record_type": "issued", "fiscal_year": 2025 } }
```

> ⚠️ Pending regulatory confirmation — `AuthMode.MTLS` not yet implemented in `mcp-einvoicing-core`.

---

#### `es__query_sii_status`

Query the status of a submitted SII batch via `ConsultaFactInformadasEmitidas` or
`ConsultaFactInformadasRecibidas`.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `batch_id` | `string` | Yes | Batch reference from `es__submit_sii_batch` |
| `record_type` | `string` | Yes | `"issued"` or `"received"` |

```json
{ "tool": "es__query_sii_status", "arguments": { "batch_id": "SII-BATCH-20250315-001", "record_type": "issued" } }
```

> ⚠️ Pending regulatory confirmation

---

#### `es__generate_sii_correction`

Generate a SII modification (`A1`) or removal (`A4`) record referencing the original
invoice via `IDFactura`. Corrective invoice builder is a candidate for `mcp-einvoicing-core` (score 3/3).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `original_invoice` | `InvoiceDocument` | Yes | Invoice being corrected |
| `corrected_invoice` | `InvoiceDocument` | No | Corrected data (`null` for A4) |
| `correction_type` | `string` | Yes | `"A1"` or `"A4"` |
| `record_type` | `string` | Yes | `"issued"` or `"received"` |

```json
{ "tool": "es__generate_sii_correction", "arguments": { "original_invoice": { "number": "2025-0042" }, "correction_type": "A1", "record_type": "issued" } }
```

> ⚠️ Pending regulatory confirmation

---

### TicketBAI

#### `es__generate_ticketbai_xml`

Generate a TicketBAI XML invoice with XAdES signature and `HuellaTBAI` chain.
Selects the correct provincial XSD automatically: Álava v1.2, Gipuzkoa v1.2, Bizkaia v2.1.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `invoice` | `InvoiceDocument` | Yes | Core invoice model |
| `province` | `string` | Yes | `"araba"`, `"gipuzkoa"`, or `"bizkaia"` |
| `previous_hash` | `string` | No | `HuellaTBAI` of preceding record |
| `software_license` | `string` | Yes | TicketBAI software license key |
| `cert_path` | `string` | Yes | Signing certificate path |
| `cert_password` | `string` | Yes | Certificate passphrase |

```json
{ "tool": "es__generate_ticketbai_xml", "arguments": { "invoice": { "date": "2025-03-15", "number": "2025-0042" }, "province": "gipuzkoa", "software_license": "TBAI-GI-12345", "cert_path": "/certs/empresa.p12", "cert_password": "s3cr3t" } }
```

> ⚠️ Pending regulatory confirmation — three provincial XSDs must be bundled separately; do not cross-validate between provinces.

---

#### `es__submit_ticketbai`

Submit a TicketBAI XML record to the correct Basque provincial authority. Endpoint is
routed automatically: Álava (`batuz.eus`), Gipuzkoa (`tbai.egoitza.gipuzkoa.eus`),
Bizkaia (`www.bizkaia.eus/ogasun`).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `xml` | `string` | Yes | Signed TicketBAI XML |
| `province` | `string` | Yes | `"araba"`, `"gipuzkoa"`, or `"bizkaia"` |
| `nif` | `string` | Yes | Submitter NIF |

```json
{ "tool": "es__submit_ticketbai", "arguments": { "xml": "<T:TicketBai>...</T:TicketBai>", "province": "bizkaia", "nif": "B12345678" } }
```

> ⚠️ Pending regulatory confirmation

---

#### `es__validate_ticketbai_schema`

Validate a TicketBAI XML document against the correct provincial XSD. Schemas are
**not interchangeable** between provinces.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `xml` | `string` | Yes | TicketBAI XML |
| `province` | `string` | Yes | `"araba"`, `"gipuzkoa"`, or `"bizkaia"` |

```json
{ "tool": "es__validate_ticketbai_schema", "arguments": { "xml": "<T:TicketBai>...</T:TicketBai>", "province": "gipuzkoa" } }
```

> ⚠️ Pending regulatory confirmation

---

### Crea y Crece / B2B

#### `es__generate_b2b_einvoice_es`

Generate an EN 16931-compliant UBL 2.1 or Facturae 3.2.2 B2B invoice per Ley 18/2022.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `invoice` | `InvoiceDocument` | Yes | Core invoice model |
| `format` | `string` | No | `"ubl"` (default) or `"facturae"` |

```json
{ "tool": "es__generate_b2b_einvoice_es", "arguments": { "invoice": { "date": "2025-03-15", "number": "2025-0042" }, "format": "ubl" } }
```

> ⚠️ Pending regulatory confirmation — implementing decree for B2B mandate not yet published.

---

#### `es__check_b2b_mandate_applicability`

Determine the applicable regime (VERI\*FACTU, SII, TicketBAI, NaTicket) from turnover,
province code, and SII enrolment. Applies Royal Decree 254/2025 mutual exclusion logic.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `annual_turnover_eur` | `number` | Yes | Annual VAT turnover in EUR |
| `tax_address_province_code` | `string` | Yes | INE province code (e.g., `"28"` Madrid) |
| `enrolled_in_sii` | `boolean` | No | SII enrolment status (default: `false`) |
| `entity_type` | `string` | No | `"IS"` (corporate tax) or `"IRPF"` |

```json
{ "tool": "es__check_b2b_mandate_applicability", "arguments": { "annual_turnover_eur": 2500000, "tax_address_province_code": "28", "enrolled_in_sii": false, "entity_type": "IS" } }
```

> ⚠️ Pending regulatory confirmation

---

### Utility Tools

#### `es__detect_regional_regime`

Detect the applicable e-invoicing regime from an INE province code. Returns
`VERIFACTU`, `TICKETBAI`, `NATICKET`, or `VERIFACTU+SII`.

Basque provinces: `01` Álava, `20` Gipuzkoa, `48` Bizkaia. Navarre: `31`.
All others return `VERIFACTU`. Candidate for promotion to `mcp-einvoicing-core`.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `province_code` | `string` | Yes | Two-digit INE province code |
| `enrolled_in_sii` | `boolean` | No | SII enrolment (default: `false`) |

```json
{ "tool": "es__detect_regional_regime", "arguments": { "province_code": "20", "enrolled_in_sii": false } }
```

> ⚠️ Pending regulatory confirmation

---

#### `es__get_compliance_status`

Return current mandate deadlines and operative system for a company profile.
Reflects RD-ley 15/2025 — subject to change by subsequent legislation.
Candidate for promotion to `mcp-einvoicing-core` (generic deadline registry).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `entity_type` | `string` | Yes | `"IS"` or `"IRPF"` |
| `province_code` | `string` | Yes | INE province code |
| `annual_turnover_eur` | `number` | No | For SII threshold check (€6M) |
| `enrolled_in_sii` | `boolean` | No | SII enrolment status |

```json
{ "tool": "es__get_compliance_status", "arguments": { "entity_type": "IS", "province_code": "28", "annual_turnover_eur": 1000000, "enrolled_in_sii": false } }
```

> ⚠️ Pending regulatory confirmation

---

#### `es__parse_aeat_response`

Parse and normalize an AEAT XML response (VERI\*FACTU or SII) to structured JSON.
Extracts `EstadoEnvio` (`Correcto`/`AceptadoConErrores`/`Incorrecto`), `CSV`
(secure verification code), and error details. Candidate for promotion to
`mcp-einvoicing-core` (generic vendor XML response parser — score 2/3).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `xml` | `string` | Yes | Raw AEAT XML response |
| `response_type` | `string` | No | `"verifactu"` (default) or `"sii"` |

```json
{ "tool": "es__parse_aeat_response", "arguments": { "xml": "<RespuestaRegFactuSistemaFacturacion>...</RespuestaRegFactuSistemaFacturacion>", "response_type": "verifactu" } }
```

> ⚠️ Pending regulatory confirmation

---

## Installation

```bash
pip install mcp-facturacion-electronica-es
```

### Claude Desktop configuration

```json
{
  "mcpServers": {
    "facturacion-es": {
      "command": "uvx",
      "args": ["mcp-facturacion-electronica-es"],
      "env": {
        "AEAT_ENV": "sandbox",
        "AEAT_CERTIFICATE_PATH": "/path/to/cert.p12",
        "AEAT_CERTIFICATE_PASSWORD": "your-cert-password"
      }
    }
  }
}
```

---

## Configuration

All configuration via environment variables or a `.env` file.

### AEAT / VERI\*FACTU / SII

| Variable | Description | Required |
|---|---|---|
| `AEAT_ENV` | `sandbox` or `production` | Yes |
| `AEAT_CERTIFICATE_PATH` | Path to FNMT-RCM PKCS#12 certificate | For submission |
| `AEAT_CERTIFICATE_PASSWORD` | Certificate passphrase | For submission |
| `AEAT_NIF` | Taxpayer NIF | For submission |

### FACe

| Variable | Description | Required |
|---|---|---|
| `FACE_ENV` | `sandbox` or `production` | Yes |
| `FACE_CLIENT_ID` | OAuth2 client ID | Yes |
| `FACE_CLIENT_SECRET` | OAuth2 client secret | Yes |

### TicketBAI

| Variable | Description | Required |
|---|---|---|
| `TICKETBAI_ENV` | `sandbox` or `production` | Yes |
| `TICKETBAI_CERTIFICATE_PATH` | Provincial signing certificate path | Yes |
| `TICKETBAI_CERTIFICATE_PASSWORD` | Certificate passphrase | Yes |

### Common (inherited from `mcp-einvoicing-core`)

| Variable | Description | Default |
|---|---|---|
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |

---

## Architecture

`mcp-facturacion-electronica-es` is a country adapter in the `mcp-einvoicing` family,
built on top of `mcp-einvoicing-core`.

```
mcp-einvoicing-core (v0.1.0+)
│   BaseDocumentGenerator, BaseDocumentValidator, BaseLifecycleManager
│   InvoiceDocument, InvoiceParty, InvoiceLineItem, VATSummary, PaymentTerms
│   EInvoicingError, ValidationError, XSDValidationError, PlatformError
│   BaseEInvoicingClient, OAuthConfig, AuthMode (OAUTH2 / BEARER / MTLS)
│   get_logger, format_amount, xml_element, format_error
│
├── mcp-facture-electronique-fr    (France — XP Z12-013, Chorus Pro)
├── mcp-einvoicing-be              (Belgium — Peppol BIS 3.0, PINT-BE, Mercurius)
├── mcp-facturacion-electronica-es (Spain — this package)
│   ├── verifactu/   record generation, hash chain, QR, cancellation
│   ├── facturae/    Facturae 3.2.2 XML, XAdES-EPES, FACe submission
│   ├── sii/         batch construction, AEAT SOAP, corrections
│   ├── ticketbai/   XML generation, provincial routing, validation
│   ├── b2b/         Crea y Crece UBL/Facturae, mandate checker
│   └── utils/       regime detection, AEAT response parser, deadline registry
└── mcp-fatturazione-it            (Italy — FatturaPA) [planned]
```

### Core promotion backlog

| Function | Score | Action |
|---|---|---|
| XAdES digital signature | 3/3 (FR, ES, IT) | MUST promote — open issue in `mcp-einvoicing-core` |
| QR code generation | 3/3 (FR, ES, TicketBAI) | MUST promote |
| Sandbox/production URL router | 3/3 (FR, BE, ES) | MUST promote |
| Corrective invoice builder | 3/3 (BE, ES, FR) | MUST promote |
| Invoice hash chain (huella) | 2/3 (ES, FR NF525) | SHOULD promote |
| Mandate deadline registry | 2/3 (FR, ES) | SHOULD promote |

---

## Compliance Notes

> **Disclaimer:** Mandate dates reflect RD-ley 15/2025 (December 2025) and are subject
> to change by subsequent legislation or AEAT administrative guidance. This software does
> not constitute legal or tax advice.

### Mandate timeline

| System | Who | Deadline |
|---|---|---|
| SII | Turnover >€6M / VAT groups / REDEME | Already mandatory (RD 596/2016) |
| Facturae/FACe | All B2G suppliers | Already mandatory (Ley 25/2013) |
| TicketBAI | All Basque Country businesses | 2022–2023 sector rollout |
| VERI\*FACTU | IS (corporate tax) taxpayers | **January 2027** (RD-ley 15/2025) |
| VERI\*FACTU | IRPF + other non-SII taxpayers | **July 2027** (RD-ley 15/2025) |
| Crea y Crece B2B | All companies | TBD — implementing decree pending |

### Regional exceptions

- **Basque Country (País Vasco):** TicketBAI applies **instead of** VERI\*FACTU.
  Each of the three provinces (Álava, Gipuzkoa, Bizkaia) has a distinct XSD, endpoint,
  and software certification process. AEAT national endpoints do not apply.
- **Navarre (Navarra):** NaTicket (Hacienda Foral de Navarra) applies. VERI\*FACTU does not.
- **Ceuta / Melilla:** IPSI (not VAT); SII/VERI\*FACTU applicability differs — verify with AEAT.
- **SII / VERI\*FACTU mutual exclusion:** Royal Decree 254/2025 makes these systems mutually
  exclusive. SII-enrolled taxpayers do not submit VERI\*FACTU records.

All AEAT submission endpoints require an FNMT-RCM or accredited CA certificate.
The AEAT provides a free sandbox at `prewww2.aeat.es`.

---

## Contributing

Open an issue before starting significant work. For utility logic reusable across
country adapters, open a `core-promotion` issue in `mcp-einvoicing-core` before
implementing — use the scoring rubric (3 = MUST promote, 2 = SHOULD, 1 = keep here).

```bash
git clone https://github.com/christophe/mcp-facturacion-electronica-es
cd mcp-facturacion-electronica-es
pip install -e ".[dev]"
pytest
```

All regulatory claims must reference a specific BOE publication, official XSD version,
or AEAT technical guide version. Do not remove `⚠️ Pending regulatory confirmation`
without linking the verified source in the PR description.

---

## Phase 1 Audit Summary

| Check | Result | Notes |
|---|---|---|
| Core contract | PENDING | Zero source code — all contracts defined, none implemented |
| Tool coverage | 0/22 | All 22 tools specified; none implemented |
| Regulatory accuracy | 0/22 verified | All tools carry `⚠️` pending implementation |
| Core promotion | 6 candidates | XAdES, QR, URL router, hash chain, corrective invoice, deadline registry |

This README is the **specification document** for the implementation phase.
Tool badges will be updated to ✅ as each tool passes regulatory verification.

---

## License

Licensed under the [Apache License 2.0](LICENSE).
Copyright 2025–2026 Christophe Méndez and contributors.
