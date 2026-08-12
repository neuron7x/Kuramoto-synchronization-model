# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for ``scripts/ci/compute_pai.py``.

The compute_pai script is a CI gate — a bug here either silently
passes when PAI should fail (false negative, very bad) or fails when
PAI should pass (annoying). These tests pin the parser, the scorer,
and the threshold semantics against fixtures, independent of the live
CLAUDE.md / tests/ tree.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "ci" / "compute_pai.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("compute_pai", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["compute_pai"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cp() -> Any:
    return _load_module()


# ---------------------------------------------------------------------------
# _expand_invariants — range and single forms
# ---------------------------------------------------------------------------


def test_expand_invariants_range_form(cp: Any) -> None:
    expanded = cp._expand_invariants("INV-K1..K7")
    assert expanded == frozenset(
        {"INV-K1", "INV-K2", "INV-K3", "INV-K4", "INV-K5", "INV-K6", "INV-K7"}
    )


def test_expand_invariants_dro_range(cp: Any) -> None:
    expanded = cp._expand_invariants("INV-DRO1..5")
    assert expanded == frozenset({"INV-DRO1", "INV-DRO2", "INV-DRO3", "INV-DRO4", "INV-DRO5"})


def test_expand_invariants_single_form(cp: Any) -> None:
    assert cp._expand_invariants("INV-YV1") == frozenset({"INV-YV1"})


def test_expand_invariants_mixed_range_and_single(cp: Any) -> None:
    expanded = cp._expand_invariants("INV-OA1..3 with INV-AC1-rev")
    assert "INV-OA1" in expanded
    assert "INV-OA2" in expanded
    assert "INV-OA3" in expanded
    assert "INV-AC1-rev" in expanded


def test_expand_invariants_empty_cell(cp: Any) -> None:
    assert cp._expand_invariants("nothing here") == frozenset()


# ---------------------------------------------------------------------------
# _parse_routing_table — fixture-driven CLAUDE.md
# ---------------------------------------------------------------------------


SYNTHETIC_CLAUDE_MD = """\
# CLAUDE.md

Some preamble.

## MODULE → INVARIANT ROUTING

| Files matching... | Invariants |
|---|---|
| `*kuramoto*` | INV-K1..K3 |
| `*serotonin*` | INV-5HT1..2 |
| `application/`, `cli/` | No physics |

---

## DECISION RULES
"""


