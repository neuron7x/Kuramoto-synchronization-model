"""T1 · offline scripts write only under offline_robustness/ and never touch
protected paths."""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = sorted((REPO / "scripts").glob("analysis_cak_*.py"))
RENDERER = REPO / "scripts" / "render_cak_offline_robustness_report.py"
FORBIDDEN_PATH_SUBSTRS = (
    "shadow_validation",
    "paper_state",
    "/demo/",
    "core/cross_asset_kuramoto/",
    "PARAMETER_LOCK.json",
    "INPUT_CONTRACT.md",
    "ops/systemd",
    "fx_native_foundation",
    "research_line_registry",
    "combo_v1",
)


def _all_offline_scripts() -> list[Path]:
    out = list(SCRIPTS)
    if RENDERER.exists():
        out.append(RENDERER)
    return out


def test_offline_scripts_exist() -> None:
    assert len(SCRIPTS) >= 4, f"expected at least 4 analysis_cak_*.py scripts, found {len(SCRIPTS)}"


def test_no_forbidden_imports() -> None:
    forbidden_modules = ("backtest", "execution", "strategies")
    for script in _all_offline_scripts():
        tree = ast.parse(script.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                assert (
                    root not in forbidden_modules
                ), f"{script.name}: forbidden import from {node.module}"


def test_no_writes_to_forbidden_paths() -> None:
    """Regex over raw source: any string literal that references a forbidden
    write-target path must not be used as an argument to write_text/to_csv/
    mkdir or open-for-write. We use a coarse heuristic: flag if a forbidden
    path substring appears on the same source line as a write token."""
    write_tokens = re.compile(r"\b(write_text|to_csv|mkdir\(|open\(.*?[\"'][wa][\"'])")
    offenders: list[str] = []
    for script in _all_offline_scripts():
        for lineno, line in enumerate(script.read_text().splitlines(), 1):
            for needle in FORBIDDEN_PATH_SUBSTRS:
                if needle in line and write_tokens.search(line):
                    offenders.append(f"{script.name}:{lineno}: {line.strip()}")
    assert not offenders, "forbidden write sites:\n" + "\n".join(offenders)


def test_all_result_path_literals_point_to_offline_robustness() -> None:
    """Every string literal that references ``results/cross_asset_kuramoto/``
    must route to offline_robustness (or read-only inputs). The intent is
    that no code path writes outside of offline_robustness/."""
    path_re = re.compile(r"[\"'](results/cross_asset_kuramoto/[^\"']+)[\"']")
    read_only_allowed = (
        "results/cross_asset_kuramoto/PARAMETER_LOCK.json",
        "results/cross_asset_kuramoto/INPUT_CONTRACT.md",
        "results/cross_asset_kuramoto/demo/",
    )
    for script in _all_offline_scripts():
        for lineno, line in enumerate(script.read_text().splitlines(), 1):
            m = path_re.search(line)
            if not m:
                continue
            target = m.group(1)
            ok_read_only = any(target.startswith(prefix) for prefix in read_only_allowed)
            ok_write = "/offline_robustness/" in target
            assert ok_read_only or ok_write, (
                f"{script.name}:{lineno}: path literal {target!r} "
                "is neither a read-only protected input nor under offline_robustness/"
            )
