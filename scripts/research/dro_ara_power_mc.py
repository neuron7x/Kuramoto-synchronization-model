#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Monte Carlo power / confusion matrix for the DRO-ARA v7 regime classifier.

For each known generator (OU, GBM-drift, random walk, white noise, AR(1) at
φ∈{0.2, 0.8}) we draw N seeded samples, classify them with ``geosync_observe``,
and summarise the predicted-regime frequencies into a confusion matrix.

Per-generator headline metric: P(CRITICAL | generator) — the operating
characteristic that matters for long-only mean-reversion entries. Bootstrap
1000× on each rate gives a 95% CI.

Contract:
    seed = 42
    n_boot = 1000
    window = 512, step = 64
    truncated replay_hash (16 hex chars) over sort_keys JSON minus timestamp
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from core.dro_ara import Regime, geosync_observe

SEED: int = 42
N_BOOT: int = 1000
WINDOW: int = 512
STEP: int = 64
REGIME_ORDER: tuple[str, ...] = tuple(r.value for r in Regime)


def _ou(
    seed: int, n: int, mu: float = 100.0, theta: float = 0.08, sigma: float = 0.6
) -> NDArray[np.float64]:
    rng = np.random.default_rng(seed)
    x = np.empty(n, dtype=np.float64)
    x[0] = mu
    for t in range(1, n):
        x[t] = x[t - 1] + theta * (mu - x[t - 1]) + sigma * rng.normal()
    return x


def _gbm_drift(seed: int, n: int, mu: float = 0.002, sigma: float = 0.01) -> NDArray[np.float64]:
    rng = np.random.default_rng(seed)
    r = mu + sigma * rng.normal(size=n)
    return 100.0 * np.exp(np.cumsum(r))


def _random_walk(seed: int, n: int, sigma: float = 0.01) -> NDArray[np.float64]:
    rng = np.random.default_rng(seed)
    r = rng.normal(0, sigma, size=n)
    return 100.0 * np.exp(np.cumsum(r))


def _white_noise(seed: int, n: int, mu: float = 100.0, sigma: float = 1.0) -> NDArray[np.float64]:
    rng = np.random.default_rng(seed)
    return mu + sigma * rng.normal(size=n)


def _ar1(seed: int, n: int, phi: float, sigma: float = 0.5) -> NDArray[np.float64]:
    rng = np.random.default_rng(seed)
    x = np.empty(n, dtype=np.float64)
    x[0] = 100.0
    for t in range(1, n):
        x[t] = phi * x[t - 1] + (1 - phi) * 100.0 + sigma * rng.normal()
    return x


GENERATORS: dict[str, Any] = {
    "ou": _ou,
    "gbm_drift": _gbm_drift,
    "random_walk": _random_walk,
    "white_noise": _white_noise,
    "ar1_phi02": lambda s, n: _ar1(s, n, phi=0.2),
    "ar1_phi08": lambda s, n: _ar1(s, n, phi=0.8),
}


def _bootstrap_rate(hits: NDArray[np.bool_], n_boot: int, seed: int) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    n = len(hits)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    boots = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boots[i] = hits[idx].mean()
    return (
        float(np.median(boots)),
        float(np.percentile(boots, 2.5)),
        float(np.percentile(boots, 97.5)),
    )


def run_mc(
    n_samples: int,
    length: int,
    window: int,
    step: int,
    seed: int,
) -> dict[str, Any]:
    confusion: dict[str, dict[str, int]] = {g: {r: 0 for r in REGIME_ORDER} for g in GENERATORS}
    critical_hits: dict[str, list[bool]] = {g: [] for g in GENERATORS}
    failures: dict[str, int] = {g: 0 for g in GENERATORS}

    for gen_name, gen in GENERATORS.items():
        for k in range(n_samples):
            sample_seed = seed + 1000 * hash(gen_name) % 10_000 + k
            series = gen(sample_seed, length)
            try:
                out = geosync_observe(series, window=window, step=step)
            except ValueError:
                failures[gen_name] += 1
                continue
            regime = str(out["regime"])
            confusion[gen_name][regime] = confusion[gen_name].get(regime, 0) + 1
            critical_hits[gen_name].append(regime == Regime.CRITICAL.value)

    rates: dict[str, dict[str, Any]] = {}
    for gen_name, hits in critical_hits.items():
        arr = np.asarray(hits, dtype=bool)
        med, lo, hi = _bootstrap_rate(arr, N_BOOT, seed=seed)
        total = int(arr.sum())
        n_eff = int(len(arr))
        rates[gen_name] = {
            "n_effective": n_eff,
            "n_failures": failures[gen_name],
            "n_critical": total,
            "p_critical_boot_median": med,
            "p_critical_ci95_low": lo,
            "p_critical_ci95_high": hi,
        }

    return {
        "confusion_matrix": confusion,
        "p_critical": rates,
        "regime_order": list(REGIME_ORDER),
        "generators": list(GENERATORS.keys()),
    }


