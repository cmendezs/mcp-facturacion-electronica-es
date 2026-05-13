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

[NEED: update CHECK 1 once mcp-einvoicing-core public API is finalised]
[NEED: update CHECK 5 once mcp-einvoicing-core tool category registry is defined]
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import inspect
import json
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

SEVERITY_BLOCKING = "BLOCKING"
SEVERITY_WARNING = "WARNING"
SEVERITY_OK = "OK"
SEVERITY_SKIP = "SKIP"


@dataclass
class CheckFinding:
    check_id: str
    tag: str           # e.g. [MISSING], [OVERRIDE], [OK], [SKIP]
    severity: str      # SEVERITY_* constants
    symbol: str        # What was checked (class name, field name, etc.)
    message: str


@dataclass
class CheckResult:
    check_id: str
    name: str
    findings: list[CheckFinding] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""

    @property
    def blocking_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SEVERITY_BLOCKING)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SEVERITY_WARNING)

    @property
    def passed(self) -> bool:
        return self.blocking_count == 0


@dataclass
class AuditReport:
    generated_at: str
    es_version: str
    core_version: str | None
    core_version_compatible: bool
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def total_blocking(self) -> int:
        return sum(c.blocking_count for c in self.checks)

    @property
    def total_warnings(self) -> int:
        return sum(c.warning_count for c in self.checks)

    @property
    def exit_code(self) -> int:
        if self.total_blocking > 0:
            return 2
        if self.total_warnings > 0:
            return 1
        return 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "es_version": self.es_version,
            "core_version": self.core_version,
            "core_version_compatible": self.core_version_compatible,
            "exit_code": self.exit_code,
            "total_blocking": self.total_blocking,
            "total_warnings": self.total_warnings,
            "checks": [
                {
                    "check_id": c.check_id,
                    "name": c.name,
                    "passed": c.passed,
                    "skipped": c.skipped,
                    "skip_reason": c.skip_reason,
                    "blocking_count": c.blocking_count,
                    "warning_count": c.warning_count,
                    "findings": [
                        {
                            "check_id": f.check_id,
                            "tag": f.tag,
                            "severity": f.severity,
                            "symbol": f.symbol,
                            "message": f.message,
                        }
                        for f in c.findings
                    ],
                }
                for c in self.checks
            ],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _try_import(module_path: str) -> tuple[Any | None, str | None]:
    """Attempt to import a module; return (module, None) or (None, error_message)."""
    try:
        return importlib.import_module(module_path), None
    except ImportError as exc:
        return None, str(exc)


def _get_public_symbols(module: Any) -> dict[str, Any]:
    """Return all public symbols from a module (respecting __all__ if defined)."""
    if hasattr(module, "__all__"):
        return {name: getattr(module, name) for name in module.__all__ if hasattr(module, name)}
    return {
        name: obj
        for name, obj in inspect.getmembers(module)
        if not name.startswith("_")
        and not inspect.ismodule(obj)
    }


