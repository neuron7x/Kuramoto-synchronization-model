# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""No-interference guard: robustness framework writes only under robustness_v1/.

Static AST + regex scan mirroring the offline-robustness packet's
`tests/analysis/test_cak_offline_no_interference.py`. Any write token
(``write_text``, ``to_csv``, ``mkdir(…)``, ``open(... , "w"/"a")``)
co-located with a forbidden-path substring fails the test.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

FRAMEWORK_PATHS = (
    REPO / "research" / "robustness",
    REPO / "backtest" / "robustness_gates.py",
    REPO / "scripts" / "run_kuramoto_robustness_v1.py",
)

FORBIDDEN_PATH_SUBSTRS = (
    "shadow_validation",
    "paper_state",
    "/demo/",
    "core/cross_asset_kuramoto/",
    "PARAMETER_LOCK.json",
    "INPUT_CONTRACT.md",
    "ops/systemd",
    "offline_robustness/SOURCE_HASHES.json",
    "offline_robustness/SEPARATION_FINDING.md",
    "offline_robustness/ROBUSTNESS_SUMMARY.md",
    "research_line_registry",
    "combo_v1",
)

FORBIDDEN_IMPORT_ROOTS = ("execution", "strategies", "paper_trader")

WRITE_TOKENS = re.compile(
    r"\b(write_text|to_csv|to_parquet|to_json|mkdir\(|open\(.*?[\"'][wa][\"'])"
)


def _iter_py_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix == ".py" else []
    return sorted(path.rglob("*.py"))


def _all_framework_files() -> list[Path]:
    files: list[Path] = []
    for base in FRAMEWORK_PATHS:
        files.extend(_iter_py_files(base))
    return files


def test_framework_files_exist() -> None:
    """NON_PHYSICS: filesystem inventory guard (no physical quantity)."""
    files = _all_framework_files()
    assert len(files) >= 10, f"expected at least 10 framework .py files, found {len(files)}"


def test_no_forbidden_imports() -> None:
    """NON_PHYSICS: import-isolation guard via static AST scan (no physics)."""
    for script in _all_framework_files():
        tree = ast.parse(script.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                assert (
                    root not in FORBIDDEN_IMPORT_ROOTS
                ), f"{script.relative_to(REPO)}: forbidden import from {node.module}"


def test_no_writes_to_forbidden_paths() -> None:
    """NON_PHYSICS: filesystem write-isolation guard (no physical quantity).

    Flags any write token co-located with a forbidden-path substring.
    """
    offenders: list[str] = []
    for script in _all_framework_files():
        for lineno, line in enumerate(script.read_text(encoding="utf-8").splitlines(), 1):
            for needle in FORBIDDEN_PATH_SUBSTRS:
                if needle in line and WRITE_TOKENS.search(line):
                    offenders.append(f"{script.relative_to(REPO)}:{lineno}: {line.strip()}")
    assert not offenders, "forbidden write sites:\n" + "\n".join(offenders)


def test_all_result_path_literals_point_to_robustness_v1() -> None:
    """NON_PHYSICS: output-path-routing guard (no physical quantity).

    Every results/cross_asset_kuramoto/ literal must route to robustness_v1/
    (writes) or to a read-only input (reads).
    """
    path_re = re.compile(r"[\"'](results/cross_asset_kuramoto/[^\"']+)[\"']")
    read_only_allowed = (
        "results/cross_asset_kuramoto/PARAMETER_LOCK.json",
        "results/cross_asset_kuramoto/INPUT_CONTRACT.md",
        "results/cross_asset_kuramoto/demo/",
        "results/cross_asset_kuramoto/offline_robustness/",
    )
    for script in _all_framework_files():
        for lineno, line in enumerate(script.read_text(encoding="utf-8").splitlines(), 1):
            m = path_re.search(line)
            if not m:
                continue
            target = m.group(1)
            ok_read_only = any(target.startswith(prefix) for prefix in read_only_allowed)
            ok_write = "/robustness_v1/" in target
            assert ok_read_only or ok_write, (
                f"{script.relative_to(REPO)}:{lineno}: path literal "
                f"{target!r} is neither a read-only frozen input nor under "
                "robustness_v1/"
            )
