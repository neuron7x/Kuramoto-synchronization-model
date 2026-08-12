# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contract guards for the pre-registered rolling-ES OOS evidence (PR #1425).

These tests are data-free and deterministic — they never touch the SHA-pinned
private OOS CSVs, so they run in CI. They lock four surfaces so the strict
evidence binding cannot silently regress:

    P0-5  the benchmark invokes rolling_es_proximity in strict (fail_closed) mode;
    P0-6  the committed artifact records the strict policy and frozen REJECT;
    P0-2  the strict-replay proof artifact is present and internally honest;
    P1-1  tools/verify_rolling_es_strict_replay.py verifies the pair green.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "artifacts" / "rolling_es_proximity_oos.json"
PROOF = ROOT / "artifacts" / "rolling_es_proximity_oos.strict_replay_proof.json"
VERIFIER = ROOT / "tools" / "verify_rolling_es_strict_replay.py"
PREREG = ROOT / "results" / "cross_asset_kuramoto" / "SL_ES_PREREGISTRATION.md"

_FORBIDDEN_PROMOTION = (
    "ACCEPTED_T2B",
    "PROMOTED",
    "physics_score_credit",
    "validated lead indicator",
)


# ── P0-5 ────────────────────────────────────────────────────────────────────
class _CapturedStrictCall(Exception):
    """Sentinel raised after capturing kwargs to abort main() before any write."""


def test_oos_benchmark_invokes_rolling_es_proximity_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-5: the OOS benchmark must call the engine with fail_closed=True.

    Monkeypatch the benchmark's ``rolling_es_proximity`` reference to capture its
    kwargs and abort before any downstream compute or artifact write. If a future
    edit reverts the benchmark to lenient mode, ``fail_closed`` is False/absent and
    this fails — even though the lower-level rolling tests would still pass.
    """
    import benchmarks.rolling_es_proximity_oos as bench

    captured: dict[str, object] = {}

    def _fake_load_panel(*_a: object, **_k: object) -> tuple[pd.DataFrame, dict[str, str]]:
        idx = pd.date_range("2024-01-01", periods=20, freq="D")
        data = {a: np.linspace(100.0, 110.0, 20) for a in bench.ASSETS}
        return pd.DataFrame(data, index=idx), {a: "0" * 64 for a in bench.ASSETS}

    def _capturing_rolling(*_args: object, **kwargs: object) -> np.ndarray:
        captured.update(kwargs)
        raise _CapturedStrictCall

    monkeypatch.setattr(bench, "load_panel", _fake_load_panel)
    monkeypatch.setattr(bench, "rolling_es_proximity", _capturing_rolling)

    with pytest.raises(_CapturedStrictCall):
        bench.main()

    assert captured.get("fail_closed") is True, (
        "OOS benchmark VIOLATED: rolling_es_proximity must be invoked with "
        f"fail_closed=True (strict evidence mode); got kwargs={captured!r}."
    )


# ── P0-6 ────────────────────────────────────────────────────────────────────
def test_rolling_es_artifact_records_strict_policy() -> None:
    """P0-6: the committed artifact records strict mode and the frozen REJECT."""
    raw = ARTIFACT.read_text(encoding="utf-8")
    art = json.loads(raw)

    assert art["config"]["fail_closed"] is True
    assert art["strict_replay"]["enabled"] is True
    assert art["strict_replay"]["failed_window_count"] == 0
    assert art["decision"] == "REJECT"
    assert art["registered"] == "2026-05-06"
    # frozen numeric criterion still fires (rejection is real, not cosmetic).
    assert float(art["p_value"]) > float(art["config"]["p_value_threshold"])

    lowered = raw.lower()
    for bad in _FORBIDDEN_PROMOTION:
        assert bad.lower() not in lowered, f"forbidden promotion string in artifact: {bad!r}"


# ── P0-2 ────────────────────────────────────────────────────────────────────
def test_strict_replay_proof_exists_and_is_bound() -> None:
    """P0-2: the strict-replay proof is present and asserts fail_closed neutrality."""
    assert PROOF.exists(), "missing strict_replay_proof.json"
    proof = json.loads(PROOF.read_text(encoding="utf-8"))

    assert proof["verdict"] == "STRICT_REPLAY_BOUND"
    assert proof["strict_policy"]["fail_closed"] is True
    assert proof["strict_policy"]["failed_window_count"] == 0

    # metric_equality here proves strict == lenient under the current runtime.
    assert proof["metric_equality_basis"] == "strict_vs_lenient_current_runtime"
    meq = proof["metric_equality"]
    assert meq and all(v is True for v in meq.values()), (
        f"strict-vs-lenient metric_equality must be all-true, got {meq!r}"
    )


def test_strict_replay_proof_honestly_discloses_model_drift() -> None:
    """P0-2 honesty: the proof discloses the post-registration model drift.

    The frozen numerics predate the fitted-state runtime, so p_value/taus do NOT
    reproduce — but decision/leads_rate/n_episodes/r_peak_indices do, and the
    REJECT verdict is invariant. The proof must say this plainly rather than
    claim a false bit-identity to the committed record.
    """
    proof = json.loads(PROOF.read_text(encoding="utf-8"))
    fr = proof["frozen_reproduction"]

    assert fr["decision_committed"] == "REJECT"
    assert fr["decision_current_runtime"] == "REJECT"
    eq = fr["metric_equality"]
    for k in ("decision", "leads_rate", "n_episodes", "r_peak_indices"):
        assert eq[k] is True, f"decision-invariant metric must reproduce: {k}"
    # honest disclosure: these are known to differ, not silently claimed equal.
    assert eq["p_value"] is False
    assert eq["taus"] is False


# ── P1-2 ────────────────────────────────────────────────────────────────────
def test_preregistration_amendment_is_policy_not_retune() -> None:
    """P1-2: the prereg amendment is labelled a failure-policy ratchet.

    It must (a) reference the committed strict-replay proof artifact, (b) frame
    fail_closed as a policy ratchet / metric-neutral rather than a numeric
    re-registration, and (c) still record the REJECT H1 verdict.
    """
    text = PREREG.read_text(encoding="utf-8")
    assert "rolling_es_proximity_oos.strict_replay_proof.json" in text, (
        "prereg amendment must reference the strict-replay proof artifact"
    )
    assert "metric-NEUTRAL" in text or "metric-neutral" in text
    assert "failure-POLICY ratchet" in text or "failure-policy ratchet" in text
    assert "REJECT H1" in text


# ── P1-1 ────────────────────────────────────────────────────────────────────
def test_verifier_tool_passes_on_committed_evidence() -> None:
    """P1-1: the verifier CLI exits 0 on the committed artifact/proof pair."""
    result = subprocess.run(
        [sys.executable, str(VERIFIER)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"verifier failed (rc={result.returncode}):\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
