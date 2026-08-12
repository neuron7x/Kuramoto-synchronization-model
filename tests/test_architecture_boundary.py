# mypy: disable-error-code="attr-defined,unused-ignore"
"""Architecture boundary enforcement.

INV-ARCH-1: geosync core NEVER imports from coherence_bridge
INV-ARCH-2: coherence_bridge MAY import from geosync
INV-ARCH-3: transport layer (kafka/grpc/questdb) NEVER in geosync/

Runs on BOTH branches:
  main: coherence_bridge absent → tests trivially pass
  feat/askar-ots: boundary actively enforced
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
GEOSYNC_DIR = REPO_ROOT / "geosync"
COHERENCE_DIR = REPO_ROOT / "coherence_bridge"

TRANSPORT_MODULES = frozenset({"kafka", "grpc", "questdb", "protobuf", "grpcio"})


def _get_imports(filepath: Path) -> list[str]:
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.split(".")[0])
    return imports


def _py_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return [p for p in directory.rglob("*.py") if "__pycache__" not in str(p)]


def test_geosync_never_imports_coherence_bridge() -> None:
    """INV-ARCH-1: canonical core independent of integration layer."""
    violations = []
    for f in _py_files(GEOSYNC_DIR):
        if "coherence_bridge" in _get_imports(f):
            violations.append(str(f.relative_to(REPO_ROOT)))
    assert violations == [], "INV-ARCH-1 VIOLATED: geosync imports coherence_bridge:\n" + "\n".join(
        violations
    )


def test_geosync_never_imports_transport() -> None:
    """INV-ARCH-3: canonical core has no transport dependencies."""
    violations = []
    for f in _py_files(GEOSYNC_DIR):
        bad = [m for m in _get_imports(f) if m in TRANSPORT_MODULES]
        if bad:
            violations.append(f"{f.relative_to(REPO_ROOT)}: {bad}")
    assert violations == [], "INV-ARCH-3 VIOLATED: geosync imports transport:\n" + "\n".join(
        violations
    )


def test_coherence_bridge_no_otp_internals() -> None:
    """coherence_bridge is OTP-agnostic at source level."""
    if not COHERENCE_DIR.exists():
        pytest.skip("coherence_bridge not present (main branch)")
    otp = frozenset({"otp_common", "otp_router", "otp_strategy"})
    violations = []
    for f in _py_files(COHERENCE_DIR):
        bad = [m for m in _get_imports(f) if m in otp]
        if bad:
            violations.append(f"{f.relative_to(REPO_ROOT)}: {bad}")
    assert violations == [], "coherence_bridge imports OTP internals:\n" + "\n".join(violations)
