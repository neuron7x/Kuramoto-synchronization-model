# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Verify (and optionally regenerate) the strict-replay evidence binding for the
pre-registered Stuart-Landau ES OOS test.

Two responsibilities, cleanly split so CI never needs the private OOS data:

    default (verify)   Pure JSON checks over the two committed artifacts. No
                       market data, no simulation, fully deterministic. Wired
                       into a pytest test and runnable as a gate.

    --generate         Re-derives the proof from the real frozen OOS window
                       (requires ~/spikes/... source CSVs, SHA-pinned in the
                       artifact). Runs the rolling ES engine in BOTH lenient and
                       strict mode, proves they are bit-identical with zero
                       fail-closed windows, and records how the current runtime
                       reproduces the frozen 2026-05-06 (#536) numeric record.

What is proven vs. what is disclosed
------------------------------------
BOUND  (metric_equality): fail_closed=True is metric-neutral — the strict and
       lenient rolling-ES series produced by the *current* runtime are
       bit-identical and no window raises. Adding the strict flag cannot alter
       any downstream metric.

DISCLOSED (frozen_reproduction): the committed artifact's numerics were frozen
       under the #536 model. The runtime was updated post-registration
       (fitted-state sweep / Hilbert-growth mu; #1208, #1362), so the current
       runtime reproduces `decision`, `leads_rate`, `n_episodes` and
       `r_peak_indices` exactly, but NOT `p_value`/`taus`. The pre-registered
       decision (REJECT, H1 not promoted) is invariant across both models. This
       is recorded honestly, not hidden: fail_closed did not move these numbers;
       the post-registration model update did.

Usage:
    python tools/verify_rolling_es_strict_replay.py            # verify (CI)
    PYTHONPATH=. python tools/verify_rolling_es_strict_replay.py --generate
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = REPO_ROOT / "artifacts" / "rolling_es_proximity_oos.json"
PROOF = REPO_ROOT / "artifacts" / "rolling_es_proximity_oos.strict_replay_proof.json"

# Metrics that must reproduce exactly across the #536 and current runtime. The
# pre-registered REJECT verdict rests on these; if any breaks, the conclusion is
# no longer model-invariant and the PR must fail.
_DECISION_INVARIANT_KEYS = ("decision", "leads_rate", "n_episodes", "r_peak_indices")
# Metrics known to differ under the post-registration model update. Recorded for
# transparency; NOT asserted equal (that would be a false claim).
_MODEL_SENSITIVE_KEYS = ("p_value", "taus", "tau_mean", "tau_median")

_FORBIDDEN_PROMOTION_STRINGS = (
    "ACCEPTED_T2B",
    "PROMOTED",
    "physics_score_credit",
    "validated lead indicator",
)


# ──────────────────────────────────────────────────────────────────────────
# Verification (CI-safe, no data, no simulation)
# ──────────────────────────────────────────────────────────────────────────
def verify() -> int:
    """Fail-closed structural verification of the committed evidence pair."""
    errors: list[str] = []

    if not ARTIFACT.exists():
        print(f"FAIL: missing artifact {ARTIFACT}", file=sys.stderr)
        return 2
    if not PROOF.exists():
        print(f"FAIL: missing proof {PROOF}", file=sys.stderr)
        return 2

    art: dict[str, Any] = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    proof: dict[str, Any] = json.loads(PROOF.read_text(encoding="utf-8"))

    # 1. Artifact records the strict policy.
    if art.get("config", {}).get("fail_closed") is not True:
        errors.append("artifact.config.fail_closed must be true")
    strict = art.get("strict_replay", {})
    if strict.get("enabled") is not True:
        errors.append("artifact.strict_replay.enabled must be true")
    if strict.get("failed_window_count") != 0:
        errors.append("artifact.strict_replay.failed_window_count must be 0")

    # 2. Frozen decision is untouched.
    if art.get("decision") != "REJECT":
        errors.append(f"artifact.decision must remain REJECT, got {art.get('decision')!r}")

    # 3. No T2b re-promotion language anywhere in the evidence.
    blob = (ARTIFACT.read_text(encoding="utf-8") + PROOF.read_text(encoding="utf-8")).lower()
    for bad in _FORBIDDEN_PROMOTION_STRINGS:
        if bad.lower() in blob:
            errors.append(f"forbidden promotion string present: {bad!r}")

    # 4. Proof structural contract.
    if proof.get("verdict") != "STRICT_REPLAY_BOUND":
        errors.append(f"proof.verdict must be STRICT_REPLAY_BOUND, got {proof.get('verdict')!r}")
    sp = proof.get("strict_policy", {})
    if sp.get("fail_closed") is not True:
        errors.append("proof.strict_policy.fail_closed must be true")
    if sp.get("failed_window_count") != 0:
        errors.append("proof.strict_policy.failed_window_count must be 0")

    # 5. metric_equality is the strict-vs-lenient (current runtime) proof: all true.
    meq = proof.get("metric_equality", {})
    if proof.get("metric_equality_basis") != "strict_vs_lenient_current_runtime":
        errors.append("proof.metric_equality_basis must be strict_vs_lenient_current_runtime")
    if not meq or not all(v is True for v in meq.values()):
        errors.append(f"proof.metric_equality must be all-true, got {meq!r}")

    # 6. frozen_reproduction honestly discloses the model drift.
    fr = proof.get("frozen_reproduction", {})
    fr_eq = fr.get("metric_equality", {})
    for k in _DECISION_INVARIANT_KEYS:
        if fr_eq.get(k) is not True:
            errors.append(
                f"frozen_reproduction.metric_equality.{k} must be true (decision-invariant)"
            )
    if fr.get("decision_committed") != "REJECT" or fr.get("decision_current_runtime") != "REJECT":
        errors.append("frozen_reproduction must record REJECT under both models")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print(
        "OK: strict-replay evidence bound and consistent (fail_closed metric-neutral; "
        "frozen decision REJECT invariant across models)."
    )
    return 0


# ──────────────────────────────────────────────────────────────────────────
# Generation (local only — needs the SHA-pinned OOS source data)
# ──────────────────────────────────────────────────────────────────────────
def generate() -> int:
    """Re-derive the proof from the real frozen OOS window and write PROOF.

    Local-only: run with the repo root on the path, e.g.
    ``PYTHONPATH=. python tools/verify_rolling_es_strict_replay.py --generate``.
    """
    import numpy as np

    import benchmarks.rolling_es_proximity_oos as bench
    from core.physics.stuart_landau_es import rolling_es_proximity

    art = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    panel, _hashes = bench.load_panel()
    cut = int(len(panel) * bench.TRAIN_FRAC)
    prices = np.ascontiguousarray(panel.iloc[cut:].values, dtype=np.float64)

    es_lenient = rolling_es_proximity(
        prices,
        window=bench.WINDOW,
        K_steps=bench.K_STEPS,
        int_steps=bench.INT_STEPS,
        seed=bench.SEED_ENGINE,
        fail_closed=False,
    )
    failed_windows = 0
    try:
        es_strict = rolling_es_proximity(
            prices,
            window=bench.WINDOW,
            K_steps=bench.K_STEPS,
            int_steps=bench.INT_STEPS,
            seed=bench.SEED_ENGINE,
            fail_closed=True,
        )
    except RuntimeError as exc:  # pragma: no cover - would abort proof
        print(f"FAIL: strict replay raised (a window failed): {exc}", file=sys.stderr)
        return 3

    both_nan = np.isnan(es_lenient) & np.isnan(es_strict)
    bit_identical = bool(
        np.array_equal(np.where(both_nan, 0.0, es_lenient), np.where(both_nan, 0.0, es_strict))
    )
    if not bit_identical:
        print("FAIL: strict != lenient — fail_closed is NOT metric-neutral", file=sys.stderr)
        return 3

    # Reproduce downstream metrics under the current runtime.
    es_s = bench.smooth_box(es_lenient)
    from scipy.signal import find_peaks

    R_s = bench.smooth_box(bench.rolling_R(prices, window=bench.WINDOW))
    valid_R = R_s[~np.isnan(R_s)]
    height = float(np.quantile(valid_R, bench.PEAK_HEIGHT_Q))
    prom = float(np.quantile(valid_R, 0.25) - np.quantile(valid_R, 0.05)) or 1e-3
    peaks_arr, _ = find_peaks(np.where(np.isnan(R_s), -np.inf, R_s), height=height, prominence=prom)
    peaks = np.asarray(peaks_arr, dtype=np.int64)
    taus = bench.compute_taus(es_s, peaks, bench.WINDOW)
    leads_rate = float(np.mean([1 if t >= 1 else 0 for t in taus]))
    p_value, _null = bench.permutation_p_value(
        es_s,
        peaks,
        bench.WINDOW,
        observed_leads_rate=leads_rate,
        n_perm=bench.N_PERM,
        seed=bench.SEED_PERM,
    )
    decision = (
        "ACCEPT"
        if (leads_rate >= bench.LEADS_RATE_THRESHOLD and p_value <= bench.P_VALUE_THRESHOLD)
        else "REJECT"
    )
    current = {
        "decision": decision,
        "leads_rate": leads_rate,
        "n_episodes": len(taus),
        "r_peak_indices": [int(p) for p in peaks],
        "p_value": p_value,
        "taus": taus,
        "tau_mean": float(np.mean(taus)),
        "tau_median": float(np.median(taus)),
    }
    fr_equal = {
        k: (art.get(k) == current[k])
        for k in (*_DECISION_INVARIANT_KEYS, *_MODEL_SENSITIVE_KEYS)
        if k in current
    }

    import platform

    proof = {
        "source_pr": 1425,
        "issue": 1358,
        "benchmark": "benchmarks/rolling_es_proximity_oos.py",
        "artifact": "artifacts/rolling_es_proximity_oos.json",
        "verdict": "STRICT_REPLAY_BOUND",
        "strict_policy": {
            "fail_closed": True,
            "failed_window_count": failed_windows,
            "policy": "raise on fit failure; no NaN masking in evidence mode",
            "reason": "#1358 P1-1 strict evidence path",
        },
        # PROVEN: strict vs lenient under the CURRENT runtime are bit-identical.
        "metric_equality_basis": "strict_vs_lenient_current_runtime",
        "metric_equality": {
            "es_series_bit_identical": bit_identical,
            "failed_window_count_zero": failed_windows == 0,
        },
        # DISCLOSED: how the current runtime reproduces the frozen #536 record.
        "frozen_reproduction": {
            "note": (
                "Frozen numerics were produced by the #536 model (2026-05-06). "
                "Runtime updated post-registration (fitted-state sweep / Hilbert "
                "growth-rate mu; #1208, #1362). fail_closed did NOT move these "
                "numbers; the model update did. decision/leads_rate/n_episodes/"
                "r_peak_indices reproduce exactly; p_value/taus differ. The "
                "pre-registered REJECT verdict is invariant across both models."
            ),
            "decision_committed": art.get("decision"),
            "decision_current_runtime": decision,
            "committed": {
                k: art.get(k) for k in (*_DECISION_INVARIANT_KEYS, *_MODEL_SENSITIVE_KEYS)
            },
            "current_runtime": current,
            "metric_equality": fr_equal,
        },
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
    }
    PROOF.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {PROOF.relative_to(REPO_ROOT)}")
    print(f"  bit_identical={bit_identical} failed_windows={failed_windows}")
    print(f"  frozen_reproduction.metric_equality={fr_equal}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--generate",
        action="store_true",
        help="re-derive the proof from the frozen OOS data (local only; needs source CSVs)",
    )
    args = parser.parse_args(argv)
    return generate() if args.generate else verify()


if __name__ == "__main__":
    raise SystemExit(main())