def build_verdict(mc: dict[str, Any]) -> tuple[str, str]:
    rates = mc["p_critical"]
    ou_rate = rates.get("ou", {}).get("p_critical_boot_median", float("nan"))
    gbm_rate = rates.get("gbm_drift", {}).get("p_critical_boot_median", float("nan"))
    verdict = "PASS"
    notes: list[str] = []
    if not (np.isfinite(ou_rate) and ou_rate >= 0.40):
        verdict = "FAIL"
        notes.append(f"OU→CRITICAL rate {ou_rate:.3f} < 0.40")
    if not (np.isfinite(gbm_rate) and gbm_rate <= 0.20):
        verdict = "FAIL"
        notes.append(f"GBM_drift→CRITICAL rate {gbm_rate:.3f} > 0.20")
    reason = (
        "; ".join(notes) if notes else f"OU→CRITICAL={ou_rate:.3f}, GBM→CRITICAL={gbm_rate:.3f}"
    )
    return verdict, reason


def _replay_hash_short(payload: dict[str, Any]) -> str:
    clean = {k: v for k, v in payload.items() if k not in {"timestamp_utc", "replay_hash_short"}}
    full = hashlib.sha256(json.dumps(clean, sort_keys=True, default=str).encode()).hexdigest()
    return full[:16]


def run(
    n_samples: int,
    length: int,
    window: int,
    step: int,
    seed: int,
    out_path: Path,
) -> dict[str, Any]:
    np.random.seed(seed)
    mc = run_mc(n_samples=n_samples, length=length, window=window, step=step, seed=seed)
    verdict, reason = build_verdict(mc)
    payload: dict[str, Any] = {
        "spike_name": "dro_ara_power_mc",
        "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
        "seed": seed,
        "n_boot": N_BOOT,
        "n_samples": n_samples,
        "length": length,
        "window": window,
        "step": step,
        "measurement": mc,
        "verdict": verdict,
        "reason": reason,
    }
    payload["replay_hash_short"] = _replay_hash_short(payload)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    return payload


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n-samples", type=int, default=500)
    p.add_argument("--length", type=int, default=2048)
    p.add_argument("--window", type=int, default=WINDOW)
    p.add_argument("--step", type=int, default=STEP)
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--out", type=Path, default=Path("results/dro_ara_power_mc.json"))
    args = p.parse_args()

    try:
        payload = run(
            n_samples=args.n_samples,
            length=args.length,
            window=args.window,
            step=args.step,
            seed=args.seed,
            out_path=args.out,
        )
    except Exception as exc:
        err = {
            "spike_name": "dro_ara_power_mc",
            "verdict": "ABORT",
            "error": f"{type(exc).__name__}: {exc}",
            "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(err, indent=2, default=str))
        print(f"[dro-ara-power] ABORT: {exc}", file=sys.stderr)
        return 1

    print(f"[dro-ara-power] verdict={payload['verdict']}")
    print(f"[dro-ara-power] {payload['reason']}")
    for gen, r in payload["measurement"]["p_critical"].items():
        print(
            f"[dro-ara-power] {gen:14s} n={r['n_effective']:4d} "
            f"P(CRIT)={r['p_critical_boot_median']:.3f} "
            f"[{r['p_critical_ci95_low']:.3f}, {r['p_critical_ci95_high']:.3f}]"
        )
    print(f"[dro-ara-power] wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
