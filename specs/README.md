# mcp-facturacion-electronica-es — Specification Assets

This directory contains the authoritative schema, WSDL, XSLT, and reference
documentation assets for the Spanish e-invoicing systems supported by this package.

TicketBAI (País Vasco) is explicitly out of scope for this package.

## Directory layout

```
specs/
├── facturae/                   Factura-e 3.2.2 / FACe B2G submission platform
│   ├── documentation/          FACe REST API and SOAP protocol manuals
│   ├── examples/               Sample signed Factura-e invoice (.xsig)
│   └── xslt/                   Official XSLT/XSL viewer stylesheets (3.2.1, 3.2.2)
├── sii/                        SII (Suministro Inmediato de Información) — AEAT VAT reporting
│   ├── documentation/          Validation rules PDF + AEAT presentation
│   ├── examples/               Sample SOAP request/response XML files
│   └── schemas/                WSDL service contracts + XSD data schemas
├── verifactu/                  VeriFactu — real-time AEAT invoice registry (RD 1007/2023)
│   └── documentation/          BOE legal text (original + consolidated)
└── crea-y-crece/               Ley Crea y Crece — future B2B mandate (Ley 18/2022)
    └── documentation/          BOE law text only; technical specs pending Ministerial Order
```

## Sources and versions

| Asset | Version | Source |
|---|---|---|
| FACe REST API manuals | Current | https://www.face.gob.es |
| FACe SOAP protocol manuals | Current | https://www.face.gob.es |
| SII WSDL schemas | v2 | https://www.agenciatributaria.es (SII) |
| SII XSD schemas | v2 | https://www.agenciatributaria.es (SII) |
| Factura-e XSLT viewer (3.2.1) | 3.2.1 | https://www.facturae.gob.es |
| Factura-e XSLT viewer (3.2.2) | 3.2.2 | https://www.facturae.gob.es |
| VeriFactu — BOE-A-2024-22138 | Orden HAC/1177/2024 | https://www.boe.es |
| VeriFactu — BOE-A-2024-22138 (consolidated) | RD 1007/2023 + HAC/1177/2024 | https://www.boe.es |
| Ley Crea y Crece — BOE-A-2022-15818 | Ley 18/2022 | https://www.boe.es |

## Pending specs

| System | Status | Notes |
|---|---|---|
| Crea y Crece technical spec | `[PENDING]` | Ministerial Order not yet published; monitor PAe Factura Electrónica page |

## Factura-e XSD

| File | Description |
|---|---|
| `facturae/xsd/Facturaev3_2_2.xml` | Factura-e 3.2.2 main XSD schema |

**Target namespace (authoritative):** `http://www.facturae.gob.es/formato/Versiones/Facturaev3_2_2.xml`

Note: The file is an XSD document. The `.xml` extension is kept intentionally — the targetNamespace URI itself ends in `Facturaev3_2_2.xml`, and external importers may reference it by that name. Renaming to `.xsd` would break schemaLocation cross-references.

## VeriFactu XSD bundle

All 7 files belong in the same directory (`verifactu/xsd/`) because the schemas import each other by relative `schemaLocation`.

| File | Root element / purpose |
|---|---|
| `SuministroInformacion.xsd` | Core data types: `RegistroAlta`, `RegistroAnulacion`, `EncadenamientoFacturaAnteriorType` |
| `SuministroLR.xsd` | Submission envelope: `RegFactuSistemaFacturacion` (up to 1,000 records) |
| `RespuestaSuministro.xsd` | Submission response: `RespuestaRegFactuSistemaFacturacion` |
| `ConsultaLR.xsd` | Query request: `ConsultaFactuSistemaFacturacion` |
| `RespuestaConsultaLR.xsd` | Query response: `RespuestaConsultaFactuSistemaFacturacion` (up to 10,000 records) |
| `EventosSIF.xsd` | Events log: `RegistroEvento` (SIF system events with hash chain) |
| `RespuestaValRegistNoVeriFactu.xsd` | Validation response for non-VeriFactu mode |

**VeriFactu namespace root:** `https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/`

Each schema appends its own filename to form its targetNamespace. For example:
- `SuministroInformacion.xsd` namespace: `…/SuministroInformacion.xsd`
- `SuministroLR.xsd` namespace: `…/SuministroLR.xsd`

## SII WSDL schema inventory

| File | Service |
|---|---|
| `ConsultaLLAA.wsdl` | Query issued invoices (consulta) |
| `ConsultaLR.xsd` | Query request schema |
| `RespuestaConsultaLR.xsd` | Query response schema |
| `SuministroInformacion.xsd` | Core suministro data schema |
| `SuministroFactEmitidas.wsdl` | Submit issued invoices |
| `SuministroFactRecibidas.wsdl` | Submit received invoices |
| `SuministroCobrosEmitidas.wsdl` | Submit collections on issued invoices |
| `SuministroPagosRecibidas.wsdl` | Submit payments on received invoices |
| `SuministroBienesInversion.wsdl` | Submit investment goods |
| `SuministroInmueblesAdicionales.wsdl` | Submit additional real estate |
| `SuministroOpIntracomunitarias.wsdl` | Submit intra-community operations |
| `SuministroOpTrascendTribu.wsdl` | Submit tax-relevant operations |
| `SuministroVentaBienesConsigna.wsdl` | Submit consignment sales |

## FACe documentation inventory

| File | Content |
|---|---|
| `FACe-manual-api-proveedores.pdf` | REST API for invoice suppliers |
| `FACe-manual-api-integradores.pdf` | REST API for platform integrators |
| `FACe-manual-api-organismos.pdf` | REST API for contracting bodies |
| `FACe-manual-soap-directorio.pdf` | SOAP directory service |
| `FACe-manual-soap-proveedores.pdf` | SOAP service for suppliers |
| `FACe-manual-soap-organismos-facturas.pdf` | SOAP service for contracting bodies (invoices) |
| `FACe-manual-soap-organismos-notificacion.pdf` | SOAP service for contracting bodies (notifications) |
| `FACe-manual-soap-proveedores-cesion.pdf` | SOAP service for invoice assignment |

## Excluded from this directory

- `FACE - Manual Cliente FACTURAe.pdf` — end-user client guide; not relevant to API integration
- `FACe Manual de Integradores.pdf` — older general guide; superseded by the API-specific version
- `FACe Manual de Proveedores.pdf` — older general guide; superseded by the API-specific version
- `GUIA INFORMATIVA Y FAQS FACE.pdf` — FAQ guide; not a technical specification
- TicketBAI assets — out of scope for this package