def _get_installed_version(package_name: str) -> str | None:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a PEP 440 version string into a comparable tuple (major, minor, patch)."""
    parts = v.split(".")
    result = []
    for p in parts[:3]:
        try:
            result.append(int(p.split("a")[0].split("b")[0].split("rc")[0]))
        except ValueError:
            result.append(0)
    while len(result) < 3:
        result.append(0)
    return tuple(result)


def _version_in_range(version: str, spec: str) -> bool:
    """
    Naive PEP 440 specifier check for >=X,<Y ranges.
    Only handles >= and < comparators (sufficient for typical ~= and range deps).
    [NEED: replace with packaging.version for full PEP 440 compliance]
    """
    v = _parse_version(version)
    for part in spec.split(","):
        part = part.strip()
        if part.startswith(">="):
            low = _parse_version(part[2:].strip())
            if v < low:
                return False
        elif part.startswith("<"):
            high = _parse_version(part[1:].strip())
            if v >= high:
                return False
        elif part.startswith("~="):
            base = _parse_version(part[2:].strip())
            if len(base) >= 2 and (v < base or v[0] != base[0]):
                return False
    return True


# ---------------------------------------------------------------------------
# CHECK 1 — Core interface coverage
# ---------------------------------------------------------------------------

# Symbols that mcp-facturacion-electronica-es intentionally overrides rather than importing.
# Format: module_path → set of symbol names
_INTENTIONAL_OVERRIDES: dict[str, set[str]] = {
    # [NEED: populate once mcp-einvoicing-core public API is known]
    # Example: "mcp_einvoicing_core.models": {"BaseInvoice"},
}

# Known core modules to audit against.
# [NEED: replace with actual mcp-einvoicing-core module paths once published]
_CORE_MODULES_TO_CHECK: list[str] = [
    "mcp_einvoicing_core",
    "mcp_einvoicing_core.models",
    "mcp_einvoicing_core.validators",
    "mcp_einvoicing_core.tools",
]

# All ES package modules that might import core symbols
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


def _collect_es_imports() -> set[str]:
    """Collect all symbol names imported into ES modules from core."""
    imported: set[str] = set()
    for mod_path in _ES_MODULES:
        mod, _ = _try_import(mod_path)
        if mod is None:
            continue
        for name, obj in inspect.getmembers(mod):
            if not name.startswith("_"):
                obj_module = getattr(obj, "__module__", "") or ""
                if "mcp_einvoicing_core" in obj_module:
                    imported.add(name)
    return imported


def run_check_1() -> CheckResult:
    """CHECK 1 — Core interface coverage."""
    result = CheckResult(check_id="CHECK_1", name="Core interface coverage")

    core_available = _get_installed_version("mcp-einvoicing-core") is not None
    if not core_available:
        result.skipped = True
        result.skip_reason = (
            "mcp-einvoicing-core is not installed. "
            "Install it with: uv sync --all-extras"
        )
        result.findings.append(CheckFinding(
            check_id="CHECK_1",
            tag="[SKIP]",
            severity=SEVERITY_WARNING,
            symbol="mcp-einvoicing-core",
            message="Package not installed — cannot verify core interface coverage.",
        ))
        return result

    es_imports = _collect_es_imports()

    for mod_path in _CORE_MODULES_TO_CHECK:
        core_mod, err = _try_import(mod_path)
        if core_mod is None:
            result.findings.append(CheckFinding(
                check_id="CHECK_1",
                tag="[SKIP]",
                severity=SEVERITY_WARNING,
                symbol=mod_path,
                message=f"Could not import core module: {err}",
            ))
            continue

        overrides_for_mod = _INTENTIONAL_OVERRIDES.get(mod_path, set())
        symbols = _get_public_symbols(core_mod)

        for sym_name, sym_obj in symbols.items():
            if not (inspect.isclass(sym_obj) or inspect.isfunction(sym_obj)):
                continue

            if sym_name in overrides_for_mod:
                result.findings.append(CheckFinding(
                    check_id="CHECK_1",
                    tag="[OVERRIDE]",
                    severity=SEVERITY_OK,
                    symbol=f"{mod_path}.{sym_name}",
                    message="Intentionally overridden by ES package.",
                ))
            elif sym_name in es_imports:
                result.findings.append(CheckFinding(
                    check_id="CHECK_1",
                    tag="[OK]",
                    severity=SEVERITY_OK,
                    symbol=f"{mod_path}.{sym_name}",
                    message="Imported and used.",
                ))
            else:
                result.findings.append(CheckFinding(
                    check_id="CHECK_1",
                    tag="[MISSING]",
                    severity=SEVERITY_WARNING,
                    symbol=f"{mod_path}.{sym_name}",
                    message=(
                        f"Core symbol '{sym_name}' is neither imported by the ES package "
                        "nor marked as an intentional override. "
                        "Add to _INTENTIONAL_OVERRIDES if this is deliberate."
                    ),
                ))

    return result


# ---------------------------------------------------------------------------
# CHECK 2 — Tool registry completeness
# ---------------------------------------------------------------------------

# All 22 tools defined in the specification (README Fase 1)
_REQUIRED_TOOL_CATEGORIES: dict[str, str] = {
    # VERI*FACTU
    "es__generate_verifactu_record":  "Generar registro VERI*FACTU con cadena SHA-256 Huella",
    "es__validate_verifactu_record":  "Validar registro VERI*FACTU contra XSD HAC/1177/2024",
    "es__submit_verifactu_to_aeat":   "Enviar registro VERI*FACTU firmado a AEAT (MTLS)",
    "es__generate_qr_verifactu":      "Generar QR obligatorio VERI*FACTU (Art. 10 HAC/1177/2024)",
    "es__cancel_verifactu_record":    "Generar registro de anulación VERI*FACTU",
    # Facturae / FACe
    "es__generate_facturae_xml":      "Generar XML Facturae 3.2.2 para envío B2G",
    "es__sign_facturae_xades":        "Aplicar firma XAdES-EPES a documento Facturae XML",
    "es__submit_to_face":             "Enviar Facturae firmado a FACe via REST API v2",
    "es__get_face_invoice_status":    "Consultar estado de factura en FACe",
    "es__validate_facturae_schema":   "Validar XML Facturae contra XSD oficial 3.2.2",
    # SII
    "es__build_sii_invoice_record":   "Construir registro XML AEAT SII (FacturaExpedida/Recibida)",
    "es__submit_sii_batch":           "Enviar lote de facturas SII al endpoint SOAP AEAT",
    "es__query_sii_status":           "Consultar estado de lote SII enviado",
    "es__generate_sii_correction":    "Generar registro de modificación (A1) o baja (A4) SII",
    # TicketBAI
    "es__generate_ticketbai_xml":     "Generar XML TicketBAI con firma XAdES y HuellaTBAI",
    "es__submit_ticketbai":           "Enviar registro TicketBAI a la autoridad provincial vasca",
    "es__validate_ticketbai_schema":  "Validar XML TicketBAI contra XSD provincial correcto",
    # Crea y Crece / B2B
    "es__generate_b2b_einvoice_es":   "Generar factura B2B EN 16931 (UBL 2.1 o Facturae 3.2.2)",
    "es__check_b2b_mandate_applicability": "Determinar régimen aplicable según RD 254/2025",
    # Utilities
    "es__detect_regional_regime":     "Detectar régimen de facturación por código de provincia INE",
    "es__get_compliance_status":      "Obtener plazos de mandato vigentes para perfil de empresa",
    "es__parse_aeat_response":        "Analizar y normalizar respuesta XML AEAT a JSON estructurado",
}

# Tool module locations: (module_path, TOOL_CONSTANT_NAME)
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
    """Return the set of tool names registered across all ES tool modules."""
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
        if tool_name in registered:
            result.findings.append(CheckFinding(
                check_id="CHECK_2",
                tag="[OK]",
                severity=SEVERITY_OK,
                symbol=tool_name,
                message=f"Tool '{tool_name}' is registered. ({description})",
            ))
        else:
            result.findings.append(CheckFinding(
                check_id="CHECK_2",
                tag="[MISSING_TOOL]",
                severity=SEVERITY_BLOCKING,
                symbol=tool_name,
                message=(
                    f"Required tool '{tool_name}' ({description}) is not registered "
                    "in the MCP server. Add it to server.py _ALL_TOOLS and _TOOL_HANDLERS."
                ),
            ))

    extra = registered - set(_REQUIRED_TOOL_CATEGORIES)
    for tool_name in sorted(extra):
        result.findings.append(CheckFinding(
            check_id="CHECK_2",
            tag="[EXTRA]",
            severity=SEVERITY_OK,
            symbol=tool_name,
            message=f"Tool '{tool_name}' is registered but not in the required tool spec.",
        ))

    return result


# ---------------------------------------------------------------------------
# CHECK 3 — Model field alignment
# ---------------------------------------------------------------------------

# Mandatory fields for a Spanish VERI*FACTU / Facturae invoice model.
# [NEED: derive from actual mcp-einvoicing-core BaseInvoice model once available]
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
    """CHECK 3 — Model field alignment."""
    result = CheckResult(check_id="CHECK_3", name="Model field alignment")

    mod, err = _try_import("mcp_facturacion_electronica_es.models.es")
    if mod is None:
        result.skipped = True
        result.skip_reason = f"Could not import ES models: {err}"
        return result

    invoice_cls = getattr(mod, "SpanishInvoice", None)
    if invoice_cls is None:
        result.findings.append(CheckFinding(
            check_id="CHECK_3",
            tag="[MISSING]",
            severity=SEVERITY_BLOCKING,
            symbol="SpanishInvoice",
            message=(
                "SpanishInvoice class not found in mcp_facturacion_electronica_es.models.es. "
                "[NEED: implement SpanishInvoice Pydantic model]"
            ),
        ))
        return result

    # Fields may be Pydantic model_fields OR @property descriptors (inherited aliases).
    # SpanishInvoice exposes EN 16931 names as properties mapping to core field names.
    model_fields = set(invoice_cls.model_fields.keys())

    def _has_field(cls: type, name: str) -> bool:
        """True if name is a Pydantic field or a property/attribute on the class."""
        if name in model_fields:
            return True
        return isinstance(getattr(cls, name, None), property) or hasattr(cls, name)

    for field_name, description in _CORE_MANDATORY_FIELDS.items():
        if _has_field(invoice_cls, field_name):
            result.findings.append(CheckFinding(
                check_id="CHECK_3",
                tag="[OK]",
                severity=SEVERITY_OK,
                symbol=f"SpanishInvoice.{field_name}",
                message=f"Mandatory field present (field or property). {description}",
            ))
        else:
            result.findings.append(CheckFinding(
                check_id="CHECK_3",
                tag="[FIELD_MISSING]",
                severity=SEVERITY_BLOCKING,
                symbol=f"SpanishInvoice.{field_name}",
                message=(
                    f"Mandatory field '{field_name}' ({description}) "
                    "is absent from SpanishInvoice."
                ),
            ))

    for dep_field in _DEPRECATED_CORE_FIELDS:
        if dep_field in model_fields:
            result.findings.append(CheckFinding(
                check_id="CHECK_3",
                tag="[DEPRECATED_IN_USE]",
                severity=SEVERITY_WARNING,
                symbol=f"SpanishInvoice.{dep_field}",
                message=(
                    f"Field '{dep_field}' is marked deprecated in mcp-einvoicing-core "
                    "but is still present in SpanishInvoice."
                ),
            ))

    return result


# ---------------------------------------------------------------------------
# CHECK 4 — Version compatibility
# ---------------------------------------------------------------------------

def _read_core_version_spec_from_pyproject() -> str | None:
    """Extract the mcp-einvoicing-core version specifier from pyproject.toml."""
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    if not pyproject_path.exists():
        return None
    try:
        text = pyproject_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "mcp-einvoicing-core" in line:
                start = line.find("mcp-einvoicing-core")
                fragment = line[start:].strip().strip('",').strip("'")
                spec = fragment.replace("mcp-einvoicing-core", "").strip()
                return spec if spec else None
    except Exception:
        pass
    return None


def run_check_4() -> CheckResult:
    """CHECK 4 — Version compatibility."""
    result = CheckResult(check_id="CHECK_4", name="Version compatibility")

    installed_core = _get_installed_version("mcp-einvoicing-core")
    if installed_core is None:
        result.findings.append(CheckFinding(
            check_id="CHECK_4",
            tag="[SKIP]",
            severity=SEVERITY_WARNING,
            symbol="mcp-einvoicing-core",
            message="mcp-einvoicing-core is not installed — cannot check version compatibility.",
        ))
        return result

    declared_spec = _read_core_version_spec_from_pyproject()
    if declared_spec is None:
        result.findings.append(CheckFinding(
            check_id="CHECK_4",
            tag="[SKIP]",
            severity=SEVERITY_WARNING,
            symbol="pyproject.toml",
            message=(
                "Could not parse mcp-einvoicing-core version spec from pyproject.toml. "
                "[NEED: ensure pyproject.toml uses standard PEP 440 specifiers]"
            ),
        ))
        return result

    compatible = _version_in_range(installed_core, declared_spec)
    tag = "[OK]" if compatible else "[VERSION_MISMATCH]"
    severity = SEVERITY_OK if compatible else SEVERITY_BLOCKING

    result.findings.append(CheckFinding(
        check_id="CHECK_4",
        tag=tag,
        severity=severity,
        symbol="mcp-einvoicing-core",
        message=(
            f"Installed: {installed_core} | "
            f"Declared range: {declared_spec} | "
            f"Compatible: {compatible}"
        ),
    ))

    return result


# ---------------------------------------------------------------------------
# CHECK 5 — ES-specific structural checks
# [NEED: extend with additional checks once mcp-einvoicing-core interface is known]
# ---------------------------------------------------------------------------

def run_check_5() -> CheckResult:
    """CHECK 5 — ES-specific structural and completeness checks."""
    result = CheckResult(check_id="CHECK_5", name="ES-specific structural checks")

    # 5a: Verify server.py exports _ALL_TOOLS, _TOOL_HANDLERS, and main
    server_mod, err = _try_import("mcp_facturacion_electronica_es.server")
    if server_mod is None:
        result.findings.append(CheckFinding(
            check_id="CHECK_5",
            tag="[MISSING]",
            severity=SEVERITY_BLOCKING,
            symbol="mcp_facturacion_electronica_es.server",
            message=f"Could not import server module: {err}",
        ))
    else:
        for attr in ("_ALL_TOOLS", "_TOOL_HANDLERS", "main"):
            if hasattr(server_mod, attr):
                result.findings.append(CheckFinding(
                    check_id="CHECK_5",
                    tag="[OK]",
                    severity=SEVERITY_OK,
                    symbol=f"server.{attr}",
                    message=f"server.{attr} is present.",
                ))
            else:
                result.findings.append(CheckFinding(
                    check_id="CHECK_5",
                    tag="[MISSING]",
                    severity=SEVERITY_BLOCKING,
                    symbol=f"server.{attr}",
                    message=f"server.{attr} is missing — required for MCP server operation.",
                ))

        # 5b: _ALL_TOOLS and _TOOL_HANDLERS must be in sync
        all_tools = getattr(server_mod, "_ALL_TOOLS", [])
        all_handlers = getattr(server_mod, "_TOOL_HANDLERS", {})
        tool_names_from_list = {t.name for t in all_tools}
        tool_names_from_handlers = set(all_handlers.keys())

        missing_handlers = tool_names_from_list - tool_names_from_handlers
        missing_registrations = tool_names_from_handlers - tool_names_from_list

        for name in sorted(missing_handlers):
            result.findings.append(CheckFinding(
                check_id="CHECK_5",
                tag="[MISSING_HANDLER]",
                severity=SEVERITY_BLOCKING,
                symbol=f"_TOOL_HANDLERS[{name!r}]",
                message=f"Tool '{name}' is in _ALL_TOOLS but has no handler in _TOOL_HANDLERS.",
            ))
        for name in sorted(missing_registrations):
            result.findings.append(CheckFinding(
                check_id="CHECK_5",
                tag="[MISSING_REGISTRATION]",
                severity=SEVERITY_WARNING,
                symbol=f"_ALL_TOOLS[{name!r}]",
                message=f"Handler '{name}' is in _TOOL_HANDLERS but not listed in _ALL_TOOLS.",
            ))
        if not missing_handlers and not missing_registrations:
            result.findings.append(CheckFinding(
                check_id="CHECK_5",
                tag="[OK]",
                severity=SEVERITY_OK,
                symbol="_ALL_TOOLS <-> _TOOL_HANDLERS",
                message=f"All {len(all_tools)} tools have matching handlers.",
            ))

    # 5c: Verify SpanishRegime enum covers required values
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
                    check_id="CHECK_5",
                    tag=tag,
                    severity=sev,
                    symbol=f"SpanishRegime.{r}",
                    message="Regime value defined." if r in actual_regimes
                    else f"Required regime '{r}' is not defined in SpanishRegime enum.",
                ))
        else:
            result.findings.append(CheckFinding(
                check_id="CHECK_5",
                tag="[MISSING]",
                severity=SEVERITY_BLOCKING,
                symbol="SpanishRegime",
                message="SpanishRegime enum not found in mcp_facturacion_electronica_es.models.es.",
            ))

        # 5d: Verify TicketBAIProvince enum covers three Basque provinces
        province_cls = getattr(models_mod, "TicketBAIProvince", None)
        if province_cls:
            required_provinces = {"araba", "gipuzkoa", "bizkaia"}
            actual_provinces = {p.value for p in province_cls}
            for p in sorted(required_provinces):
                tag = "[OK]" if p in actual_provinces else "[MISSING_PROVINCE]"
                sev = SEVERITY_OK if p in actual_provinces else SEVERITY_BLOCKING
                result.findings.append(CheckFinding(
                    check_id="CHECK_5",
                    tag=tag,
                    severity=sev,
                    symbol=f"TicketBAIProvince.{p}",
                    message="Province value defined." if p in actual_provinces
                    else f"Required TicketBAI province '{p}' missing from TicketBAIProvince.",
                ))
        else:
            result.findings.append(CheckFinding(
                check_id="CHECK_5",
                tag="[MISSING]",
                severity=SEVERITY_BLOCKING,
                symbol="TicketBAIProvince",
                message=(
                    "TicketBAIProvince enum not found in mcp_facturacion_electronica_es.models.es. "
                    "[NEED: define TicketBAIProvince with araba, gipuzkoa, bizkaia]"
                ),
            ))

        # 5e: Verify VerifactuInvoiceType covers required type codes
        invoice_type_cls = getattr(models_mod, "VerifactuInvoiceType", None)
        if invoice_type_cls:
            required_types = {"F1", "F2", "F3", "R1", "R2", "R3", "R4", "R5"}
            actual_types = {t.value for t in invoice_type_cls}
            missing_types = required_types - actual_types
            if missing_types:
                for t in sorted(missing_types):
                    result.findings.append(CheckFinding(
                        check_id="CHECK_5",
                        tag="[MISSING_TYPE]",
                        severity=SEVERITY_BLOCKING,
                        symbol=f"VerifactuInvoiceType.{t}",
                        message=f"Required VERI*FACTU invoice type '{t}' is not defined.",
                    ))
            else:
                result.findings.append(CheckFinding(
                    check_id="CHECK_5",
                    tag="[OK]",
                    severity=SEVERITY_OK,
                    symbol="VerifactuInvoiceType",
                    message=f"All {len(required_types)} required invoice type codes defined.",
                ))

    # 5f: Verify specs/ directory exists for reference documents
    specs_dir = Path(__file__).parent.parent / "specs"
    if specs_dir.exists():
        spec_files = [f for f in specs_dir.iterdir() if not f.name.startswith(".")]
        result.findings.append(CheckFinding(
            check_id="CHECK_5",
            tag="[OK]",
            severity=SEVERITY_OK,
            symbol="specs/",
            message=f"specs/ directory found with {len(spec_files)} reference file(s).",
        ))
    else:
        result.findings.append(CheckFinding(
            check_id="CHECK_5",
            tag="[MISSING_SPECS]",
            severity=SEVERITY_WARNING,
            symbol="specs/",
            message=(
                "specs/ directory not found. "
                "Drop official XSD files (HAC/1177/2024, Facturae 3.2.2, TicketBAI provincial) "
                "into specs/ to enable schema-based validation. "
                "[NEED: download and bundle normative XSD files before first release]"
            ),
        ))

    return result


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def render_summary_table(report: AuditReport) -> str:
    """Render a human-readable ASCII summary table."""
    lines: list[str] = []
    sep = "─" * 80

    lines.append(sep)
    lines.append("  mcp-facturacion-electronica-es  Pre-publish Audit Report")
    lines.append(f"  Generated : {report.generated_at}")
    lines.append(f"  ES version: {report.es_version}")
    lines.append(f"  Core ver  : {report.core_version or 'not installed'}")
    lines.append(sep)

    for check in report.checks:
        status = "SKIPPED" if check.skipped else ("PASS" if check.passed else "FAIL")
        lines.append(f"\n  [{status}] {check.check_id}: {check.name}")
        if check.skipped:
            lines.append(f"         -> {check.skip_reason}")
            continue
        lines.append(
            f"         Blocking: {check.blocking_count}  "
            f"Warnings: {check.warning_count}  "
            f"OK: {sum(1 for f in check.findings if f.severity == SEVERITY_OK)}"
        )
        for finding in check.findings:
            if finding.severity in (SEVERITY_BLOCKING, SEVERITY_WARNING):
                indent = "    "
                tag_str = f"{finding.tag:<24}"
                msg = textwrap.fill(
                    finding.message,
                    width=72,
                    initial_indent=indent + tag_str + " ",
                    subsequent_indent=indent + " " * 25,
                )
                lines.append(msg)

    lines.append(f"\n{sep}")
    lines.append(
        f"  TOTAL — Blocking: {report.total_blocking}  "
        f"Warnings: {report.total_warnings}  "
        f"Exit code: {report.exit_code}"
    )
    verdict = {0: "PASS", 1: "WARNINGS", 2: "FAIL"}[report.exit_code]
    lines.append(f"  Verdict: {verdict}")
    lines.append(sep)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_audit() -> AuditReport:
    """Execute all checks and return the aggregated AuditReport. No side effects."""
    es_version = _get_installed_version("mcp-facturacion-electronica-es") or "0.0.0-dev"
    core_version = _get_installed_version("mcp-einvoicing-core")

    core_compat = True
    if core_version:
        spec = _read_core_version_spec_from_pyproject()
        if spec:
            core_compat = _version_in_range(core_version, spec)

    report = AuditReport(
        generated_at=datetime.now(UTC).isoformat(),
        es_version=es_version,
        core_version=core_version,
        core_version_compatible=core_compat,
    )

    report.checks.append(run_check_1())
    report.checks.append(run_check_2())
    report.checks.append(run_check_3())
    report.checks.append(run_check_4())
    report.checks.append(run_check_5())

    return report


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pre-publish audit: mcp-facturacion-electronica-es vs mcp-einvoicing-core",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Exit codes:
          0  All checks passed
          1  Warnings only
          2  Blocking failures (publish should be blocked)
        """),
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="Write JSON report to this path (default: audit/report.json)",
        default=None,
    )
    parser.add_argument(
        "--fail-on",
        metavar="LEVEL",
        choices=["blocking", "warnings", "never"],
        default="blocking",
        help=(
            "When to exit non-zero: "
            "'blocking' (default) = only on BLOCKING findings; "
            "'warnings' = on any warning or blocking; "
            "'never' = always exit 0 (for informational runs)."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress human-readable table; only write JSON.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entrypoint — returns exit code."""
    args = _parse_args(argv)

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
