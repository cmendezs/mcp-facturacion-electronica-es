# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.11.0] - 2026-11-21

### Fixed
- `es__validate_verifactu_record` and `es__validate_facturae_schema` now run full XSD validation. Both schemas import the W3C XML-DSig schema by a URL that does not resolve offline, so schema compilation failed and every call silently fell back to structural checks. The W3C schema is bundled under `resources/xmldsig/` and resolved locally. Reported `validation_mode` is now `xsd`.
- Full validation exposed generator output that the schemas reject; all of it is corrected:
  - Factura-e: children were wrongly placed in the schema namespace (the schema leaves children unqualified), `InvoiceIssuerType` defaulted to the invalid value `EU` (valid values are `EM`, `RE` and `TE`; `EU` is still accepted as an alias of `EM`), country codes were alpha-2 where the schema requires alpha-3 (`ESP`), and overseas addresses used `PostCode` and `Town` instead of `PostCodeAndTown` and `Province`. A non-Spanish alpha-2 country code now raises an error asking for the alpha-3 code.
  - VeriFactu: `Cabecera` was in the wrong namespace and `NombreRazonSocial` should be `NombreRazon`. `DesgloseIVA` and `DetalleIVA` should be `DetalleDesglose` under `Desglose`, and `BaseImponibleOImporteNoSujeto` should be `BaseImponibleOimporteNoSujeto`. `RegistroAnulacion` had a `NombreRazonEmisor` element it does not allow. Chained records emitted `PrimerRegistro` with the value `N`, which the schema rejects; a chained record now carries `RegistroAnterior` only.
- `SistemaInformatico/Version` in generated `RegistroAlta` records now carries the package version instead of the hardcoded literal `0.1.0`.
- `es__detect_regional_regime` and `es__check_b2b_mandate_applicability` descriptions no longer claim to return `TICKETBAI` or `NATICKET`. Both return `VERIFACTU` or `VERIFACTU+SII`, and flag the foral provinces (Araba, Gipuzkoa, Bizkaia, Navarre) through `out_of_scope_warning`.
- README and README.es no longer document the TicketBAI tools and `TICKETBAI_*` environment variables removed in v0.2.0.

### Changed
- The UBL generator behind `es__generate_b2b_einvoice_es` is reworked for the AEAT public solution and validates against the OASIS UBL 2.5 `UBL-Invoice-2.5.xsd`. It emits the Annex I identifiers (BT-24 `urn:cen.eu:en16931:2026#conformant#urn:aeat.es:spfe:1.0.0:extended`, BT-23 `urn:aeat:names:specification:schema:profile:B2B`) in place of the Peppol BIS values, identifies Spanish parties by NIF (`LOC` scheme with `schemeID="FC"`) and other parties by NIF-IVA, and always writes the postal address (BR-ES-8 and BR-ES-10). The previous output placed `EndpointID` in the wrong namespace, wrote `Note` after the currency code, and omitted the address.
- The AEAT Schematron rules for EN 16931:2026 are not published; the generator does not run them and the tool disclaimer says so.

### Added
- `es__generate_b2b_einvoice_es` takes `is_copy` (Annex I BT-ES-1, `cbc:CopyIndicator`).
- Regression tests: generated Factura-e, VeriFactu records (first, chained and cancellation) and UBL validate against their schemas, schema violations surface as `[XSD]` errors, and `SistemaInformatico/Version` stays bound to the package version.

---

## [Unreleased]

### Changed
- `es__check_b2b_mandate_applicability` now reports concrete Crea y Crece application dates. Orden HAC/1028/2026 (BOE-A-2026-20587, published 2026-10-05) entered into force on 2026-10-06, so the 12-month date (taxpayers above 8 million euros of turnover, and platform-operator obligations) is 2027-10-06 and the 24-month date (all other taxpayers) is 2028-10-06. New fields: `om_reference`, `om_publication_date`, `om_entry_into_force_date`, `this_taxpayer_application_date`, `over_8m_application_date`, `other_taxpayers_application_date`, `platform_operator_application_date`, `b2b_public_solution_order`, `b2b_aeat_technical_specs_pending`. The calendar-month counting is an inference; the supplied texts do not state whether the obligation applies on that day or the day after.
- B2B tool descriptions and notes now cite the order: EN 16931 in UBL for the public solution, unique code (issuer NIF + series/number + issue date), no embedded files, and the copy indicator (BT-ES-1) on faithful copies. The UBL structure of the public solution still depends on the AEAT electronic-office specifications, which are not bundled, so the UBL generator is unchanged.
- The order text is added to the reference specifications.

---

## [0.10.1] - 2026-09-12

### Changed
- Lower-bound pin on `mcp-einvoicing-core` raised to `>=1.34.1` (was `>=1.32.0`). This package's own CI now runs `CHECK_PUBLIC_HYGIENE`, the pre-publish audit check that blocks accidental citations of the private orchestration repo.

---

## [0.8.0] - 2026-08-22

### Added
- Initial changelog. Prior release history is recorded in the Git tags and
  GitHub Releases for this repository.
