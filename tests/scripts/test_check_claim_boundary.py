# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Product-category claim-boundary gate — behavioural tests.

These tests are the self-falsification proof for
``scripts/ci/check_claim_boundary.py``: the gate must (1) pass on the
real canonical surface as shipped, (2) reject an injected unreviewed
product-category claim, (3) honour a reasoned allowlist entry, (4)
reject a stale allowlist entry that no longer matches, and (5) survive
unicode-dash / line-wrap obfuscation of a banned phrase.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "ci" / "check_claim_boundary.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("check_claim_boundary", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_claim_boundary"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod() -> Any:
    return _load_module()


def test_canonical_surface_holds(mod: Any) -> None:
    """The repository as shipped must keep the boundary (exit 0)."""
    assert mod.main() == 0


def test_normalisation_defeats_dash_and_wrap_obfuscation(mod: Any) -> None:
    """En-dash and NFKC variants of a banned phrase still match."""
    assert "live-trading" in mod._normalise("Live—Trading")
    assert mod._normalise("LIVE  TRADING") == "live trading"


def test_injected_claim_is_unreviewed(mod: Any, tmp_path: Path) -> None:
    """A genuine product-category claim is flagged unless allowlisted."""
    v = mod.Violation(
        file="docs/x.md", lineno=1, why="t", text="geosync emits live trading signals"
    )
    # not present in the shipped allowlist -> would be unreviewed
    allow = mod._load_allowlist()
    assert not any(e.file == v.file and e.match in v.text for e in allow)


def test_allowlist_entry_suppresses(mod: Any) -> None:
    """A reasoned allow entry whose match is a substring suppresses a hit."""
    e = mod.AllowEntry(
        file="docs/x.md",
        match=mod._normalise("trading signal"),
        reason="mechanism",
    )
    text = mod._normalise('a Signal docstring: """trading signal."""')
    assert e.match in text


def test_patterns_are_compiled_and_nonempty(mod: Any) -> None:
    assert mod._COMPILED, "boundary patterns must not be empty"
    assert any("live" in p.pattern for p, _ in mod._COMPILED)


# ---------------------------------------------------------------------------
# Instrument B — code-surface coverage (composite trading-signal firewall)
# ---------------------------------------------------------------------------


def test_code_surfaces_are_scanned(mod: Any) -> None:
    """The claim-bearing indicator modules must be part of the scanned
    surface — not just the markdown docs. This is what makes the gate a
    firewall against trading-product wording reappearing in code."""
    scanned = {p.relative_to(mod.ROOT).as_posix() for p in mod._iter_surface()}
    for rel in mod.CODE_SURFACE_FILES:
        assert rel in scanned, f"{rel} is not on the scanned claim-boundary surface"


def test_composite_module_has_no_trading_product_wording(mod: Any) -> None:
    """Regression: the composite indicator module must carry no unreviewed
    product-category phrasing on its own prose surface."""
    composite = mod.ROOT / "core" / "indicators" / "kuramoto_ricci_composite.py"
    allow = mod._load_allowlist()
    rel = composite.relative_to(mod.ROOT).as_posix()
    for lineno, raw in enumerate(composite.read_text(encoding="utf-8").splitlines(), 1):
        norm = mod._normalise(raw)
        for pattern, why in mod._COMPILED:
            if pattern.search(norm):
                suppressed = any(e.file == rel and e.match in norm for e in allow)
                assert suppressed, f"{rel}:{lineno} unreviewed [{why}]: {norm[:100]}"


@pytest.mark.parametrize(
    "rel",
    [
        "core/indicators/hurst.py",
        "core/indicators/entropy.py",
    ],
)
def test_descriptor_modules_have_no_trading_product_wording(mod: Any, rel: str) -> None:
    """Regression (Instrument E): the Hurst and Entropy descriptor modules must
    carry no unreviewed product-category phrasing on their own prose surface,
    mirroring the composite-module guard. These are descriptor-only modules and
    must stay on the firewalled claim-boundary surface."""
    assert rel in mod.CODE_SURFACE_FILES, f"{rel} must be on the firewall surface list"
    path = mod.ROOT / Path(rel)
    allow = mod._load_allowlist()
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        norm = mod._normalise(raw)
        for pattern, why in mod._COMPILED:
            if pattern.search(norm):
                suppressed = any(e.file == rel and e.match in norm for e in allow)
                assert suppressed, f"{rel}:{lineno} unreviewed [{why}]: {norm[:100]}"


def test_injected_code_surface_claim_is_flagged_by_main(
    mod: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If a banned phrase is injected into a scanned code surface, main()
    must fail (exit 1) — proving the firewall actually gates code, not only
    docs. We point the gate at a temp ROOT carrying a poisoned module so the
    real tree is never mutated."""
    surface = tmp_path / "evil_module.py"
    surface.write_text(
        '"""This module emits actionable trading signals."""\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "ALLOWLIST_PATH", tmp_path / "missing_allow.json")
    monkeypatch.setattr(mod, "SCAN_GLOBS", ())
    monkeypatch.setattr(mod, "CODE_SURFACE_FILES", ("evil_module.py",))
    assert mod.main() == 1
