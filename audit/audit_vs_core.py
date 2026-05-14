"""Pre-publish audit: verify mcp-facturacion-electronica-es coherence against mcp-einvoicing-core.

Run standalone:
    python audit/audit_vs_core.py
    python audit/audit_vs_core.py --output audit/report.json
    python audit/audit_vs_core.py --fail-on blocking   # exits 2 on blocking failures
    python audit/audit_vs_core.py --fail-on warnings   # exits 1 on warnings, 2 on blocking

Exit codes:
    0  All checks passed
    1  Warnings only (non-blocking)
    2  Blocking failures found

This script is designed to be importable with no side effects; all execution
is guarded by `if __name__ == "__main__"`.

CHECK 1 and CHECK 4 are delegated to mcp_einvoicing_core.audit.
CHECK 2 (tool registry), CHECK 3 (SpanishInvoice field alignment), and CHECK 5
(ES-specific structural) are implemented here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from mcp_einvoicing_core.audit import (
    SEVERITY_BLOCKING,
    SEVERITY_OK,
    SEVERITY_WARNING,
    AuditReport,
    CheckFinding,
    CheckResult,
    _try_import,
    make_report,
    parse_audit_args,
    render_summary_table,
    run_check_core_coverage,
    run_check_version_compatibility,
)

# ---------------------------------------------------------------------------
# CHECK 1 configuration — country-specific constants
# ---------------------------------------------------------------------------

# Factura-e 3.2.2 is a CIUS of EN 16931. SpanishInvoice likely extends
# EN16931Invoice but this is unverified pending a full model-tree audit.
# Set to None to skip the canonical tree check until verified.
# [Inference: is_en16931_family=True once SpanishInvoice model is confirmed]
_IS_EN16931_FAMILY: bool | None = None
_PRIMARY_INVOICE_CLASS: tuple[str, str] | None = None

_INTENTIONAL_OVERRIDES: dict[str, set[str]] = {
    # ES uses standalone FastMCP; ABC base classes are not subclassed directly.
    "mcp_einvoicing_core.base_server": {
        "BaseDocumentGenerator",
        "BaseDocumentParser",
        "BaseDocumentValidator",
        "BasePartyValidator",
        "EInvoicingMCPServer",
        "BaseLifecycleManager",
        "SubmitResult",
    },
    # SchematronValidator: ES uses XSD + business-rule validation, not Schematron.
    "mcp_einvoicing_core.schematron": {
        "BaseStructuredValidator",
        "SchematronValidator",
        "ValidationMessage",
        "ValidationResult",
    },
    # PDF/A-3 embedding is not required for Facturae or TicketBAI.
    "mcp_einvoicing_core.pdf": {
        "PDFEmbedder",
    },
    # KSeF artefacts framework: not applicable to ES.
    "mcp_einvoicing_core.download_rules": {
        "DownloadSpec",
        "download_artefacts",
    },
    # TokenCache: ES uses per-call OAuth2 or mTLS; session token caching not needed.
    "mcp_einvoicing_core.http_client": {
        "TokenCache",
    },
    # PartyValidationError / SchematronValidationError: not raised by ES tools.
    "mcp_einvoicing_core.exceptions": {
        "PartyValidationError",
        "SchematronValidationError",
    },
}

_ES_MODULES: list[str] = [
    "mcp_facturacion_electronica_es",
    "mcp_facturacion_electronica_es.models.es",
    "mcp_facturacion_electronica_es.tools.verifactu",
    "mcp_facturacion_electronica_es.tools.facturae",
    "mcp_facturacion_electronica_es.tools.sii",
    "mcp_facturacion_electronica_es.tools.ticketbai",
    "mcp_facturacion_electronica_es.tools.b2b",
    "mcp_facturacion_electronica_es.tools.utils",
]

_PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


# ---------------------------------------------------------------------------
# CHECK 2 — Tool registry completeness
# ---------------------------------------------------------------------------

_REQUIRED_TOOL_CATEGORIES: dict[str, str] = {
    # VERI*FACTU
    "es__generate_verifactu_record":       "Generar registro VERI*FACTU con Huella SHA-256",
    "es__validate_verifactu_record":       "Validar registro VERI*FACTU contra XSD HAC/1177/2024",
    "es__submit_verifactu_to_aeat":        "Enviar registro VERI*FACTU firmado a AEAT (MTLS)",
    "es__generate_qr_verifactu":           "Generar QR obligatorio VERI*FACTU (Art. 10 HAC/1177/2024)",
    "es__cancel_verifactu_record":         "Generar registro de anulación VERI*FACTU",
    # Facturae / FACe
    "es__generate_facturae_xml":           "Generar XML Facturae 3.2.2 para envío B2G",
    "es__sign_facturae_xades":             "Aplicar firma XAdES-EPES a documento Facturae XML",
    "es__submit_to_face":                  "Enviar Facturae firmado a FACe via REST API v2",
    "es__get_face_invoice_status":         "Consultar estado de factura en FACe",
    "es__validate_facturae_schema":        "Validar XML Facturae contra XSD oficial 3.2.2",
    # SII
    "es__build_sii_invoice_record":        "Construir registro XML AEAT SII (FacturaExpedida/Recibida)",
    "es__submit_sii_batch":                "Enviar lote de facturas SII al endpoint SOAP AEAT",
    "es__query_sii_status":                "Consultar estado de lote SII enviado",
    "es__generate_sii_correction":         "Generar registro de modificación (A1) o baja (A4) SII",
    # TicketBAI
    "es__generate_ticketbai_xml":          "Generar XML TicketBAI con firma XAdES y HuellaTBAI",
    "es__submit_ticketbai":                "Enviar registro TicketBAI a la autoridad provincial vasca",
    "es__validate_ticketbai_schema":       "Validar XML TicketBAI contra XSD provincial correcto",
    # Crea y Crece / B2B
    "es__generate_b2b_einvoice_es":        "Generar factura B2B EN 16931 (UBL 2.1 o Facturae 3.2.2)",
    "es__check_b2b_mandate_applicability": "Determinar régimen aplicable según RD 254/2025",
    # Utilities
    "es__detect_regional_regime":          "Detectar régimen de facturación por código de provincia INE",
    "es__get_compliance_status":           "Obtener plazos de mandato vigentes para perfil de empresa",
    "es__parse_aeat_response":             "Analizar y normalizar respuesta XML AEAT a JSON estructurado",
}

_TOOL_MODULE_ATTRS: list[tuple[str, str]] = [
    ("mcp_facturacion_electronica_es.tools.verifactu", "TOOL_ES_GENERATE_VERIFACTU_RECORD"),
    ("mcp_facturacion_electronica_es.tools.verifactu", "TOOL_ES_VALIDATE_VERIFACTU_RECORD"),
    ("mcp_facturacion_electronica_es.tools.verifactu", "TOOL_ES_SUBMIT_VERIFACTU_TO_AEAT"),
    ("mcp_facturacion_electronica_es.tools.verifactu", "TOOL_ES_GENERATE_QR_VERIFACTU"),
    ("mcp_facturacion_electronica_es.tools.verifactu", "TOOL_ES_CANCEL_VERIFACTU_RECORD"),
    ("mcp_facturacion_electronica_es.tools.facturae",  "TOOL_ES_GENERATE_FACTURAE_XML"),
    ("mcp_facturacion_electronica_es.tools.facturae",  "TOOL_ES_SIGN_FACTURAE_XADES"),
    ("mcp_facturacion_electronica_es.tools.facturae",  "TOOL_ES_SUBMIT_TO_FACE"),
    ("mcp_facturacion_electronica_es.tools.facturae",  "TOOL_ES_GET_FACE_INVOICE_STATUS"),
    ("mcp_facturacion_electronica_es.tools.facturae",  "TOOL_ES_VALIDATE_FACTURAE_SCHEMA"),
    ("mcp_facturacion_electronica_es.tools.sii",       "TOOL_ES_BUILD_SII_INVOICE_RECORD"),
    ("mcp_facturacion_electronica_es.tools.sii",       "TOOL_ES_SUBMIT_SII_BATCH"),
    ("mcp_facturacion_electronica_es.tools.sii",       "TOOL_ES_QUERY_SII_STATUS"),
    ("mcp_facturacion_electronica_es.tools.sii",       "TOOL_ES_GENERATE_SII_CORRECTION"),
    ("mcp_facturacion_electronica_es.tools.ticketbai", "TOOL_ES_GENERATE_TICKETBAI_XML"),
    ("mcp_facturacion_electronica_es.tools.ticketbai", "TOOL_ES_SUBMIT_TICKETBAI"),
    ("mcp_facturacion_electronica_es.tools.ticketbai", "TOOL_ES_VALIDATE_TICKETBAI_SCHEMA"),
    ("mcp_facturacion_electronica_es.tools.b2b",       "TOOL_ES_GENERATE_B2B_EINVOICE_ES"),
    ("mcp_facturacion_electronica_es.tools.b2b",       "TOOL_ES_CHECK_B2B_MANDATE_APPLICABILITY"),
    ("mcp_facturacion_electronica_es.tools.utils",     "TOOL_ES_DETECT_REGIONAL_REGIME"),
    ("mcp_facturacion_electronica_es.tools.utils",     "TOOL_ES_GET_COMPLIANCE_STATUS"),
    ("mcp_facturacion_electronica_es.tools.utils",     "TOOL_ES_PARSE_AEAT_RESPONSE"),
]


def _collect_registered_tools() -> set[str]:
    registered: set[str] = set()
    for mod_path, attr in _TOOL_MODULE_ATTRS:
        mod, _ = _try_import(mod_path)
        if mod and hasattr(mod, attr):
            tool_obj = getattr(mod, attr)
            if hasattr(tool_obj, "name"):
                registered.add(tool_obj.name)
    return registered


def run_check_2() -> CheckResult:
    """CHECK 2 — Tool registry completeness."""
    result = CheckResult(check_id="CHECK_2", name="Tool registry completeness")
    registered = _collect_registered_tools()

    for tool_name, description in _REQUIRED_TOOL_CATEGORIES.items():
        tag = "[OK]" if tool_name in registered else "[MISSING_TOOL]"
        sev = SEVERITY_OK if tool_name in registered else SEVERITY_BLOCKING
        result.findings.append(CheckFinding(
            check_id="CHECK_2", tag=tag, severity=sev,
            symbol=tool_name,
            message=(
                f"Tool '{tool_name}' is registered. ({description})"
                if tool_name in registered
                else (
                    f"Required tool '{tool_name}' ({description}) is not registered "
                    "in the MCP server. Add it to server.py _ALL_TOOLS and _TOOL_HANDLERS."
                )
            ),
        ))

    for tool_name in sorted(registered - set(_REQUIRED_TOOL_CATEGORIES)):
        result.findings.append(CheckFinding(
            check_id="CHECK_2", tag="[EXTRA]", severity=SEVERITY_OK,
            symbol=tool_name,
            message=f"Tool '{tool_name}' is registered but not in the required tool spec.",
        ))

    return result


# ---------------------------------------------------------------------------
# CHECK 3 — Model field alignment (SpanishInvoice)
# ---------------------------------------------------------------------------

# EN 16931 field names that SpanishInvoice must expose (as Pydantic fields or
# mapped properties). Descriptions are in Spanish for locale consistency.
_CORE_MANDATORY_FIELDS: dict[str, str] = {
    "invoice_number":       "BT-1  — Número de factura",
    "invoice_date":         "BT-2  — Fecha de expedición",
    "invoice_type_code":    "BT-3  — Tipo de factura (F1, F2, R1…)",
    "currency_code":        "BT-5  — Moneda (EUR)",
    "seller":               "BG-4  — Emisor / Vendedor",
    "buyer":                "BG-7  — Receptor / Comprador",
    "tax_lines":            "BG-23 — Desglose de IVA",
    "tax_exclusive_amount": "BT-109 — Base imponible total",
    "tax_inclusive_amount": "BT-112 — Total con IVA",
    "tax_total":            "BT-110 — Cuota total de IVA",
    "amount_due":           "BT-115 — Importe a pagar",
}

_DEPRECATED_CORE_FIELDS: set[str] = set()


def run_check_3() -> CheckResult:
    """CHECK 3 — Model field alignment (SpanishInvoice)."""
    result = CheckResult(check_id="CHECK_3", name="Model field alignment")

    mod, err = _try_import("mcp_facturacion_electronica_es.models.es")
    if mod is None:
        result.skipped = True
        result.skip_reason = f"Could not import ES models: {err}"
        return result

    invoice_cls = getattr(mod, "SpanishInvoice", None)
    if invoice_cls is None:
        result.findings.append(CheckFinding(
            check_id="CHECK_3", tag="[MISSING]", severity=SEVERITY_BLOCKING,
            symbol="SpanishInvoice",
            message="SpanishInvoice class not found in mcp_facturacion_electronica_es.models.es.",
        ))
        return result

    # SpanishInvoice may expose EN 16931 names as properties mapping to internal fields.
    model_fields = set(invoice_cls.model_fields.keys())

    def _has_field(cls: type, name: str) -> bool:
        if name in model_fields:
            return True
        return isinstance(getattr(cls, name, None), property) or hasattr(cls, name)

    for field_name, description in _CORE_MANDATORY_FIELDS.items():
        ok = _has_field(invoice_cls, field_name)
        result.findings.append(CheckFinding(
            check_id="CHECK_3",
            tag="[OK]" if ok else "[FIELD_MISSING]",
            severity=SEVERITY_OK if ok else SEVERITY_BLOCKING,
            symbol=f"SpanishInvoice.{field_name}",
            message=(
                f"Mandatory field present (field or property). {description}"
                if ok
                else f"Mandatory field '{field_name}' ({description}) is absent from SpanishInvoice."
            ),
        ))

    for dep_field in _DEPRECATED_CORE_FIELDS:
        if dep_field in model_fields:
            result.findings.append(CheckFinding(
                check_id="CHECK_3", tag="[DEPRECATED_IN_USE]", severity=SEVERITY_WARNING,
                symbol=f"SpanishInvoice.{dep_field}",
                message=(
                    f"Field '{dep_field}' is marked deprecated in mcp-einvoicing-core "
                    "but is still present in SpanishInvoice."
                ),
            ))

    return result


# ---------------------------------------------------------------------------
# CHECK 5 — ES-specific structural checks
# ---------------------------------------------------------------------------

def run_check_5() -> CheckResult:
    """CHECK 5 — ES-specific structural and completeness checks."""
    result = CheckResult(check_id="CHECK_5", name="ES-specific structural checks")

    # 5a: server module exports _ALL_TOOLS, _TOOL_HANDLERS, and main
    server_mod, err = _try_import("mcp_facturacion_electronica_es.server")
    if server_mod is None:
        result.findings.append(CheckFinding(
            check_id="CHECK_5", tag="[MISSING]", severity=SEVERITY_BLOCKING,
            symbol="mcp_facturacion_electronica_es.server",
            message=f"Could not import server module: {err}",
        ))
    else:
        for attr in ("_ALL_TOOLS", "_TOOL_HANDLERS", "main"):
            tag = "[OK]" if hasattr(server_mod, attr) else "[MISSING]"
            sev = SEVERITY_OK if hasattr(server_mod, attr) else SEVERITY_BLOCKING
            result.findings.append(CheckFinding(
                check_id="CHECK_5", tag=tag, severity=sev,
                symbol=f"server.{attr}",
                message=(
                    f"server.{attr} is present."
                    if hasattr(server_mod, attr)
                    else f"server.{attr} is missing — required for MCP server operation."
                ),
            ))

        # 5b: _ALL_TOOLS and _TOOL_HANDLERS in sync
        all_tools = getattr(server_mod, "_ALL_TOOLS", [])
        all_handlers = getattr(server_mod, "_TOOL_HANDLERS", {})
        tool_names_list = {t.name for t in all_tools}
        tool_names_handlers = set(all_handlers.keys())

        for name in sorted(tool_names_list - tool_names_handlers):
            result.findings.append(CheckFinding(
                check_id="CHECK_5", tag="[MISSING_HANDLER]", severity=SEVERITY_BLOCKING,
                symbol=f"_TOOL_HANDLERS[{name!r}]",
                message=f"Tool '{name}' is in _ALL_TOOLS but has no handler in _TOOL_HANDLERS.",
            ))
        for name in sorted(tool_names_handlers - tool_names_list):
            result.findings.append(CheckFinding(
                check_id="CHECK_5", tag="[MISSING_REGISTRATION]", severity=SEVERITY_WARNING,
                symbol=f"_ALL_TOOLS[{name!r}]",
                message=f"Handler '{name}' is in _TOOL_HANDLERS but not listed in _ALL_TOOLS.",
            ))
        if not (tool_names_list - tool_names_handlers) and not (tool_names_handlers - tool_names_list):
            result.findings.append(CheckFinding(
                check_id="CHECK_5", tag="[OK]", severity=SEVERITY_OK,
                symbol="_ALL_TOOLS ↔ _TOOL_HANDLERS",
                message=f"All {len(all_tools)} tools have matching handlers.",
            ))

    # 5c: SpanishRegime enum covers required values
    models_mod, _ = _try_import("mcp_facturacion_electronica_es.models.es")
    if models_mod:
        regime_cls = getattr(models_mod, "SpanishRegime", None)
        if regime_cls:
            required_regimes = {"VERIFACTU", "TICKETBAI", "NATICKET", "VERIFACTU_SII"}
            actual_regimes = {r.name for r in regime_cls}
            for r in sorted(required_regimes):
                tag = "[OK]" if r in actual_regimes else "[MISSING_REGIME]"
                sev = SEVERITY_OK if r in actual_regimes else SEVERITY_BLOCKING
                result.findings.append(CheckFinding(
                    check_id="CHECK_5", tag=tag, severity=sev,
                    symbol=f"SpanishRegime.{r}",
                    message=(
                        "Regime value defined."
                        if r in actual_regimes
                        else f"Required regime '{r}' is not defined in SpanishRegime enum."
                    ),
                ))
        else:
            result.findings.append(CheckFinding(
                check_id="CHECK_5", tag="[MISSING]", severity=SEVERITY_BLOCKING,
                symbol="SpanishRegime",
                message="SpanishRegime enum not found in mcp_facturacion_electronica_es.models.es.",
            ))

        # 5d: TicketBAIProvince covers three Basque provinces
        province_cls = getattr(models_mod, "TicketBAIProvince", None)
        if province_cls:
            required_provinces = {"araba", "gipuzkoa", "bizkaia"}
            actual_provinces = {p.value for p in province_cls}
            for p in sorted(required_provinces):
                tag = "[OK]" if p in actual_provinces else "[MISSING_PROVINCE]"
                sev = SEVERITY_OK if p in actual_provinces else SEVERITY_BLOCKING
                result.findings.append(CheckFinding(
                    check_id="CHECK_5", tag=tag, severity=sev,
                    symbol=f"TicketBAIProvince.{p}",
                    message=(
                        "Province value defined."
                        if p in actual_provinces
                        else f"Required TicketBAI province '{p}' missing from TicketBAIProvince."
                    ),
                ))
        else:
            result.findings.append(CheckFinding(
                check_id="CHECK_5", tag="[MISSING]", severity=SEVERITY_BLOCKING,
                symbol="TicketBAIProvince",
                message="TicketBAIProvince enum not found in mcp_facturacion_electronica_es.models.es.",
            ))

        # 5e: VerifactuInvoiceType covers required type codes
        invoice_type_cls = getattr(models_mod, "VerifactuInvoiceType", None)
        if invoice_type_cls:
            required_types = {"F1", "F2", "F3", "R1", "R2", "R3", "R4", "R5"}
            actual_types = {t.value for t in invoice_type_cls}
            missing_types = required_types - actual_types
            if missing_types:
                for t in sorted(missing_types):
                    result.findings.append(CheckFinding(
                        check_id="CHECK_5", tag="[MISSING_TYPE]", severity=SEVERITY_BLOCKING,
                        symbol=f"VerifactuInvoiceType.{t}",
                        message=f"Required VERI*FACTU invoice type '{t}' is not defined.",
                    ))
            else:
                result.findings.append(CheckFinding(
                    check_id="CHECK_5", tag="[OK]", severity=SEVERITY_OK,
                    symbol="VerifactuInvoiceType",
                    message=f"All {len(required_types)} required invoice type codes defined.",
                ))

    # 5f: specs/ directory for normative XSD files
    specs_dir = Path(__file__).parent.parent / "specs"
    if specs_dir.exists():
        spec_files = [f for f in specs_dir.iterdir() if not f.name.startswith(".")]
        result.findings.append(CheckFinding(
            check_id="CHECK_5", tag="[OK]", severity=SEVERITY_OK,
            symbol="specs/",
            message=f"specs/ directory found with {len(spec_files)} reference file(s).",
        ))
    else:
        result.findings.append(CheckFinding(
            check_id="CHECK_5", tag="[MISSING_SPECS]", severity=SEVERITY_WARNING,
            symbol="specs/",
            message=(
                "specs/ directory not found. Drop official XSD files "
                "(HAC/1177/2024, Facturae 3.2.2, TicketBAI provincial) into specs/ "
                "to enable schema-based validation."
            ),
        ))

    return result


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def run_audit() -> AuditReport:
    """Execute all checks and return the aggregated AuditReport. No side effects."""
    report = make_report("mcp-facturacion-electronica-es", _PYPROJECT)

    report.checks.append(run_check_core_coverage(
        package_name="mcp-facturacion-electronica-es",
        package_modules=_ES_MODULES,
        intentional_overrides=_INTENTIONAL_OVERRIDES,
        is_en16931_family=_IS_EN16931_FAMILY,
        primary_invoice_class=_PRIMARY_INVOICE_CLASS,
    ))
    report.checks.append(run_check_2())
    report.checks.append(run_check_3())
    report.checks.append(run_check_version_compatibility(
        package_name="mcp-facturacion-electronica-es",
        pyproject_path=_PYPROJECT,
    ))
    report.checks.append(run_check_5())

    return report


def main(argv: list[str] | None = None) -> int:
    args = parse_audit_args(
        "Pre-publish audit: mcp-facturacion-electronica-es vs mcp-einvoicing-core", argv
    )
    report = run_audit()

    output_path = Path(args.output) if args.output else Path("audit/report.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    if not args.quiet:
        print(render_summary_table(report))
        print(f"\nJSON report written to: {output_path}")

    if args.fail_on == "never":
        return 0
    if args.fail_on == "warnings":
        return min(report.exit_code, 2)
    return 2 if report.total_blocking > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