def test_parse_routing_table_picks_up_invariant_rows(
    tmp_path: Path,
    cp: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    md_path = tmp_path / "CLAUDE.md"
    md_path.write_text(SYNTHETIC_CLAUDE_MD, encoding="utf-8")
    groups = cp._parse_routing_table(SYNTHETIC_CLAUDE_MD)
    labels = [g.label for g in groups]
    assert "*kuramoto*" in labels
    assert "*serotonin*" in labels
    assert "application/ | cli/" not in labels  # No-physics row drops out


def test_parse_routing_table_invariant_count(cp: Any) -> None:
    groups = cp._parse_routing_table(SYNTHETIC_CLAUDE_MD)
    by_label = {g.label: g for g in groups}
    assert len(by_label["*kuramoto*"].declared_invariants) == 3
    assert len(by_label["*serotonin*"].declared_invariants) == 2


def test_parse_routing_table_missing_section(cp: Any) -> None:
    with pytest.raises(ValueError, match="MODULE"):
        cp._parse_routing_table("# no routing here")


# ---------------------------------------------------------------------------
# _score_modules — coverage threshold semantics
# ---------------------------------------------------------------------------


def _make_group(cp: Any, label: str, invs: list[str]) -> Any:
    return cp.ModuleGroup(label=label, patterns=(label,), declared_invariants=frozenset(invs))


def _abs(rel: str, cp: Any) -> Path:
    """Build an absolute path under ROOT — _score_modules requires it."""
    root = cp.ROOT
    assert isinstance(root, Path)
    return root / rel


def test_score_modules_three_or_more_invs_pass(cp: Any) -> None:
    group = _make_group(cp, "kuramoto", ["INV-K1", "INV-K2", "INV-K3"])
    inv_to_files = {
        "INV-K1": {_abs("tests/test_a.py", cp)},
        "INV-K2": {_abs("tests/test_b.py", cp)},
        "INV-K3": {_abs("tests/test_c.py", cp)},
    }
    scores = cp._score_modules([group], inv_to_files)
    assert scores[0].covered is True
    assert scores[0].distinct_inv_refs_in_tests == 3


def test_score_modules_full_coverage_below_three_passes(cp: Any) -> None:
    """A 1-invariant module with that one invariant tested is covered."""
    group = _make_group(cp, "yv", ["INV-YV1"])
    inv_to_files = {"INV-YV1": {_abs("tests/test_yv.py", cp)}}
    scores = cp._score_modules([group], inv_to_files)
    assert scores[0].covered is True


def test_score_modules_partial_below_three_fails(cp: Any) -> None:
    """A 5-invariant module with only 2 invariants tested fails."""
    group = _make_group(cp, "dro", [f"INV-DRO{i}" for i in range(1, 6)])
    inv_to_files = {
        "INV-DRO3": {_abs("tests/test_dro_a.py", cp)},
        "INV-DRO4": {_abs("tests/test_dro_b.py", cp)},
    }
    scores = cp._score_modules([group], inv_to_files)
    assert scores[0].covered is False
    assert scores[0].distinct_inv_refs_in_tests == 2


def test_score_modules_zero_coverage_fails(cp: Any) -> None:
    group = _make_group(cp, "ac", ["INV-AC1-rev"])
    scores = cp._score_modules([group], {})
    assert scores[0].covered is False
    assert scores[0].distinct_inv_refs_in_tests == 0


# ---------------------------------------------------------------------------
# _count_forbidden_assertions — CLAUDE.md "Forbidden:" anti-pattern scan
# ---------------------------------------------------------------------------


def test_forbidden_magic_bare_bound_caught_without_inv(tmp_path: Path, cp: Any) -> None:
    fixture = tmp_path / "test_x.py"
    fixture.write_text("def test_a():\n    assert R < 0.3\n", encoding="utf-8")
    assert cp._count_forbidden_assertions(fixture) == 1


def test_forbidden_redeemed_by_inv_citation(tmp_path: Path, cp: Any) -> None:
    fixture = tmp_path / "test_x.py"
    fixture.write_text(
        "def test_a():\n    assert R < 0.3  # INV-K2 finite-size bound\n",
        encoding="utf-8",
    )
    assert cp._count_forbidden_assertions(fixture) == 0


def test_forbidden_exact_stochastic_caught(tmp_path: Path, cp: Any) -> None:
    fixture = tmp_path / "test_x.py"
    fixture.write_text("def test_a():\n    assert R == 0.0\n", encoding="utf-8")
    assert cp._count_forbidden_assertions(fixture) == 1


def test_forbidden_no_context_caught(tmp_path: Path, cp: Any) -> None:
    fixture = tmp_path / "test_x.py"
    fixture.write_text("def test_a():\n    assert result.order > 0\n", encoding="utf-8")
    assert cp._count_forbidden_assertions(fixture) == 1


def test_forbidden_clean_file_zero(tmp_path: Path, cp: Any) -> None:
    fixture = tmp_path / "test_x.py"
    fixture.write_text(
        "def test_a():\n    assert R_final < epsilon, f'INV-K2 VIOLATED: R={R_final:.4f}'\n",
        encoding="utf-8",
    )
    assert cp._count_forbidden_assertions(fixture) == 0


def test_score_modules_emits_forbidden_count(tmp_path: Path, cp: Any) -> None:
    fx = tmp_path / "test_y.py"
    fx.write_text(
        "from x import R\n# INV-K1 referenced in this file\ndef test_one():\n    assert R < 0.3\n",
        encoding="utf-8",
    )
    group = _make_group(cp, "kuramoto", ["INV-K1"])
    inv_to_files = {"INV-K1": {fx}}
    scores = cp._score_modules([group], inv_to_files)
    assert scores[0].covered is True
    assert scores[0].forbidden_assertion_count == 1
    assert any("test_y.py" in entry for entry in scores[0].forbidden_assertion_files)


# ---------------------------------------------------------------------------
# Snapshot serialization
# ---------------------------------------------------------------------------


def test_snapshot_to_dict_round_trip(cp: Any) -> None:
    score = cp.ModuleScore(
        label="x",
        declared_invariants=2,
        distinct_inv_refs_in_tests=2,
        test_files=["tests/test_x.py"],
        covered=True,
    )
    snap = cp.PaiSnapshot(
        pai=1.0,
        threshold=0.9,
        threshold_met=True,
        modules=[score],
        total_declared=1,
        total_covered=1,
    )
    payload = json.loads(json.dumps(snap.to_dict()))
    assert payload["pai"] == 1.0
    assert payload["threshold_met"] is True
    assert payload["modules"][0]["label"] == "x"
    assert payload["modules"][0]["test_files_count"] == 1


# ---------------------------------------------------------------------------
# Live integration — exercise the actual repo state once
# ---------------------------------------------------------------------------


def test_live_pai_at_or_above_phase0_threshold(cp: Any) -> None:
    """Repo PAI must stay above the IERD §5 0.90 floor on main."""
    snapshot = cp.compute_pai(threshold=0.9)
    assert snapshot.threshold_met, (
        f"PAI dropped below 0.90: {snapshot.pai:.4f}; uncovered modules: "
        f"{[m.label for m in snapshot.modules if not m.covered]}"
    )


def test_live_pai_module_count_matches_routing(cp: Any) -> None:
    """Catch silent routing-table edits that drop modules."""
    snapshot = cp.compute_pai(threshold=0.9)
    assert (
        snapshot.total_declared >= 19
    ), f"routing table shrunk to {snapshot.total_declared} modules"
