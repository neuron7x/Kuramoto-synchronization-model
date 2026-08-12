"""Task 7 · End-to-end demo smoke gate.

Single test that proves the demo is runnable right now from the checked-
in state: every stage artifact exists, every figure exists with valid
PNG bytes, every gate fixture present, manifest is internally consistent,
and verdict headlines match the values cited in FINDINGS.md.

This is the one-gate-to-rule-them-all: if this test fails, the demo
is not shippable regardless of which subtest caused the failure.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

_RESULTS = Path("results")
_FIGURES = _RESULTS / "figures"
_GATES = _RESULTS / "gate_fixtures"
_FINDINGS = Path("research/microstructure/FINDINGS.md")

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

_EXPECTED_FIGURES = (
    "fig0_cover.png",
    "fig1_signal_validation.png",
    "fig2_dynamics.png",
    "fig3_coupling.png",
    "fig4_stability.png",
)

_EXPECTED_ARTIFACTS = (
    "L2_KILLTEST_VERDICT.json",
    "L2_IC_ATTRIBUTION.json",
    "L2_ROBUSTNESS.json",
    "L2_PURGED_CV.json",
    "L2_SPECTRAL.json",
    "L2_HURST.json",
    "L2_REGIME_MARKOV.json",
    "L2_TRANSFER_ENTROPY.json",
    "L2_CONDITIONAL_TE.json",
    "L2_WALK_FORWARD_SUMMARY.json",
    "L2_WALK_FORWARD.json",
    "L2_DIURNAL_PROFILE.json",
    "L2_EXEC_COST_SWEEP.json",
    "L2_FULL_CYCLE_MANIFEST.json",
)

_EXPECTED_GATES = (
    "breakeven_q75.json",
    "breakeven_q75_diurnal.json",
    "ic_test_q75.json",
)


def _load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


def test_every_committed_artifact_exists_and_parses() -> None:
    missing = [a for a in _EXPECTED_ARTIFACTS if not (_RESULTS / a).exists()]
    assert not missing, f"missing artifacts: {missing}"
    for artifact in _EXPECTED_ARTIFACTS:
        _load(_RESULTS / artifact)  # raises on parse error


def test_every_gate_fixture_exists_and_parses() -> None:
    missing = [g for g in _EXPECTED_GATES if not (_GATES / g).exists()]
    assert not missing, f"missing gate fixtures: {missing}"
    for gate in _EXPECTED_GATES:
        payload = _load(_GATES / gate)
        assert "value" in payload
        assert "tolerance" in payload


def test_every_figure_exists_with_png_magic() -> None:
    for fig in _EXPECTED_FIGURES:
        p = _FIGURES / fig
        assert p.exists(), f"figure missing: {p}"
        with p.open("rb") as fh:
            header = fh.read(8)
        assert header == _PNG_MAGIC, f"{p} is not a valid PNG file"
        assert p.stat().st_size > 10 * 1024, f"{p} suspiciously small"


def test_manifest_covers_all_expected_stages() -> None:
    manifest = _load(_RESULTS / "L2_FULL_CYCLE_MANIFEST.json")
    stage_names = {s["name"] for s in manifest["stages"]}
    assert stage_names == {
        "killtest",
        "attribution",
        "purged_cv",
        "spectral",
        "hurst",
        "regime_markov",
        "robustness",
        "transfer_entropy",
        "conditional_te",
    }
    # Figures manifest references all five
    figures = manifest.get("figures", {})
    assert set(figures.keys()) == {
        "cover",
        "signal_validation",
        "dynamics",
        "coupling",
        "stability",
    }


def test_findings_md_references_current_verdicts() -> None:
    if not _FINDINGS.exists():
        pytest.skip("FINDINGS.md not present")
    text = _FINDINGS.read_text(encoding="utf-8")
    # Headline: PROCEED
    assert re.search(r"\*\*PROCEED\*\*", text), "FINDINGS.md missing PROCEED headline"
    # 10 axes
    assert "10 independent methodologies" in text or "Ten orthogonal validations" in text
    # Spectral β, DFA H match artifacts
    spectral = _load(_RESULTS / "L2_SPECTRAL.json")
    hurst = _load(_RESULTS / "L2_HURST.json")
    beta_str = f"{float(spectral['redness_slope_beta']):.2f}"
    h_str = f"{float(hurst['report']['hurst_exponent']):.3f}"
    assert beta_str in text, f"β = {beta_str} not mentioned in FINDINGS.md"
    assert h_str in text, f"H = {h_str} not mentioned in FINDINGS.md"


def test_kill_test_verdict_is_proceed() -> None:
    killtest = _load(_RESULTS / "L2_KILLTEST_VERDICT.json")
    assert killtest["verdict"] == "PROCEED"


def test_all_ten_axes_have_artifact_receipts() -> None:
    """Each axis in FINDINGS has a concrete JSON payload that backs it."""
    artifact_receipts = {
        "1_killtest": "L2_KILLTEST_VERDICT.json",
        "2_bootstrap": "L2_ROBUSTNESS.json",
        "3_dsr": "L2_ROBUSTNESS.json",
        "4_purged_cv": "L2_PURGED_CV.json",
        "5_mi": "L2_ROBUSTNESS.json",
        "6_spectral": "L2_SPECTRAL.json",
        "7_hurst": "L2_HURST.json",
        "8_te": "L2_TRANSFER_ENTROPY.json",
        "9_cte": "L2_CONDITIONAL_TE.json",
        "10_walk_forward": "L2_WALK_FORWARD_SUMMARY.json",
    }
    missing = [k for k, v in artifact_receipts.items() if not (_RESULTS / v).exists()]
    assert not missing, f"axes without receipts: {missing}"
