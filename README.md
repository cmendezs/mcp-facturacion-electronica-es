# mcp-facturacion-electronica-es 🇪🇸
<!-- mcp-name: io.github.cmendezs/mcp-facturacion-electronica-es -->

![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)
[![PyPI version](https://img.shields.io/pypi/v/mcp-facturacion-electronica-es.svg)](https://pypi.org/project/mcp-facturacion-electronica-es/)
[![Python](https://img.shields.io/pypi/pyversions/mcp-facturacion-electronica-es.svg)](https://pypi.org/project/mcp-facturacion-electronica-es/) [![mcp-facturacion-electronica-es MCP server](https://glama.ai/mcp/servers/cmendezs/mcp-facturacion-electronica-es/badges/score.svg)](https://glama.ai/mcp/servers/cmendezs/mcp-facturacion-electronica-es)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-brightgreen.svg)](https://modelcontextprotocol.io)
[![Audit status](https://img.shields.io/badge/audit-PENDING%20IMPLEMENTATION-orange.svg)](#resumen-del-audit--fase-1)

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

## Construido sobre

Este paquete se basa en [**mcp-einvoicing-core**](https://github.com/cmendezs/mcp-einvoicing-core),
la librería base compartida por todos los servidores MCP del ecosistema `mcp-einvoicing`. Proporciona
modelos comunes, abstracciones de validación, utilidades XML y la jerarquía de excepciones.

`mcp-einvoicing-core` se instala automáticamente como dependencia transitiva — no se requiere
ningún paso adicional.

---

## Descripción general

El ecosistema español de facturación electrónica cuenta con **seis sistemas coexistentes** con
ámbitos, formatos y calendarios distintos. VERI\*FACTU introduce registros de factura
inviolables encadenados que se envían en tiempo real a la AEAT (Agencia Estatal de
Administración Tributaria), aplicable a la mayoría de empresas a partir de 2027 (RD-ley 15/2025).
El SII ya es obligatorio para grandes contribuyentes bajo una ventana de comunicación de
4 días. Facturae XML con firma XAdES-EPES cubre toda la facturación B2G a través del portal
FACe. El País Vasco aplica TicketBAI de forma independiente, con tres autoridades provinciales
que mantienen cada una sus propios esquemas XSD y endpoints. Navarra opera NaTicket. La Ley
Crea y Crece exige la facturación electrónica B2B para todas las empresas, con formato
pendiente del reglamento de desarrollo. La detección del régimen a partir del domicilio
fiscal y el volumen de operaciones es un requisito previo a todas las demás operaciones —
utilice `es__detect_regional_regime` en primer lugar.

---

## Cobertura regulatoria

| Sistema | Ámbito | Formato | Obligatorio desde | Estado |
|---|---|---|---|---|
| **VERI\*FACTU** | Todas las empresas no-SII | XML propietario (XSD v1.0 HAC/1177/2024) | IS: ene 2027 / Otros: jul 2027 (RD-ley 15/2025) | ⚠️ Pendiente |
| **Facturae / FACe** | B2G (sector público) | Facturae 3.2.2 + XAdES-EPES | Obligatorio desde 2015 (Ley 25/2013) | ⚠️ Pendiente |
| **SII** | Facturación >€6M, grupos IVA, REDEME | XML SOAP/REST AEAT | Ya obligatorio (RD 596/2016) | ⚠️ Pendiente |
| **TicketBAI** | Álava, Gipuzkoa, Bizkaia | XML provincial + XAdES + QR | Según provincia, 2022–2023 | ⚠️ Pendiente |
| **Crea y Crece (B2B)** | Todas las empresas (umbral pendiente) | UBL 2.1 o Facturae 3.2.2 (EN 16931) | Reglamento de desarrollo pendiente | ⚠️ Pendiente |
| **NaTicket** | Navarra | XML foral + firma | Mandato foral (implantación escalonada) | Parcial (vía `es__detect_regional_regime`) |

> **Exclusión mutua SII / VERI\*FACTU (Real Decreto 254/2025):** Los contribuyentes
> inscritos en el SII quedan exentos de VERI\*FACTU. Utilice `es__check_b2b_mandate_applicability`
> antes de generar cualquier registro.

---

## Herramientas

### VERI\*FACTU

#### `es__generate_verifactu_record`

Genera un registro de factura inviolable (Orden HAC/1177/2024) con encadenamiento SHA-256
`Huella` que lo vincula al registro anterior.

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `invoice` | `InvoiceDocument` | Sí | Modelo de factura del core (vendedor, comprador, líneas, IVA) |
| `previous_hash` | `string` | No | SHA-256 `Huella` del registro precedente (`null` = primero en la cadena) |
| `software_id` | `string` | Sí | `IDSistemaInformatico` del software certificado |
| `software_nif` | `string` | Sí | NIF del fabricante del software |
| `invoice_type` | `string` | Sí | `F1`, `F2`, `R1`–`R5` o `F3` |

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

> ⚠️ Pendiente de confirmación regulatoria — XSD v1.0 (HAC/1177/2024) no validado aún contra el entorno de pruebas de la AEAT.

---

#### `es__validate_verifactu_record`

Valida un registro VERI\*FACTU XML contra el XSD oficial publicado con la Orden HAC/1177/2024
(BOE-A-2024-22138).

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `xml` | `string` | Sí | Registro VERI\*FACTU XML en crudo |
| `schema_version` | `string` | No | Versión del esquema (por defecto: `"1.0"`) |

```json
{ "tool": "es__validate_verifactu_record", "arguments": { "xml": "<RegistroFacturacion>...</RegistroFacturacion>" } }
```

> ⚠️ Pendiente de confirmación regulatoria

---

#### `es__submit_verifactu_to_aeat`

Envía un registro VERI\*FACTU firmado al endpoint en tiempo real de la AEAT mediante MTLS
(certificado FNMT-RCM Clase 1). Respeta `AEAT_ENV=sandbox|production`.

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `xml` | `string` | Sí | XML VERI\*FACTU firmado |
| `nif` | `string` | Sí | NIF del remitente |

```json
{ "tool": "es__submit_verifactu_to_aeat", "arguments": { "xml": "<RegistroFacturacion>...</RegistroFacturacion>", "nif": "B12345678" } }
```

> ⚠️ Pendiente de confirmación regulatoria — `AuthMode.MTLS` no está implementado aún en `mcp-einvoicing-core`; registrado en el backlog de gaps del core.

---

#### `es__generate_qr_verifactu`

Genera el código QR obligatorio de VERI\*FACTU (HAC/1177/2024 Art. 10) como PNG en base64.
Codifica la URL de verificación de la AEAT con el texto "Factura verificable en la sede
electrónica de la AEAT". Candidato a promoción a `mcp-einvoicing-core` (generación de QR).

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `nif` | `string` | Sí | NIF del emisor |
| `invoice_number` | `string` | Sí | `NumSerieFactura` |
| `invoice_date` | `string` | Sí | `FechaExpedicionFactura` (YYYY-MM-DD) |
| `total_amount` | `number` | Sí | Total de la factura con IVA incluido |
| `size_px` | `integer` | No | Tamaño del QR en píxeles (por defecto: 200) |

```json
{ "tool": "es__generate_qr_verifactu", "arguments": { "nif": "B12345678", "invoice_number": "2025-0042", "invoice_date": "2025-03-15", "total_amount": 1210.00 } }
```

> ⚠️ Pendiente de confirmación regulatoria

---

#### `es__cancel_verifactu_record`

Genera un registro de anulación VERI\*FACTU (`IndicadorAnulacion=S`, `TipoHuella=01`)
encadenado a la secuencia de huellas actual.

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `original_invoice_number` | `string` | Sí | `NumSerieFactura` a anular |
| `original_invoice_date` | `string` | Sí | `FechaExpedicionFactura` (YYYY-MM-DD) |
| `issuer_nif` | `string` | Sí | NIF del emisor |
| `previous_hash` | `string` | Sí | `Huella` del último registro en la cadena |

```json
{ "tool": "es__cancel_verifactu_record", "arguments": { "original_invoice_number": "2025-0042", "original_invoice_date": "2025-03-15", "issuer_nif": "B12345678", "previous_hash": "3C4A9B..." } }
```

> ⚠️ Pendiente de confirmación regulatoria

---

### Facturae / FACe

#### `es__generate_facturae_xml`

Genera una factura XML conforme a Facturae 3.2.2 para su envío B2G. Utiliza
`InvoiceDocument` de `mcp-einvoicing-core`.

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `invoice` | `InvoiceDocument` | Sí | Modelo de factura del core |
| `schema_version` | `string` | No | Versión del esquema Facturae (por defecto: `"3.2.2"`) |

```json
{ "tool": "es__generate_facturae_xml", "arguments": { "invoice": { "date": "2025-03-15", "number": "2025-0042", "seller": { "tax_id": { "country_code": "ES", "identifier": "B12345678" }, "name": "Proveedor SL" }, "buyer": { "tax_id": { "country_code": "ES", "identifier": "S2800000D" }, "name": "Ayuntamiento de Madrid" }, "lines": [{ "line_number": 1, "description": "Suministro", "quantity": 5, "unit_price": 200.00, "vat_rate": 21.0 }] } } }
```

> ⚠️ Pendiente de confirmación regulatoria

---

#### `es__sign_facturae_xades`

Aplica una firma digital XAdES-EPES (ETSI EN 319 132-1) a un documento Facturae XML.
Candidato a promoción a `mcp-einvoicing-core` (firma XAdES — puntuación 3/3).

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `xml` | `string` | Sí | XML Facturae sin firmar |
| `cert_path` | `string` | Sí | Ruta al certificado PKCS#12 (`.p12` / `.pfx`) |
| `cert_password` | `string` | Sí | Contraseña del certificado |
| `signature_policy_id` | `string` | No | OID de la política de firma (por defecto: estándar Facturae) |

```json
{ "tool": "es__sign_facturae_xades", "arguments": { "xml": "<Facturae>...</Facturae>", "cert_path": "/certs/empresa.p12", "cert_password": "s3cr3t" } }
```

> ⚠️ Pendiente de confirmación regulatoria

---

#### `es__submit_to_face`

Envía un XML Facturae firmado a FACe (Punto General de Entrada de Facturas Electrónicas)
a través de la API REST B2B de FACe v2. Requiere OAuth2 (`FACE_CLIENT_ID` / `FACE_CLIENT_SECRET`).

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `xml` | `string` | Sí | XML Facturae con firma XAdES |
| `administrative_unit` | `string` | Sí | Código `UnidadTramitadora` de FACe |
| `accounting_office` | `string` | Sí | Código `OficinasContables` de FACe |
| `management_body` | `string` | Sí | Código `OrganoGestor` de FACe |

```json
{ "tool": "es__submit_to_face", "arguments": { "xml": "<Facturae>...</Facturae>", "administrative_unit": "U00000038", "accounting_office": "U00000038", "management_body": "U00000038" } }
```

> ⚠️ Pendiente de confirmación regulatoria

---

#### `es__get_face_invoice_status`

Consulta el estado de tramitación de una factura en FACe. Devuelve los códigos estándar:
1200 (Registrada), 2400 (Reconocida), 3100 (Rechazada), 4100 (Pagada).

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `invoice_id` | `string` | Sí | Número de registro FACe |

```json
{ "tool": "es__get_face_invoice_status", "arguments": { "invoice_id": "FAC-2025-00012345" } }
```

> ⚠️ Pendiente de confirmación regulatoria

---

#### `es__validate_facturae_schema`

Valida un XML Facturae contra el XSD oficial de Facturae 3.2.2 mediante `lxml`. Devuelve
errores estructurados con ubicaciones XPath.

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `xml` | `string` | Sí | XML Facturae a validar |
| `schema_version` | `string` | No | Versión del esquema (por defecto: `"3.2.2"`) |

```json
{ "tool": "es__validate_facturae_schema", "arguments": { "xml": "<Facturae>...</Facturae>" } }
```

> ⚠️ Pendiente de confirmación regulatoria

---

### SII (Suministro Inmediato de Información)

#### `es__build_sii_invoice_record`

Construye un registro XML AEAT SII (emisión `FacturaExpedida` o recepción `FacturaRecibida`)
conforme a la guía técnica SII de la AEAT v3.0 (abril 2024). Soporta `TipoComunicacion` A0/A1/A4.

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `invoice` | `InvoiceDocument` | Sí | Modelo de factura del core |
| `record_type` | `string` | Sí | `"issued"` (emitida) o `"received"` (recibida) |
| `communication_type` | `string` | No | `"A0"` alta (por defecto), `"A1"` modificación, `"A4"` baja |

```json
{ "tool": "es__build_sii_invoice_record", "arguments": { "invoice": { "date": "2025-03-15", "number": "2025-0042" }, "record_type": "issued", "communication_type": "A0" } }
```

> ⚠️ Pendiente de confirmación regulatoria

---

#### `es__submit_sii_batch`

Envía un lote de facturas (máximo 10.000 registros) al endpoint SOAP SII de la AEAT. Requiere MTLS.

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `records` | `array` | Sí | Lista de cadenas XML de `es__build_sii_invoice_record` |
| `record_type` | `string` | Sí | `"issued"` o `"received"` |
| `fiscal_year` | `integer` | Sí | Ejercicio fiscal (YYYY) |

```json
{ "tool": "es__submit_sii_batch", "arguments": { "records": ["<RegistroLRFacturasEmitidas>...</RegistroLRFacturasEmitidas>"], "record_type": "issued", "fiscal_year": 2025 } }
```

> ⚠️ Pendiente de confirmación regulatoria — `AuthMode.MTLS` no está implementado aún en `mcp-einvoicing-core`.

---

#### `es__query_sii_status`

Consulta el estado de un lote SII enviado mediante `ConsultaFactInformadasEmitidas` o
`ConsultaFactInformadasRecibidas`.

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `batch_id` | `string` | Sí | Referencia del lote devuelta por `es__submit_sii_batch` |
| `record_type` | `string` | Sí | `"issued"` o `"received"` |

```json
{ "tool": "es__query_sii_status", "arguments": { "batch_id": "SII-BATCH-20250315-001", "record_type": "issued" } }
```

> ⚠️ Pendiente de confirmación regulatoria

---

#### `es__generate_sii_correction`

Genera un registro de modificación SII (`A1`) o baja (`A4`) que referencia la factura
original mediante `IDFactura`. El constructor de facturas rectificativas es candidato a
`mcp-einvoicing-core` (puntuación 3/3).

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `original_invoice` | `InvoiceDocument` | Sí | Factura que se rectifica |
| `corrected_invoice` | `InvoiceDocument` | No | Datos corregidos (`null` para A4) |
| `correction_type` | `string` | Sí | `"A1"` o `"A4"` |
| `record_type` | `string` | Sí | `"issued"` o `"received"` |

```json
{ "tool": "es__generate_sii_correction", "arguments": { "original_invoice": { "number": "2025-0042" }, "correction_type": "A1", "record_type": "issued" } }
```

> ⚠️ Pendiente de confirmación regulatoria

---

### TicketBAI

#### `es__generate_ticketbai_xml`

Genera una factura XML TicketBAI con firma XAdES y cadena `HuellaTBAI`. Selecciona
automáticamente el XSD provincial correcto: Álava v1.2, Gipuzkoa v1.2, Bizkaia v2.1.

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `invoice` | `InvoiceDocument` | Sí | Modelo de factura del core |
| `province` | `string` | Sí | `"araba"`, `"gipuzkoa"` o `"bizkaia"` |
| `previous_hash` | `string` | No | `HuellaTBAI` del registro precedente |
| `software_license` | `string` | Sí | Clave de licencia del software TicketBAI |
| `cert_path` | `string` | Sí | Ruta del certificado de firma |
| `cert_password` | `string` | Sí | Contraseña del certificado |

```json
{ "tool": "es__generate_ticketbai_xml", "arguments": { "invoice": { "date": "2025-03-15", "number": "2025-0042" }, "province": "gipuzkoa", "software_license": "TBAI-GI-12345", "cert_path": "/certs/empresa.p12", "cert_password": "s3cr3t" } }
```

> ⚠️ Pendiente de confirmación regulatoria — los tres XSD provinciales deben empaquetarse por separado; no se deben validar cruzadamente entre provincias.

---

#### `es__submit_ticketbai`

Envía un registro TicketBAI XML a la autoridad provincial vasca correspondiente. El endpoint
se enruta automáticamente: Álava (`batuz.eus`), Gipuzkoa (`tbai.egoitza.gipuzkoa.eus`),
Bizkaia (`www.bizkaia.eus/ogasun`).

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `xml` | `string` | Sí | XML TicketBAI firmado |
| `province` | `string` | Sí | `"araba"`, `"gipuzkoa"` o `"bizkaia"` |
| `nif` | `string` | Sí | NIF del remitente |

```json
{ "tool": "es__submit_ticketbai", "arguments": { "xml": "<T:TicketBai>...</T:TicketBai>", "province": "bizkaia", "nif": "B12345678" } }
```

> ⚠️ Pendiente de confirmación regulatoria

---

#### `es__validate_ticketbai_schema`

Valida un documento XML TicketBAI contra el XSD provincial correcto. Los esquemas
**no son intercambiables** entre provincias.

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `xml` | `string` | Sí | XML TicketBAI |
| `province` | `string` | Sí | `"araba"`, `"gipuzkoa"` o `"bizkaia"` |

```json
{ "tool": "es__validate_ticketbai_schema", "arguments": { "xml": "<T:TicketBai>...</T:TicketBai>", "province": "gipuzkoa" } }
```

> ⚠️ Pendiente de confirmación regulatoria

---

### Crea y Crece / B2B

#### `es__generate_b2b_einvoice_es`

Genera una factura B2B conforme a EN 16931 en formato UBL 2.1 o Facturae 3.2.2 según
la Ley 18/2022.

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `invoice` | `InvoiceDocument` | Sí | Modelo de factura del core |
| `format` | `string` | No | `"ubl"` (por defecto) o `"facturae"` |

```json
{ "tool": "es__generate_b2b_einvoice_es", "arguments": { "invoice": { "date": "2025-03-15", "number": "2025-0042" }, "format": "ubl" } }
```

> ⚠️ Pendiente de confirmación regulatoria — el reglamento de desarrollo del mandato B2B no está publicado aún.

---

#### `es__check_b2b_mandate_applicability`

Determina el régimen aplicable (VERI\*FACTU, SII, TicketBAI, NaTicket) a partir del
volumen de operaciones, el código de provincia y la inscripción en el SII. Aplica la lógica
de exclusión mutua del Real Decreto 254/2025.

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `annual_turnover_eur` | `number` | Sí | Volumen anual de operaciones IVA en EUR |
| `tax_address_province_code` | `string` | Sí | Código de provincia INE (p. ej., `"28"` Madrid) |
| `enrolled_in_sii` | `boolean` | No | Inscripción en el SII (por defecto: `false`) |
| `entity_type` | `string` | No | `"IS"` (Impuesto sobre Sociedades) o `"IRPF"` |

```json
{ "tool": "es__check_b2b_mandate_applicability", "arguments": { "annual_turnover_eur": 2500000, "tax_address_province_code": "28", "enrolled_in_sii": false, "entity_type": "IS" } }
```

> ⚠️ Pendiente de confirmación regulatoria

---

### Herramientas de utilidad

#### `es__detect_regional_regime`

Detecta el régimen de facturación electrónica aplicable a partir del código de provincia INE.
Devuelve `VERIFACTU`, `TICKETBAI`, `NATICKET` o `VERIFACTU+SII`.

Provincias vascas: `01` Álava, `20` Gipuzkoa, `48` Bizkaia. Navarra: `31`.
El resto devuelve `VERIFACTU`. Candidato a promoción a `mcp-einvoicing-core`.

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `province_code` | `string` | Sí | Código de provincia INE de dos dígitos |
| `enrolled_in_sii` | `boolean` | No | Inscripción en el SII (por defecto: `false`) |

```json
{ "tool": "es__detect_regional_regime", "arguments": { "province_code": "20", "enrolled_in_sii": false } }
```

> ⚠️ Pendiente de confirmación regulatoria

---

#### `es__get_compliance_status`

Devuelve los plazos de mandato vigentes y el sistema operativo para un perfil de empresa.
Refleja el RD-ley 15/2025 — sujeto a cambios por legislación posterior.
Candidato a promoción a `mcp-einvoicing-core` (registro genérico de plazos).

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `entity_type` | `string` | Sí | `"IS"` o `"IRPF"` |
| `province_code` | `string` | Sí | Código de provincia INE |
| `annual_turnover_eur` | `number` | No | Para la verificación del umbral SII (€6M) |
| `enrolled_in_sii` | `boolean` | No | Inscripción en el SII |

```json
{ "tool": "es__get_compliance_status", "arguments": { "entity_type": "IS", "province_code": "28", "annual_turnover_eur": 1000000, "enrolled_in_sii": false } }
```

> ⚠️ Pendiente de confirmación regulatoria

---

#### `es__parse_aeat_response`

Analiza y normaliza una respuesta XML de la AEAT (VERI\*FACTU o SII) en JSON estructurado.
Extrae `EstadoEnvio` (`Correcto`/`AceptadoConErrores`/`Incorrecto`), `CSV`
(código seguro de verificación) y detalle de errores. Candidato a promoción a
`mcp-einvoicing-core` (analizador genérico de respuestas XML de proveedores — puntuación 2/3).

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `xml` | `string` | Sí | Respuesta XML de la AEAT en crudo |
| `response_type` | `string` | No | `"verifactu"` (por defecto) o `"sii"` |

```json
{ "tool": "es__parse_aeat_response", "arguments": { "xml": "<RespuestaRegFactuSistemaFacturacion>...</RespuestaRegFactuSistemaFacturacion>", "response_type": "verifactu" } }
```

> ⚠️ Pendiente de confirmación regulatoria

---

## Instalación

### Desde PyPI (recomendado)

```bash
pip install mcp-facturacion-electronica-es
```

Sin instalación previa, con `uvx`:

```bash
uvx mcp-facturacion-electronica-es
```

### Desde las fuentes

```bash
git clone https://github.com/cmendezs/mcp-facturacion-electronica-es.git
cd mcp-facturacion-electronica-es
uv sync --all-extras
```

---

## Configuración

### Claude Desktop

```json
{
  "mcpServers": {
    "facturacion-es": {
      "command": "uvx",
      "args": ["mcp-facturacion-electronica-es"],
      "env": {
        "AEAT_ENV": "sandbox",
        "AEAT_CERTIFICATE_PATH": "/ruta/al/cert.p12",
        "AEAT_CERTIFICATE_PASSWORD": "contraseña-del-certificado"
      }
    }
  }
}
```

Toda la configuración se realiza mediante variables de entorno o un archivo `.env`.

### AEAT / VERI\*FACTU / SII

| Variable | Descripción | Obligatorio |
|---|---|---|
| `AEAT_ENV` | `sandbox` o `production` | Sí |
| `AEAT_CERTIFICATE_PATH` | Ruta al certificado PKCS#12 FNMT-RCM | Para el envío |
| `AEAT_CERTIFICATE_PASSWORD` | Contraseña del certificado | Para el envío |
| `AEAT_NIF` | NIF del contribuyente | Para el envío |

### FACe

| Variable | Descripción | Obligatorio |
|---|---|---|
| `FACE_ENV` | `sandbox` o `production` | Sí |
| `FACE_CLIENT_ID` | ID de cliente OAuth2 | Sí |
| `FACE_CLIENT_SECRET` | Secreto de cliente OAuth2 | Sí |

### TicketBAI

| Variable | Descripción | Obligatorio |
|---|---|---|
| `TICKETBAI_ENV` | `sandbox` o `production` | Sí |
| `TICKETBAI_CERTIFICATE_PATH` | Ruta del certificado de firma provincial | Sí |
| `TICKETBAI_CERTIFICATE_PASSWORD` | Contraseña del certificado | Sí |

### Comunes (heredadas de `mcp-einvoicing-core`)

| Variable | Descripción | Por defecto |
|---|---|---|
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |

---

## Arquitectura

`mcp-facturacion-electronica-es` es un adaptador de país dentro de la familia `mcp-einvoicing`,
construido sobre `mcp-einvoicing-core`.

```
mcp-einvoicing-core (v0.1.0+)
│   BaseDocumentGenerator, BaseDocumentValidator, BaseLifecycleManager
│   InvoiceDocument, InvoiceParty, InvoiceLineItem, VATSummary, PaymentTerms
│   EInvoicingError, ValidationError, XSDValidationError, PlatformError
│   BaseEInvoicingClient, OAuthConfig, AuthMode (OAUTH2 / BEARER / MTLS)
│   get_logger, format_amount, xml_element, format_error
│
├── mcp-facture-electronique-fr    (Francia — XP Z12-013, Chorus Pro)
├── mcp-einvoicing-be              (Bélgica — Peppol BIS 3.0, PINT-BE, Mercurius)
├── mcp-facturacion-electronica-es (España — este paquete)
│   ├── verifactu/   generación de registros, cadena hash, QR, anulación
│   ├── facturae/    XML Facturae 3.2.2, XAdES-EPES, envío FACe
│   ├── sii/         construcción de lotes, SOAP AEAT, rectificaciones
│   ├── ticketbai/   generación XML, enrutamiento provincial, validación
│   ├── b2b/         UBL/Facturae Crea y Crece, detector de mandato
│   └── utils/       detección de régimen, analizador respuestas AEAT, registro de plazos
├── mcp-fattura-elettronica-it     (Italia — FatturaPA / SDI)
└── mcp-ksef-pl                    (Polonia — KSeF / FA(2))
```

### Funciones candidatas a `mcp-einvoicing-core`

| Función | Puntuación | Acción |
|---|---|---|
| Firma digital XAdES | 3/3 (FR, ES, IT) | DEBE promoverse — abrir issue en `mcp-einvoicing-core` |
| Generación de código QR | 3/3 (FR, ES, TicketBAI) | DEBE promoverse |
| Enrutador sandbox/producción | 3/3 (FR, BE, ES) | DEBE promoverse |
| Constructor de facturas rectificativas | 3/3 (BE, ES, FR) | DEBE promoverse |
| Cadena hash de facturas (huella) | 2/3 (ES, FR NF525) | DEBERÍA promoverse |
| Registro de plazos de mandato | 2/3 (FR, ES) | DEBERÍA promoverse |

---

## Notas de cumplimiento normativo

> **Aviso:** Las fechas de mandato reflejan el RD-ley 15/2025 (diciembre 2025) y están
> sujetas a cambios por legislación posterior o instrucciones administrativas de la AEAT.
> Este software no constituye asesoramiento jurídico ni fiscal.

### Calendario de mandatos

| Sistema | Destinatarios | Plazo |
|---|---|---|
| SII | Facturación >€6M / grupos IVA / REDEME | Ya obligatorio (RD 596/2016) |
| Facturae/FACe | Todos los proveedores B2G | Ya obligatorio (Ley 25/2013) |
| TicketBAI | Todas las empresas del País Vasco | Implantación sectorial 2022–2023 |
| VERI\*FACTU | Contribuyentes IS (Impuesto sobre Sociedades) | **Enero 2027** (RD-ley 15/2025) |
| VERI\*FACTU | IRPF + otros no-SII | **Julio 2027** (RD-ley 15/2025) |
| Crea y Crece B2B | Todas las empresas | Pendiente — reglamento de desarrollo sin publicar |

### Excepciones regionales

- **País Vasco:** TicketBAI aplica **en lugar de** VERI\*FACTU.
  Cada una de las tres provincias (Álava, Gipuzkoa, Bizkaia) tiene un XSD, endpoint
  y proceso de certificación de software distintos. Los endpoints nacionales de la AEAT no aplican.
- **Navarra:** Aplica NaTicket (Hacienda Foral de Navarra). VERI\*FACTU no aplica.
- **Ceuta / Melilla:** IPSI (no IVA); la aplicabilidad del SII/VERI\*FACTU difiere — verificar con la AEAT.
- **Exclusión mutua SII / VERI\*FACTU:** El Real Decreto 254/2025 hace estos sistemas
  mutuamente excluyentes. Los contribuyentes inscritos en el SII no envían registros VERI\*FACTU.

Todos los endpoints de envío de la AEAT requieren un certificado FNMT-RCM o de CA acreditada.
La AEAT dispone de un entorno de pruebas gratuito en `prewww2.aeat.es`.

---

## Tests

```bash
# Instalar dependencias de desarrollo
uv sync --all-extras

# Ejecutar la suite de tests completa
uv run pytest tests/ -v

# Con informe de cobertura
uv run pytest --cov=mcp_facturacion_electronica_es --cov-report=term-missing
```

---

## Hoja de ruta

Los elementos pendientes se han extraído directamente de los marcadores `[NEED]` presentes en el código fuente. Cada versión es un prerequisito de la siguiente y debe pasar el audit gate (`make audit`) antes de publicarse.

### v0.1.0 (actual) — Scaffold y generación local

Herramientas implementadas con XML válido generado localmente, validación estructural, lógica de régimen y firma XAdES. Sin envíos a plataformas externas confirmados contra entornos reales.

---

### v0.2.0 — Bundle de esquemas XSD y correcciones de protocolo

**Validación XSD completa (ahora solo estructural):**

| Tarea | Archivo | Referencia normativa |
|---|---|---|
| Descargar XSD v1.0 VERI\*FACTU en `specs/verifactu/` | `tools/verifactu.py` | BOE-A-2024-22138 (Orden HAC/1177/2024) |
| Descargar XSD Facturae 3.2.2 en `specs/facturae/` | `tools/facturae.py` | facturae.gob.es |
| Descargar XSD TicketBAI Álava v1.2 en `specs/ticketbai/araba/` | `tools/ticketbai.py` | batuz.eus |
| Descargar XSD TicketBAI Gipuzkoa v1.2 en `specs/ticketbai/gipuzkoa/` | `tools/ticketbai.py` | gipuzkoa.eus |
| Descargar XSD TicketBAI Bizkaia v2.1 en `specs/ticketbai/bizkaia/` | `tools/ticketbai.py` | bizkaia.eus |

**Políticas de firma XAdES:**

| Tarea | Archivo |
|---|---|
| Calcular SHA-256 del PDF de política Facturae (Orden EHA/962/2007) y asignar `FACTURAE_POLICY_HASH` en `_helpers.py` | `_helpers.py`, `tools/facturae.py` |
| Obtener y asignar los hash SHA-256 de las políticas provinciales TicketBAI (Álava, Gipuzkoa, Bizkaia) en `TICKETBAI_POLICY_IDS` | `_helpers.py`, `tools/ticketbai.py` |
| Verificar los tres URI de política TicketBAI contra la documentación técnica oficial de cada provincia | `_helpers.py` |

**Correcciones de protocolo:**

| Tarea | Archivo |
|---|---|
| Verificar el algoritmo HuellaTBAI contra la especificación técnica oficial (¿bytes en crudo, Base64 decodificado o texto?) | `tools/ticketbai.py` |
| Rellenar el elemento `Claves` de TicketBAI con los tipos de factura correctos | `tools/ticketbai.py` |
| Añadir `HoraExpedicionFactura` como parámetro de entrada en `es__generate_ticketbai_xml` | `tools/ticketbai.py` |
| Confirmar el formato exacto y los parámetros de la URL del QR VERI\*FACTU (Art. 10 HAC/1177/2024) | `tools/verifactu.py` |
| Añadir campos IBAN y BIC al bloque `AccountToBeCredited` de Facturae 3.2.2 | `tools/facturae.py` |

---

### v0.3.0 — Verificación de endpoints y sandbox

**AEAT — VERI\*FACTU:**

| Tarea | Archivo |
|---|---|
| Verificar la URL del endpoint sandbox de VERI\*FACTU una vez que la AEAT abra el entorno de pruebas | `tools/verifactu.py`, `_helpers.py` |
| Confirmar la URL de producción de VERI\*FACTU contra la guía técnica publicada por la AEAT | `_helpers.py` |

**AEAT — SII:**

| Tarea | Archivo |
|---|---|
| Confirmar la URL del sandbox SII (¿`www7` o `www10`?) contra la guía técnica SII v3.0 | `_helpers.py`, `tools/sii.py` |
| Validar la estructura del SOAP envelope contra el sandbox SII v3.0 de la AEAT | `tools/sii.py` |

**FACe:**

| Tarea | Archivo |
|---|---|
| Verificar la ruta base de la API FACe B2B v2 (puede haber cambiado en 2025) | `_helpers.py` |
| Verificar la URL del endpoint OAuth2 de FACe para sandbox y producción | `tools/facturae.py` |
| Validar el flujo OAuth2 completo de FACe contra credenciales reales del sandbox | `tools/facturae.py` |

**TicketBAI:**

| Tarea | Archivo |
|---|---|
| Verificar el endpoint sandbox de Álava (¿mismo que producción con NIF de prueba?) | `_helpers.py` |
| Verificar la ruta de la API LROE de Bizkaia (esquema de envío diferente al resto) | `_helpers.py` |
| Confirmar el método de autenticación por provincia (certificado MTLS, API key, etc.) | `tools/ticketbai.py` |

---

### v0.4.0 — Cadena completa y lotes SII correctos

| Tarea | Archivo | Detalle |
|---|---|---|
| Almacenar y propagar `IDEmisorFacturaAnterior`, `NumSerieFacturaAnterior` y `FechaAnterior` para el encadenamiento completo de VERI\*FACTU | `tools/verifactu.py` | Actualmente solo se encadena la `Huella`; la especificación exige también los identificadores del registro anterior |
| Fusionar múltiples registros `RegistroLRFacturas` en un único `SuministroLRFacturasEmitidas` para el lote SII real | `tools/sii.py` | El comportamiento actual envía cada registro por separado |
| Construir el envelope SOAP `ConsultaFactInformadasEmitidas` / `ConsultaFactInformadasRecibidas` con filtro por `IDFactura` en `es__query_sii_status` | `tools/sii.py` | Actualmente envía una petición GET genérica |
| Documentar o implementar el flujo de firma XAdES del registro VERI\*FACTU antes del envío | `tools/verifactu.py` | El registro generado por `es__generate_verifactu_record` debe firmarse antes de enviarse a la AEAT |
| Parsear la respuesta AEAT en el handler `es__submit_verifactu_to_aeat` usando `es__parse_aeat_response` | `tools/verifactu.py` | Actualmente devuelve el texto crudo |

---

### v0.5.0 — Crea y Crece B2B + endurecimiento del audit

| Tarea | Archivo | Detalle |
|---|---|---|
| Confirmar los requisitos de formato B2B (UBL 2.1 vs. Facturae 3.2.2) una vez publicado el reglamento de desarrollo de la Ley 18/2022 | `tools/b2b.py` | El reglamento está pendiente de publicación a fecha de mayo 2026 |
| Actualizar `_INTENTIONAL_OVERRIDES` y `_CORE_MODULES_TO_CHECK` en el audit una vez que la API pública de `mcp-einvoicing-core` esté finalizada | `audit/audit_vs_core.py` | Reducirá los 66 avisos actuales de CHECK 1 |
| Sustituir el parser de versiones PEP 440 artesanal por `packaging.version` | `audit/audit_vs_core.py` | El parser actual solo soporta `>=X` y `<Y` |
| Actualizar CHECK 5 con las comprobaciones adicionales del registro de categorías de herramientas de `mcp-einvoicing-core` | `audit/audit_vs_core.py` | — |

---

### v1.0.0 — Preparado para producción

- Todas las verificaciones de sandbox completadas
- Todas las validaciones XSD habilitadas (specs/ poblado)
- Cobertura completa del mandato VERI\*FACTU (enero y julio 2027)
- Software TicketBAI certificado por las tres provincias vascas
- Reglamento Crea y Crece B2B publicado e implementado
- Audit gate sin ningún aviso (exit code 0)

---

## Contribuir

Abra un issue antes de iniciar trabajo significativo. Para lógica de utilidad reutilizable
entre adaptadores de país, abra un issue de `core-promotion` en `mcp-einvoicing-core` antes
de implementarla — utilice la rúbrica de puntuación (3 = DEBE promoverse, 2 = DEBERÍA, 1 = mantener aquí).

```bash
git clone https://github.com/cmendezs/mcp-facturacion-electronica-es.git
cd mcp-facturacion-electronica-es
uv sync --all-extras
uv run pytest
make audit
```

Todas las afirmaciones regulatorias deben referenciar una publicación específica del BOE,
una versión oficial del XSD o una versión de la guía técnica de la AEAT. No elimine
`⚠️ Pendiente de confirmación regulatoria` sin enlazar la fuente verificada en la
descripción del PR.

---

## Resumen del Audit — Fase 1

| Verificación | Resultado | Notas |
|---|---|---|
| Contrato con el core | PENDIENTE | Sin código fuente — todos los contratos definidos, ninguno implementado |
| Cobertura de herramientas | 0/22 | Las 22 herramientas están especificadas; ninguna implementada |
| Exactitud regulatoria | 0/22 verificadas | Todas las herramientas llevan `⚠️` de implementación pendiente |
| Promoción al core | 6 candidatos | XAdES, QR, enrutador URL, cadena hash, factura rectificativa, registro de plazos |

Este README es el **documento de especificación** para la fase de implementación.
Los badges de las herramientas se actualizarán a ✅ a medida que cada herramienta supere
la verificación regulatoria.

---

## Otros servidores MCP de facturación electrónica

| País | Servidor |
|---------|--------|
| 🌍 Global | [mcp-einvoicing-core](https://github.com/cmendezs/mcp-einvoicing-core) |
| 🇩🇪 Alemania | [mcp-einvoicing-de](https://github.com/cmendezs/mcp-einvoicing-de) |
| 🇧🇪 Bélgica | [mcp-einvoicing-be](https://github.com/cmendezs/mcp-einvoicing-be) |
| 🇪🇸 España | [mcp-facturacion-electronica-es](https://github.com/cmendezs/mcp-facturacion-electronica-es) |
| 🇫🇷 Francia | [mcp-facture-electronique-fr](https://github.com/cmendezs/mcp-facture-electronique-fr) |
| 🇮🇹 Italia | [mcp-fattura-elettronica-it](https://github.com/cmendezs/mcp-fattura-elettronica-it) |
| 🇵🇱 Polonia | [mcp-ksef-pl](https://github.com/cmendezs/mcp-ksef-pl) |

---

## Licencia

Publicado bajo la [licencia Apache 2.0](LICENSE).
Copyright 2025–2026 Christophe Méndez y colaboradores.
