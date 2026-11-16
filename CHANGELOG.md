# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
