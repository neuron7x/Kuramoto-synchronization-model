"""Regression tests to ensure cryptographically insecure RNGs stay out of security-critical modules."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SECURITY_SENSITIVE_MODULES = (
    Path("application/api/security.py"),
    Path("application/secrets/hashicorp.py"),
    Path("application/secrets/manager.py"),
    Path("application/secrets/rotation.py"),
    Path("application/secrets/secure_channel.py"),
    Path("application/secrets/vault.py"),
    Path("interfaces/secrets/backends.py"),
    Path("interfaces/secrets/manager.py"),
    Path("src/audit/audit_logger.py"),
)


def _find_random_imports(module_path: Path) -> list[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "random":
                    findings.append(f"import random (line {node.lineno})")
        elif isinstance(node, ast.ImportFrom) and node.module == "random":
            names = ", ".join(alias.name for alias in node.names)
            findings.append(f"from random import {names} (line {node.lineno})")
    return findings


@pytest.mark.parametrize("module_path", SECURITY_SENSITIVE_MODULES)
def test_security_modules_do_not_use_insecure_random(module_path: Path) -> None:
    """Security-sensitive modules must rely on cryptographically secure randomness."""

    assert module_path.exists(), f"Expected module {module_path} to exist"
    findings = _find_random_imports(module_path)
    assert not findings, f"Insecure random usage detected in {module_path}: {findings}"
