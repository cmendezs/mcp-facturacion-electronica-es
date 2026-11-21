"""Regression tests for package metadata consistency."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import mcp_facturacion_electronica_es

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_version_slot_consistency() -> None:
    pyproject = tomllib.loads((_PACKAGE_ROOT / "pyproject.toml").read_text())
    assert mcp_facturacion_electronica_es.__version__ == pyproject["project"]["version"], (
        f"__version__={mcp_facturacion_electronica_es.__version__} drifted from "
        f"pyproject={pyproject['project']['version']}"
    )


def test_server_json_version_matches_pyproject() -> None:
    pyproject = tomllib.loads((_PACKAGE_ROOT / "pyproject.toml").read_text())
    server = json.loads((_PACKAGE_ROOT / "server.json").read_text())
    expected = pyproject["project"]["version"]
    assert server["version"] == expected, (
        f"server.json version={server['version']} drifted from pyproject={expected}"
    )
    pkg_version = server["packages"][0]["version"]
    assert pkg_version == expected, (
        f"server.json packages[0].version={pkg_version} drifted from pyproject={expected}"
    )


def test_sistema_informatico_version_tracks_package_version() -> None:
    """SistemaInformatico/Version must follow the package version, never a literal."""
    source = (
        _PACKAGE_ROOT / "src" / "mcp_facturacion_electronica_es" / "tools" / "verifactu.py"
    ).read_text()
    assert '"Version", "0.1.0"' not in source
    assert source.count('_sub(si, "Version", _PACKAGE_VERSION)') == 2
