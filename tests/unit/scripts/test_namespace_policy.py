# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from pathlib import Path

from scripts.check_namespace_policy import find_namespace_violations


def test_detects_direct_src_import(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    target.write_text("from src.data import pipeline\n", encoding="utf-8")

    violations = find_namespace_violations(tmp_path, allowlist=set())

    assert len(violations) == 1
    violation = violations[0]
    assert violation.path == Path("module.py")
    assert violation.module == "src.data"


def test_allowlist_suppresses_known_legacy_path(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.py"
    legacy.write_text("import src.risk.risk_manager\n", encoding="utf-8")

    violations = find_namespace_violations(tmp_path, allowlist={Path("legacy.py")})

    assert violations == []
