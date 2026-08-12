# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Descriptor-to-physics promotion firewall — behavioural tests.

Self-falsification proof for ``tools/claims/check_descriptor_promotion.py``:

1. the firewall passes on the real canonical surface as shipped (zero false
   positives on legitimate descriptor-discipline prose);
2. every one of the six forbidden promotions fires its own ``rule_id``;
3. the negation guard lets honest negation / proxy-disclosure through;
4. a reasoned allowlist entry suppresses an otherwise-failing promotion;
5. a stale allowlist entry that no longer matches fails the gate;
6. unicode-dash / line-wrap obfuscation cannot smuggle a promotion past it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "tools" / "claims" / "check_descriptor_promotion.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("check_descriptor_promotion", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_descriptor_promotion"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod() -> Any:
    return _load_module()


# --- 1. real surface holds ---------------------------------------------------


def test_canonical_surface_holds(mod: Any) -> None:
    """The firewall must pass on the repository as shipped (no false positives)."""
    assert mod.main() == 0


def test_surface_is_non_empty(mod: Any) -> None:
    """A scanner that scans nothing is vacuously green — guard against that."""
    assert len(mod._iter_surface()) > 100


# --- 2. every forbidden promotion fires its own rule -------------------------

POSITIVE_CASES: tuple[tuple[str, str], ...] = (
    ("descriptor-to-physical-law", "This descriptor is a physical law of markets."),
    ("proxy-phase-to-physical-phase", "The proxy phase equals the physical phase of the asset."),
    (
        "correlation-ricci-to-microstructure-ricci",
        "Correlation-graph Ricci is the L2 microstructure Ricci.",
    ),
    ("coherence-to-market-consensus", "Phase coherence measures market consensus directly."),
    ("topology-to-predictive-validity", "This topology feature predicts the price next bar."),
    ("feature-to-alpha", "Each feature is alpha you can trade."),
)


@pytest.mark.parametrize(("rule_id", "line"), POSITIVE_CASES)
def test_forbidden_promotion_fires(mod: Any, rule_id: str, line: str) -> None:
    hits = [r for r, _ in mod.scan_line(mod._normalise(line))]
    assert rule_id in hits, f"rule {rule_id} failed to fire on: {line!r} (got {hits})"


def test_every_rule_id_is_covered(mod: Any) -> None:
    """Positive cases must exercise all six rules — no rule ships untested."""
    covered = {rid for rid, _ in POSITIVE_CASES}
    declared = {rule.rule_id for rule in mod.PROMOTION_RULES}
    assert covered == declared


# --- 3. negation / proxy-disclosure passes -----------------------------------

NEGATIVE_CASES: tuple[str, ...] = (
    "This descriptor is NOT a physical law.",
    "The proxy phase is not the physical phase; it is a Hilbert estimate.",
    "Bid-ask spread as a proxy for slippage.",
    "Phase coherence does not imply market consensus.",
    "This topology feature does not predict the price.",
    "A feature is not alpha.",
    "Correlation-graph Ricci is a descriptor, not L2 microstructure Ricci.",
    # Real repository phrasing that must keep passing:
    "The Ricci cross-sectional edge on L2 microstructure passes ten axes.",
    "tier: EXTRAPOLATED",
    "Measures bid-ask spread as a proxy for slippage.",
)


@pytest.mark.parametrize("line", NEGATIVE_CASES)
def test_descriptor_discipline_passes(mod: Any, line: str) -> None:
    hits = mod.scan_line(mod._normalise(line))
    assert hits == [], f"false positive on legitimate prose: {line!r} (got {hits})"


# --- 4 & 5. allowlist honoured / stale entry rejected ------------------------


def _write_promotion_doc(tmp_path: Path, line: str) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    doc = docs / "leak.md"
    doc.write_text(f"# leak\n\n{line}\n", encoding="utf-8")
    return doc


def _patch_root(mod: Any, monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    """Re-point the checker's module-level paths at a throwaway tree."""
    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(mod, "ALLOWLIST_PATH", root / ".github" / "descriptor_promotion_allow.json")
    monkeypatch.setattr(mod, "CODE_SURFACE_FILES", ())


def test_injected_promotion_fails(
    mod: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_promotion_doc(tmp_path, "Each feature is alpha you can trade.")
    (tmp_path / ".github").mkdir()
    _patch_root(mod, monkeypatch, tmp_path)
    assert mod.main() == 1


def test_allowlist_suppresses_reviewed_line(
    mod: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    line = "Each feature is alpha you can trade."
    _write_promotion_doc(tmp_path, line)
    gh = tmp_path / ".github"
    gh.mkdir()
    (gh / "descriptor_promotion_allow.json").write_text(
        json.dumps(
            {
                "version": 1,
                "allow": [
                    {
                        "file": "docs/leak.md",
                        "match": "each feature is alpha you can trade.",
                        "reason": "test: reviewed mechanism quotation",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    _patch_root(mod, monkeypatch, tmp_path)
    assert mod.main() == 0


def test_stale_allowlist_entry_fails(
    mod: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Clean doc → the allowlist entry matches nothing → stale → fail-closed.
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "clean.md").write_text("# clean\n\nA feature is not alpha.\n", encoding="utf-8")
    gh = tmp_path / ".github"
    gh.mkdir()
    (gh / "descriptor_promotion_allow.json").write_text(
        json.dumps(
            {
                "version": 1,
                "allow": [
                    {
                        "file": "docs/clean.md",
                        "match": "each feature is alpha you can trade.",
                        "reason": "test: now stale",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    _patch_root(mod, monkeypatch, tmp_path)
    unreviewed, stale, _ = mod.evaluate()
    assert unreviewed == []
    assert len(stale) == 1
    assert mod.main() == 1


# --- 6. obfuscation cannot smuggle a promotion -------------------------------


def test_unicode_dash_obfuscation_is_caught(mod: Any) -> None:
    """An em-dash / non-breaking variant of a banned phrase still fires."""
    # 'out‑of‑sample' uses non-breaking hyphens; normalisation folds them.
    line = "The topology feature is out‑of‑sample predictive."
    hits = [r for r, _ in mod.scan_line(mod._normalise(line))]
    assert "topology-to-predictive-validity" in hits
