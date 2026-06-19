# mcp-facturacion-electronica-es 🇪🇸

[English](README.md) | [Espanol](README.es.md)

<!-- mcp-name: io.github.cmendezs/mcp-facturacion-electronica-es -->

![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)
[![PyPI version](https://img.shields.io/pypi/v/mcp-facturacion-electronica-es.svg)](https://pypi.org/project/mcp-facturacion-electronica-es/)
[![Python](https://img.shields.io/pypi/pyversions/mcp-facturacion-electronica-es.svg)](https://pypi.org/project/mcp-facturacion-electronica-es/) [![mcp-facturacion-electronica-es MCP server](https://glama.ai/mcp/servers/cmendezs/mcp-facturacion-electronica-es/badges/score.svg)](https://glama.ai/mcp/servers/cmendezs/mcp-facturacion-electronica-es)

---

## Introduction

**mcp-facturacion-electronica-es** is an MCP (Model Context Protocol) server specialized
in Spanish e-invoicing. It provides tools to generate, validate, and submit electronic
invoices under the six coexisting systems in Spain: VERI\*FACTU, Facturae/FACe,
SII, TicketBAI (Basque Country), NaTicket (Navarre), and the B2B obligations of Ley 18/2022
"Crea y Crece". The server is built on `mcp-einvoicing-core`, the shared base library
used by `mcp-facture-electronique-fr` (France, XP Z12-013) and `mcp-einvoicing-be`
(Belgium, Peppol BIS 3.0).

Spain operates one of the most complex e-invoicing landscapes in Europe, with six overlapping
systems that apply depending on taxpayer size, sector, and region. VERI\*FACTU
(Royal Decree 1007/2023, Order HAC/1177/2024) is the forthcoming mandatory real-time invoice
registry for non-SII taxpayers, with hard deadlines in January and July 2027 (RD-ley 15/2025).
SII (Suministro Inmediato de Informacion, Immediate Information Supply) already applies to
large taxpayers (>6M EUR turnover). The Basque Country runs TicketBAI and Navarre runs NaTicket,
both independent of the national AEAT framework. B2G invoicing via Facturae XML on the FACe
portal has been mandatory since 2015 (Ley 25/2013).

---

## Built on

This package is built on [**mcp-einvoicing-core**](https://github.com/cmendezs/mcp-einvoicing-core),
the shared base library used by all MCP servers in the `mcp-einvoicing` ecosystem. It provides
common models, validation abstractions, XML utilities, and the exception hierarchy.

`mcp-einvoicing-core` is installed automatically as a transitive dependency, no additional
steps are required.

---

## Overview

The Spanish e-invoicing ecosystem has **six coexisting systems** with distinct scopes,
formats, and timelines. VERI\*FACTU introduces tamper-proof chained invoice records
submitted in real time to the AEAT (Agencia Estatal de Administracion Tributaria),
applicable to most businesses from 2027 (RD-ley 15/2025). SII is already mandatory for
large taxpayers under a 4-day communication window. Facturae XML with XAdES-EPES signing
covers all B2G invoicing through the FACe portal. The Basque Country applies TicketBAI
independently, with three provincial authorities each maintaining their own XSD schemas and
endpoints. Navarre operates NaTicket. The Ley Crea y Crece mandates B2B e-invoicing for
all businesses, with the format still pending implementing regulations. Regime detection
based on tax domicile and turnover is a prerequisite to all other operations: use
`es__detect_regional_regime` first.

---

## Regulatory coverage

| System | Scope | Format | Mandatory from | Status |
|---|---|---|---|---|
| **VERI\*FACTU** | All non-SII businesses | Proprietary XML (XSD v1.0 HAC/1177/2024) | IS: Jan 2027 / Others: Jul 2027 (RD-ley 15/2025) | ⚠️ Pending |
| **Facturae / FACe** | B2G (public sector) | Facturae 3.2.2 + XAdES-EPES | Mandatory since 2015 (Ley 25/2013) | ⚠️ Pending |
| **SII** | Turnover >6M EUR, VAT groups, REDEME | XML SOAP/REST AEAT | Already mandatory (RD 596/2016) | ⚠️ Pending |
| **TicketBAI** | Araba, Gipuzkoa, Bizkaia | Provincial XML + XAdES + QR | By province, 2022-2023 | ⚠️ Pending |
| **Crea y Crece (B2B)** | All businesses (threshold pending) | UBL 2.1 or Facturae 3.2.2 (EN 16931) | Implementing regulations pending | ⚠️ Pending |
| **NaTicket** | Navarre | Foral XML + signature | Foral mandate (phased rollout) | Partial (via `es__detect_regional_regime`) |

> **SII / VERI\*FACTU mutual exclusion (Real Decreto 254/2025):** Taxpayers enrolled in
> SII are exempt from VERI\*FACTU. Use `es__check_b2b_mandate_applicability`
> before generating any record.

---

## Tools

### VERI\*FACTU

#### `es__generate_verifactu_record`

Generates a tamper-proof invoice record (Orden HAC/1177/2024) with SHA-256 `Huella`
chaining that links it to the previous record.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `invoice` | `InvoiceDocument` | Yes | Core invoice model (seller, buyer, lines, VAT) |
| `previous_hash` | `string` | No | SHA-256 `Huella` of the preceding record (`null` = first in chain) |
| `software_id` | `string` | Yes | `IDSistemaInformatico` of the certified software |
| `software_nif` | `string` | Yes | NIF of the software manufacturer |
| `invoice_type` | `string` | Yes | `F1`, `F2`, `R1`-`R5` or `F3` |

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

> ⚠️ Pending regulatory confirmation: XSD v1.0 (HAC/1177/2024) not yet validated against the AEAT test environment.

---

#### `es__validate_verifactu_record`

Validates a VERI\*FACTU XML record against the official XSD published with Orden HAC/1177/2024
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

Submits a signed VERI\*FACTU record to the AEAT real-time endpoint via MTLS
(FNMT-RCM Class 1 certificate). Respects `AEAT_ENV=sandbox|production`.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `xml` | `string` | Yes | Signed VERI\*FACTU XML |
| `nif` | `string` | Yes | Sender NIF |

```json
{ "tool": "es__submit_verifactu_to_aeat", "arguments": { "xml": "<RegistroFacturacion>...</RegistroFacturacion>", "nif": "B12345678" } }
```

> ⚠️ Pending regulatory confirmation: `AuthMode.MTLS` is not yet implemented in `mcp-einvoicing-core`; tracked in the core gaps backlog.

---

#### `es__generate_qr_verifactu`

Generates the mandatory VERI\*FACTU QR code (HAC/1177/2024 Art. 10) as a base64-encoded PNG.
Encodes the AEAT verification URL with the text "Factura verificable en la sede
electronica de la AEAT". Candidate for promotion to `mcp-einvoicing-core` (QR generation).

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

Generates a VERI\*FACTU cancellation record (`IndicadorAnulacion=S`, `TipoHuella=01`)
chained to the current fingerprint sequence.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `original_invoice_number` | `string` | Yes | `NumSerieFactura` to cancel |
| `original_invoice_date` | `string` | Yes | `FechaExpedicionFactura` (YYYY-MM-DD) |
| `issuer_nif` | `string` | Yes | Issuer NIF |
| `previous_hash` | `string` | Yes | `Huella` of the last record in the chain |

```json
{ "tool": "es__cancel_verifactu_record", "arguments": { "original_invoice_number": "2025-0042", "original_invoice_date": "2025-03-15", "issuer_nif": "B12345678", "previous_hash": "3C4A9B..." } }
```

> ⚠️ Pending regulatory confirmation

---

### Facturae / FACe

#### `es__generate_facturae_xml`

Generates a Facturae 3.2.2 compliant XML invoice for B2G submission. Uses
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

Applies an XAdES-EPES digital signature (ETSI EN 319 132-1) to a Facturae XML document.
Candidate for promotion to `mcp-einvoicing-core` (XAdES signing, score 3/3).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `xml` | `string` | Yes | Unsigned Facturae XML |
| `cert_path` | `string` | Yes | Path to PKCS#12 certificate (`.p12` / `.pfx`) |
| `cert_password` | `string` | Yes | Certificate password |
| `signature_policy_id` | `string` | No | Signature policy OID (default: Facturae standard) |

```json
{ "tool": "es__sign_facturae_xades", "arguments": { "xml": "<Facturae>...</Facturae>", "cert_path": "/certs/empresa.p12", "cert_password": "s3cr3t" } }
```

> ⚠️ Pending regulatory confirmation

---

#### `es__submit_to_face`

Submits a signed Facturae XML to FACe (Punto General de Entrada de Facturas Electronicas)
via the FACe B2B REST API v2. Requires OAuth2 (`FACE_CLIENT_ID` / `FACE_CLIENT_SECRET`).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `xml` | `string` | Yes | Facturae XML with XAdES signature |
| `administrative_unit` | `string` | Yes | FACe `UnidadTramitadora` code |
| `accounting_office` | `string` | Yes | FACe `OficinasContables` code |
| `management_body` | `string` | Yes | FACe `OrganoGestor` code |

```json
{ "tool": "es__submit_to_face", "arguments": { "xml": "<Facturae>...</Facturae>", "administrative_unit": "U00000038", "accounting_office": "U00000038", "management_body": "U00000038" } }
```

> ⚠️ Pending regulatory confirmation

---

#### `es__get_face_invoice_status`

Queries the processing status of an invoice on FACe. Returns standard status codes:
1200 (Registered), 2400 (Acknowledged), 3100 (Rejected), 4100 (Paid).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `invoice_id` | `string` | Yes | FACe registration number |

```json
{ "tool": "es__get_face_invoice_status", "arguments": { "invoice_id": "FAC-2025-00012345" } }
```

> ⚠️ Pending regulatory confirmation

---

#### `es__validate_facturae_schema`

Validates a Facturae XML against the official Facturae 3.2.2 XSD using `lxml`. Returns
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

### SII (Suministro Inmediato de Informacion)

#### `es__build_sii_invoice_record`

Builds an AEAT SII XML record (issued `FacturaExpedida` or received `FacturaRecibida`)
conforming to the AEAT SII technical guide v3.0 (April 2024). Supports `TipoComunicacion` A0/A1/A4.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `invoice` | `InvoiceDocument` | Yes | Core invoice model |
| `record_type` | `string` | Yes | `"issued"` or `"received"` |
| `communication_type` | `string` | No | `"A0"` new (default), `"A1"` modification, `"A4"` cancellation |

```json
{ "tool": "es__build_sii_invoice_record", "arguments": { "invoice": { "date": "2025-03-15", "number": "2025-0042" }, "record_type": "issued", "communication_type": "A0" } }
```

> ⚠️ Pending regulatory confirmation

---

#### `es__submit_sii_batch`

Submits a batch of invoices (up to 10,000 records) to the AEAT SII SOAP endpoint. Requires MTLS.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `records` | `array` | Yes | List of XML strings from `es__build_sii_invoice_record` |
| `record_type` | `string` | Yes | `"issued"` or `"received"` |
| `fiscal_year` | `integer` | Yes | Fiscal year (YYYY) |

```json
{ "tool": "es__submit_sii_batch", "arguments": { "records": ["<RegistroLRFacturasEmitidas>...</RegistroLRFacturasEmitidas>"], "record_type": "issued", "fiscal_year": 2025 } }
```

> ⚠️ Pending regulatory confirmation: `AuthMode.MTLS` is not yet implemented in `mcp-einvoicing-core`.

---

#### `es__query_sii_status`

Queries the status of a submitted SII batch via `ConsultaFactInformadasEmitidas` or
`ConsultaFactInformadasRecibidas`.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `batch_id` | `string` | Yes | Batch reference returned by `es__submit_sii_batch` |
| `record_type` | `string` | Yes | `"issued"` or `"received"` |

```json
{ "tool": "es__query_sii_status", "arguments": { "batch_id": "SII-BATCH-20250315-001", "record_type": "issued" } }
```

> ⚠️ Pending regulatory confirmation

---

#### `es__generate_sii_correction`

Generates an SII modification (`A1`) or cancellation (`A4`) record referencing the original
invoice via `IDFactura`. The credit note builder is a candidate for `mcp-einvoicing-core`
(score 3/3).

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

Generates a TicketBAI XML invoice with XAdES signature and `HuellaTBAI` chain. Automatically
selects the correct provincial XSD: Araba v1.2, Gipuzkoa v1.2, Bizkaia v2.1.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `invoice` | `InvoiceDocument` | Yes | Core invoice model |
| `province` | `string` | Yes | `"araba"`, `"gipuzkoa"` or `"bizkaia"` |
| `previous_hash` | `string` | No | `HuellaTBAI` of the preceding record |
| `software_license` | `string` | Yes | TicketBAI software license key |
| `cert_path` | `string` | Yes | Signing certificate path |
| `cert_password` | `string` | Yes | Certificate password |

```json
{ "tool": "es__generate_ticketbai_xml", "arguments": { "invoice": { "date": "2025-03-15", "number": "2025-0042" }, "province": "gipuzkoa", "software_license": "TBAI-GI-12345", "cert_path": "/certs/empresa.p12", "cert_password": "s3cr3t" } }
```

> ⚠️ Pending regulatory confirmation: the three provincial XSDs must be packaged separately; cross-province validation is not permitted.

---

#### `es__submit_ticketbai`

Submits a TicketBAI XML record to the corresponding Basque provincial authority. The endpoint
is automatically routed: Araba (`batuz.eus`), Gipuzkoa (`tbai.egoitza.gipuzkoa.eus`),
Bizkaia (`www.bizkaia.eus/ogasun`).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `xml` | `string` | Yes | Signed TicketBAI XML |
| `province` | `string` | Yes | `"araba"`, `"gipuzkoa"` or `"bizkaia"` |
| `nif` | `string` | Yes | Sender NIF |

```json
{ "tool": "es__submit_ticketbai", "arguments": { "xml": "<T:TicketBai>...</T:TicketBai>", "province": "bizkaia", "nif": "B12345678" } }
```

> ⚠️ Pending regulatory confirmation

---

#### `es__validate_ticketbai_schema`

Validates a TicketBAI XML document against the correct provincial XSD. The schemas
**are not interchangeable** between provinces.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `xml` | `string` | Yes | TicketBAI XML |
| `province` | `string` | Yes | `"araba"`, `"gipuzkoa"` or `"bizkaia"` |

```json
{ "tool": "es__validate_ticketbai_schema", "arguments": { "xml": "<T:TicketBai>...</T:TicketBai>", "province": "gipuzkoa" } }
```

> ⚠️ Pending regulatory confirmation

---

### Crea y Crece / B2B

#### `es__generate_b2b_einvoice_es`

Generates a B2B invoice conforming to EN 16931 in UBL 2.1 or Facturae 3.2.2 format
per Ley 18/2022.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `invoice` | `InvoiceDocument` | Yes | Core invoice model |
| `format` | `string` | No | `"ubl"` (default) or `"facturae"` |

```json
{ "tool": "es__generate_b2b_einvoice_es", "arguments": { "invoice": { "date": "2025-03-15", "number": "2025-0042" }, "format": "ubl" } }
```

> ⚠️ Pending regulatory confirmation: the B2B mandate implementing regulations have not been published yet.

---

#### `es__check_b2b_mandate_applicability`

Determines the applicable regime (VERI\*FACTU, SII, TicketBAI, NaTicket) based on
turnover, province code, and SII enrollment. Applies the mutual exclusion logic of
Real Decreto 254/2025.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `annual_turnover_eur` | `number` | Yes | Annual VAT turnover in EUR |
| `tax_address_province_code` | `string` | Yes | INE province code (e.g., `"28"` Madrid) |
| `enrolled_in_sii` | `boolean` | No | SII enrollment (default: `false`) |
| `entity_type` | `string` | No | `"IS"` (Impuesto sobre Sociedades) or `"IRPF"` |

```json
{ "tool": "es__check_b2b_mandate_applicability", "arguments": { "annual_turnover_eur": 2500000, "tax_address_province_code": "28", "enrolled_in_sii": false, "entity_type": "IS" } }
```

> ⚠️ Pending regulatory confirmation

---

### Utility tools

#### `es__detect_regional_regime`

Detects the applicable e-invoicing regime based on the INE province code.
Returns `VERIFACTU`, `TICKETBAI`, `NATICKET`, or `VERIFACTU+SII`.

Basque provinces: `01` Araba, `20` Gipuzkoa, `48` Bizkaia. Navarre: `31`.
All others return `VERIFACTU`. Candidate for promotion to `mcp-einvoicing-core`.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `province_code` | `string` | Yes | Two-digit INE province code |
| `enrolled_in_sii` | `boolean` | No | SII enrollment (default: `false`) |

```json
{ "tool": "es__detect_regional_regime", "arguments": { "province_code": "20", "enrolled_in_sii": false } }
```

> ⚠️ Pending regulatory confirmation

---

#### `es__get_compliance_status`

Returns the current mandate deadlines and operating system for a business profile.
Reflects RD-ley 15/2025, subject to changes by subsequent legislation.
Candidate for promotion to `mcp-einvoicing-core` (generic deadline registry).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `entity_type` | `string` | Yes | `"IS"` or `"IRPF"` |
| `province_code` | `string` | Yes | INE province code |
| `annual_turnover_eur` | `number` | No | For SII threshold check (6M EUR) |
| `enrolled_in_sii` | `boolean` | No | SII enrollment |

```json
{ "tool": "es__get_compliance_status", "arguments": { "entity_type": "IS", "province_code": "28", "annual_turnover_eur": 1000000, "enrolled_in_sii": false } }
```

> ⚠️ Pending regulatory confirmation

---

#### `es__parse_aeat_response`

Parses and normalizes an AEAT XML response (VERI\*FACTU or SII) into structured JSON.
Extracts `EstadoEnvio` (`Correcto`/`AceptadoConErrores`/`Incorrecto`), `CSV`
(secure verification code), and error details. Candidate for promotion to
`mcp-einvoicing-core` (generic vendor XML response parser, score 2/3).

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

### From PyPI (recommended)

```bash
pip install mcp-facturacion-electronica-es
```

Without prior installation, using `uvx`:

```bash
uvx mcp-facturacion-electronica-es
```

### From source

```bash
git clone https://github.com/cmendezs/mcp-facturacion-electronica-es.git
cd mcp-facturacion-electronica-es
uv sync --all-extras
```

---

## Configuration

### Claude Desktop

```json
{
  "mcpServers": {
    "facturacion-es": {
      "command": "uvx",
      "args": ["mcp-facturacion-electronica-es"],
      "env": {
        "AEAT_ENV": "sandbox",
        "AEAT_CERTIFICATE_PATH": "/path/to/cert.p12",
        "AEAT_CERTIFICATE_PASSWORD": "certificate-password"
      }
    }
  }
}
```

All configuration is done through environment variables or a `.env` file.

### AEAT / VERI\*FACTU / SII

| Variable | Description | Required |
|---|---|---|
| `AEAT_ENV` | `sandbox` or `production` | Yes |
| `AEAT_CERTIFICATE_PATH` | Path to FNMT-RCM PKCS#12 certificate | For submission |
| `AEAT_CERTIFICATE_PASSWORD` | Certificate password | For submission |
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
| `TICKETBAI_CERTIFICATE_PASSWORD` | Certificate password | Yes |

### Common (inherited from `mcp-einvoicing-core`)

| Variable | Description | Default |
|---|---|---|
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |

---

## Architecture

`mcp-facturacion-electronica-es` is a country adapter within the `mcp-einvoicing` family,
built on `mcp-einvoicing-core`.

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
│   ├── sii/         batch building, AEAT SOAP, corrections
│   ├── ticketbai/   XML generation, provincial routing, validation
│   ├── b2b/         UBL/Facturae Crea y Crece, mandate detector
│   └── utils/       regime detection, AEAT response parser, deadline registry
├── mcp-fattura-elettronica-it     (Italy — FatturaPA / SDI)
└── mcp-ksef-pl                    (Poland — KSeF / FA(2))
```

### Functions candidate for `mcp-einvoicing-core`

| Function | Score | Action |
|---|---|---|
| XAdES digital signing | 3/3 (FR, ES, IT) | MUST promote, open issue in `mcp-einvoicing-core` |
| QR code generation | 3/3 (FR, ES, TicketBAI) | MUST promote |
| Sandbox/production URL router | 3/3 (FR, BE, ES) | MUST promote |
| Credit note builder | 3/3 (BE, ES, FR) | MUST promote |
| Invoice hash chain (fingerprint) | 2/3 (ES, FR NF525) | SHOULD promote |
| Mandate deadline registry | 2/3 (FR, ES) | SHOULD promote |

---

## Compliance notes

> **Notice:** Mandate dates reflect RD-ley 15/2025 (December 2025) and are
> subject to changes by subsequent legislation or AEAT administrative instructions.
> This software does not constitute legal or tax advice.

### Mandate timeline

| System | Targets | Deadline |
|---|---|---|
| SII | Turnover >6M EUR / VAT groups / REDEME | Already mandatory (RD 596/2016) |
| Facturae/FACe | All B2G suppliers | Already mandatory (Ley 25/2013) |
| TicketBAI | All businesses in the Basque Country | Phased rollout by sector 2022-2023 |
| VERI\*FACTU | IS (Impuesto sobre Sociedades) taxpayers | **January 2027** (RD-ley 15/2025) |
| VERI\*FACTU | IRPF + other non-SII | **July 2027** (RD-ley 15/2025) |
| Crea y Crece B2B | All businesses | Pending, implementing regulations not yet published |

### Regional exceptions

- **Basque Country:** TicketBAI applies **instead of** VERI\*FACTU.
  Each of the three provinces (Araba, Gipuzkoa, Bizkaia) has a different XSD, endpoint,
  and software certification process. National AEAT endpoints do not apply.
- **Navarre:** NaTicket applies (Hacienda Foral de Navarra). VERI\*FACTU does not apply.
- **Ceuta / Melilla:** IPSI (not VAT); SII/VERI\*FACTU applicability differs, verify with the AEAT.
- **SII / VERI\*FACTU mutual exclusion:** Real Decreto 254/2025 makes these systems
  mutually exclusive. Taxpayers enrolled in SII do not submit VERI\*FACTU records.

All AEAT submission endpoints require an FNMT-RCM certificate or one from an accredited CA.
The AEAT provides a free test environment at `prewww2.aeat.es`.

---

## Tests

```bash
# Install development dependencies
uv sync --all-extras

# Run the full test suite
uv run pytest tests/ -v

# With coverage report
uv run pytest --cov=mcp_facturacion_electronica_es --cov-report=term-missing
```

---

## Roadmap

Pending items have been extracted directly from the `[NEED]` markers present in the source code. Each version is a prerequisite for the next and must pass the audit gate (`make audit`) before being published.

### v0.1.0 (current) — Scaffold and local generation

Tools implemented with valid XML generated locally, structural validation, regime logic, and XAdES signing. No submissions to external platforms confirmed against real environments.

---

### v0.2.0 — XSD schema bundle and protocol fixes

**Complete XSD validation (currently structural only):**

| Task | File | Regulatory reference |
|---|---|---|
| Download VERI\*FACTU XSD v1.0 to `specs/verifactu/` | `tools/verifactu.py` | BOE-A-2024-22138 (Orden HAC/1177/2024) |
| Download Facturae 3.2.2 XSD to `specs/facturae/` | `tools/facturae.py` | facturae.gob.es |
| Download TicketBAI Araba XSD v1.2 to `specs/ticketbai/araba/` | `tools/ticketbai.py` | batuz.eus |
| Download TicketBAI Gipuzkoa XSD v1.2 to `specs/ticketbai/gipuzkoa/` | `tools/ticketbai.py` | gipuzkoa.eus |
| Download TicketBAI Bizkaia XSD v2.1 to `specs/ticketbai/bizkaia/` | `tools/ticketbai.py` | bizkaia.eus |

**XAdES signature policies:**

| Task | File |
|---|---|
| Compute SHA-256 of the Facturae policy PDF (Orden EHA/962/2007) and assign `FACTURAE_POLICY_HASH` in `_helpers.py` | `_helpers.py`, `tools/facturae.py` |
| Obtain and assign the SHA-256 hashes of provincial TicketBAI policies (Araba, Gipuzkoa, Bizkaia) in `TICKETBAI_POLICY_IDS` | `_helpers.py`, `tools/ticketbai.py` |
| Verify the three TicketBAI policy URIs against each province's official technical documentation | `_helpers.py` |

**Protocol fixes:**

| Task | File |
|---|---|
| Verify the HuellaTBAI algorithm against the official technical specification (raw bytes, Base64-decoded, or text?) | `tools/ticketbai.py` |
| Fill in the TicketBAI `Claves` element with the correct invoice types | `tools/ticketbai.py` |
| Add `HoraExpedicionFactura` as an input parameter to `es__generate_ticketbai_xml` | `tools/ticketbai.py` |
| Confirm the exact VERI\*FACTU QR URL format and parameters (Art. 10 HAC/1177/2024) | `tools/verifactu.py` |
| Add IBAN and BIC fields to the Facturae 3.2.2 `AccountToBeCredited` block | `tools/facturae.py` |

---

### v0.3.0 — Endpoint verification and sandbox

**AEAT — VERI\*FACTU:**

| Task | File |
|---|---|
| Verify the VERI\*FACTU sandbox endpoint URL once the AEAT opens the test environment | `tools/verifactu.py`, `_helpers.py` |
| Confirm the VERI\*FACTU production URL against the technical guide published by the AEAT | `_helpers.py` |

**AEAT — SII:**

| Task | File |
|---|---|
| Confirm the SII sandbox URL (`www7` or `www10`?) against the SII technical guide v3.0 | `_helpers.py`, `tools/sii.py` |
| Validate the SOAP envelope structure against the AEAT SII v3.0 sandbox | `tools/sii.py` |

**FACe:**

| Task | File |
|---|---|
| Verify the FACe B2B API v2 base path (may have changed in 2025) | `_helpers.py` |
| Verify the FACe OAuth2 endpoint URL for sandbox and production | `tools/facturae.py` |
| Validate the complete FACe OAuth2 flow against real sandbox credentials | `tools/facturae.py` |

**TicketBAI:**

| Task | File |
|---|---|
| Verify the Araba sandbox endpoint (same as production with test NIF?) | `_helpers.py` |
| Verify the Bizkaia LROE API path (different submission schema from the rest) | `_helpers.py` |
| Confirm the authentication method per province (MTLS certificate, API key, etc.) | `tools/ticketbai.py` |

---

### v0.4.0 — Full chain and correct SII batches

| Task | File | Detail |
|---|---|---|
| Store and propagate `IDEmisorFacturaAnterior`, `NumSerieFacturaAnterior`, and `FechaAnterior` for complete VERI\*FACTU chaining | `tools/verifactu.py` | Currently only the `Huella` is chained; the specification also requires the previous record identifiers |
| Merge multiple `RegistroLRFacturas` records into a single `SuministroLRFacturasEmitidas` for the actual SII batch | `tools/sii.py` | Current behavior sends each record separately |
| Build the SOAP envelope `ConsultaFactInformadasEmitidas` / `ConsultaFactInformadasRecibidas` with `IDFactura` filter in `es__query_sii_status` | `tools/sii.py` | Currently sends a generic GET request |
| Document or implement the VERI\*FACTU record XAdES signing flow before submission | `tools/verifactu.py` | The record generated by `es__generate_verifactu_record` must be signed before being submitted to the AEAT |
| Parse the AEAT response in the `es__submit_verifactu_to_aeat` handler using `es__parse_aeat_response` | `tools/verifactu.py` | Currently returns raw text |

---

### v0.5.0 — Crea y Crece B2B + audit hardening

| Task | File | Detail |
|---|---|---|
| Confirm B2B format requirements (UBL 2.1 vs. Facturae 3.2.2) once the implementing regulations of Ley 18/2022 are published | `tools/b2b.py` | The regulations are pending publication as of May 2026 |
| Update `_INTENTIONAL_OVERRIDES` and `_CORE_MODULES_TO_CHECK` in the audit once the `mcp-einvoicing-core` public API is finalized | `audit/audit_vs_core.py` | Will reduce the current 66 CHECK 1 warnings |
| Replace the hand-rolled PEP 440 version parser with `packaging.version` | `audit/audit_vs_core.py` | The current parser only supports `>=X` and `<Y` |
| Update CHECK 5 with additional checks from the `mcp-einvoicing-core` tool category registry | `audit/audit_vs_core.py` | — |

---

### v1.0.0 — Production ready

- All sandbox verifications completed
- All XSD validations enabled (specs/ populated)
- Full VERI\*FACTU mandate coverage (January and July 2027)
- TicketBAI software certified by all three Basque provinces
- Crea y Crece B2B regulations published and implemented
- Audit gate with zero warnings (exit code 0)

---

## Contributing

Open an issue before starting significant work. For reusable utility logic across country
adapters, open a `core-promotion` issue in `mcp-einvoicing-core` before implementing it:
use the scoring rubric (3 = MUST promote, 2 = SHOULD, 1 = keep here).

```bash
git clone https://github.com/cmendezs/mcp-facturacion-electronica-es.git
cd mcp-facturacion-electronica-es
uv sync --all-extras
uv run pytest
make audit
```

All regulatory assertions must reference a specific BOE publication, an official XSD version,
or an AEAT technical guide version. Do not remove
`⚠️ Pending regulatory confirmation` without linking the verified source in the
PR description.

---

## Audit Summary — Phase 1

| Check | Result | Notes |
|---|---|---|
| Core contract | PENDING | No source code, all contracts defined, none implemented |
| Tool coverage | 0/22 | All 22 tools specified; none implemented |
| Regulatory accuracy | 0/22 verified | All tools carry `⚠️` pending implementation |
| Core promotion | 6 candidates | XAdES, QR, URL router, hash chain, credit note, deadline registry |

This README is the **specification document** for the implementation phase.
Tool badges will be updated to ✅ as each tool passes regulatory verification.

---

## Other e-invoicing MCP servers

| Country | Server |
|---------|--------|
| 🌍 Global | [mcp-einvoicing-core](https://github.com/cmendezs/mcp-einvoicing-core) |
| 🇧🇪 Belgium | [mcp-einvoicing-be](https://github.com/cmendezs/mcp-einvoicing-be) |
| 🇧🇷 Brazil | [mcp-nfe-br](https://github.com/cmendezs/mcp-nfe-br) |
| 🇫🇷 France | [mcp-facture-electronique-fr](https://github.com/cmendezs/mcp-facture-electronique-fr) |
| 🇩🇪 Germany | [mcp-einvoicing-de](https://github.com/cmendezs/mcp-einvoicing-de) |
| 🇮🇹 Italy | [mcp-fattura-elettronica-it](https://github.com/cmendezs/mcp-fattura-elettronica-it) |
| 🇵🇱 Poland | [mcp-ksef-pl](https://github.com/cmendezs/mcp-ksef-pl) |
| 🇪🇸 Spain | [mcp-facturacion-electronica-es](https://github.com/cmendezs/mcp-facturacion-electronica-es) |

---

## License

Released under the [Apache License 2.0](LICENSE).
Copyright 2025-2026 Christophe Mendez and contributors.
