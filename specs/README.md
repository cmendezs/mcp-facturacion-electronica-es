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
│   ├── documentation/          BOE legal text + official AEAT technical notes (huella, QR, web service)
│   ├── schemas/                Official WSDL (SistemaFacturacion.wsdl)
│   ├── xsd/                    Official XSD schemas (SuministroInformacion, SuministroLR, etc.)
│   └── examples/               Official signed RegistroAlta examples (AnexosEjemplosFirmaRegFact.zip)
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
| VeriFactu huella spec (`Veri-Factu_especificaciones_huella_hash_registros.pdf`) | v0.1.2, 27/08/2024 | AEAT (Sede Electrónica), user-supplied 2026-08-09 |
| VeriFactu QR code spec (`DetalleEspecificacTecnCodigoQRfactura.pdf`) | v0.5.0, 10/12/2025 | AEAT (Sede Electrónica), user-supplied 2026-08-09 |
| VeriFactu web service description (`Veri-Factu_Descripcion_SWeb.pdf`) | v1.0.3, 28/07/2025 | AEAT (Sede Electrónica), user-supplied 2026-08-09 |
| VeriFactu WSDL (`SistemaFacturacion.wsdl`) | — | AEAT, user-supplied 2026-08-09; soap:address entries are the authoritative source for `_helpers.VERIFACTU_ENDPOINTS` / `VERIFACTU_SELLO_ENDPOINTS` |
| VeriFactu validation/error catalog (`Validaciones_Errores_Veri-Factu.pdf`, `errores.properties`) | — | AEAT, user-supplied 2026-08-09; reference only, not yet wired into a local error-code table |
| VeriFactu XSD bundle (7 files, `verifactu/xsd/`) | — | AEAT; byte-identical to the 2026-06-26 bundle already present, reconfirmed against the user-supplied 2026-08-09 copies |
| VeriFactu signed RegistroAlta examples (`AnexosEjemplosFirmaRegFact.zip`) | — | AEAT, user-supplied 2026-08-09; not yet used by tests |
| VeriFactu "declaración responsable" examples (`EjemplosDeclaracionResponsable(V0.5.1).pdf`), `DsRegistroVeriFactu.xlsx` | v0.5.1 | AEAT, user-supplied 2026-08-09; SIF-certification reference material, not used by this package's tools |
| ~~VeriFactu technical reference (huella, QR, WSDL ops)~~ | `[Inference]`, 2026-08 | **Superseded 2026-08-09** by the official documents above. User-supplied transcription in `verifactu/documentation/verifactu-technical-reference.md`; two of its claims (RegistroAnulacion field names, WSDL operation names) turned out wrong when checked against the primary source — see the inline callouts in that file and ES-SC-10/11/ES-LC-8/9/10 in `context-library/audit-history.md`. |
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

## VeriFactu WSDL (`verifactu/schemas/SistemaFacturacion.wsdl`)

Two services, four ports each (production/sandbox × personal-certificate/Sello-certificate).
`www10`/`prewww10` are **not** a failover secondary for `www1`/`prewww1` — they are the
Sello (company seal) certificate variant of the same operation, confirmed directly from
the WSDL's own port names (`SistemaVerifactuSello`, `SistemaVerifactuSelloPruebas`).

| Service | Binding | Operations | Port (URL host) |
|---|---|---|---|
| `sfVerifactu` | `sfVerifactu` | `RegFactuSistemaFacturacion` (alta + anulación, by XML root element), `ConsultaFactuSistemaFacturacion` | `www1`/`www10`.agenciatributaria.gob.es (prod), `prewww1`/`prewww10`.aeat.es (sandbox) — path `/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP` |
| `sfRequerimiento` | `sfRequerimiento` | `RegFactuSistemaFacturacion` (response to an AEAT-initiated requerimiento) | same hosts, path `/wlpl/TIKE-CONT/ws/SistemaFacturacion/RequerimientoSOAP` — not implemented by this package (voluntary remisión only) |

`RegFactuSistemaFacturacion` and `ConsultaFactuSistemaFacturacion` share one endpoint —
see `_helpers.VERIFACTU_ENDPOINTS` / `VERIFACTU_CONSULTA_ENDPOINTS` (now the same value)
and `VERIFACTU_SELLO_ENDPOINTS`. The QR verification service (`ValidarQR`, section above)
is a separate REST-style endpoint on a third host pair (`www2`/`prewww2`) — see
`VERIFACTU_QR_ENDPOINTS`.

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
