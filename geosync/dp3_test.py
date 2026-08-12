# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""FIX-3: honest DP3 (snapshot-staleness) recovery test.

The earlier informal claim was: "manual tick refreshed paper-state →
Sharpe rose from −6.82 → −4.68; therefore DP3 staleness explains 31 %
of the deficit." That claim conflates a *causal* recovery with a
*mechanical* small-n effect: at n=14 returns, simply appending one
positive bar moves the annualised Sharpe by O(1/sqrt(N)) ≈ 1.0–2.0
SD-units regardless of whether the new bar carries any signal about
staleness. n=1 datapoint, confounded.

This module replaces the informal claim with a registered protocol:

    H0  observed ΔSharpe between bar N−1 and bar N is
        indistinguishable from the mechanical small-n distribution
        produced by appending a random draw from the prior return
        distribution.
    H1  observed |ΔSharpe| > 2 × SE_of_mechanical_distribution.

If H0 is not rejected → label REJECT (no DP3 effect detectable beyond
mechanics). If observed exceeds the band, emit CONFIRMED with the
two-sided permutation p-value over the mechanical null.

Pre-registered thresholds:
    band  = 2 × std(mechanical_distribution)
    p     = mean(|mech_delta| >= |observed_delta|)
    label = REJECT if |observed_delta| < band, else CONFIRMED

The output is BINARY by design (REJECT / CONFIRMED) with explicit
p-value. ``ambiguous`` / ``promising`` / ``partial`` are forbidden —
the test answers a yes/no question.

Falsification gate (FIX-3): on a synthetic series whose final bar is
exactly the prior-mean (zero novel signal), the test MUST give
REJECT. The test in tests/scripts/test_dp3_test.py asserts this.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.typing import NDArray

REPO = Path(__file__).resolve().parents[1]
PAPER_EQUITY = Path.home() / "spikes" / "cross_asset_sync_regime" / "paper_state" / "equity.csv"

BARS_PER_YEAR: float = 252.0
DEFAULT_N_PERM: int = 999
DEFAULT_SEED: int = 20260506
BAND_K: float = 2.0  # 2 × std-of-mechanical-null


@dataclass(frozen=True, slots=True)
class DP3Result:
    bar: int
    sharpe_full: float
    sharpe_prior: float
    delta_observed: float
    band: float
    p_value: float
    label: str
    n_returns: int


def _load_returns_up_to_bar(bar: int, equity_path: Path = PAPER_EQUITY) -> NDArray[np.float64]:
    """Same canonical loader used by geosync.verdict — derive log-rets from equity."""
    if not equity_path.is_file():
        raise FileNotFoundError(
            f"paper-state ledger not found at {equity_path}. "
            f"Run paper_trader.py --tick to populate."
        )
    df = pd.read_csv(equity_path, parse_dates=["date"])
    for col in ("equity", "day_n", "date"):
        if col not in df.columns:
            raise ValueError(
                f"paper-state {equity_path} missing required {col!r} column. "
                f"Got columns: {list(df.columns)}."
            )
    df = df.sort_values(["date", "day_n"]).drop_duplicates("date", keep="last")
    df = df.reset_index(drop=True)
    if bar < 2:
        raise ValueError(f"DP3 test requires bar >= 2 (need >=1 prior return); got {bar}")
    if bar > len(df):
        raise ValueError(f"bar {bar} exceeds available live bars ({len(df)} unique dates)")
    equity = df["equity"].to_numpy(dtype=np.float64)[:bar]
    log_rets = np.diff(np.log(np.maximum(equity, 1e-12)))
    return log_rets[np.isfinite(log_rets)]


def _sharpe_annualised(returns: NDArray[np.float64]) -> float:
    if returns.size < 2:
        return float("nan")
    mu = float(returns.mean()) * BARS_PER_YEAR
    sd = float(returns.std(ddof=1)) * float(np.sqrt(BARS_PER_YEAR))
    if sd <= 0.0 or not np.isfinite(sd):
        return float("nan")
    return mu / sd


def evaluate(
    bar: int,
    *,
    equity_path: Path = PAPER_EQUITY,
    n_perm: int = DEFAULT_N_PERM,
    seed: int = DEFAULT_SEED,
) -> DP3Result:
    full = _load_returns_up_to_bar(bar, equity_path=equity_path)
    if full.size < 3:
        raise ValueError(
            f"DP3 test requires >= 3 returns; got {full.size} from "
            f"bar={bar}. Wait for more ticks before running this test."
        )
    prior = full[:-1]
    sharpe_full = _sharpe_annualised(full)
    sharpe_prior = _sharpe_annualised(prior)
    delta_observed = sharpe_full - sharpe_prior

    rng = np.random.default_rng(seed)
    mech_deltas = np.empty(n_perm, dtype=np.float64)
    for i in range(n_perm):
        synthetic_bar = float(rng.choice(prior))
        synthetic_full = np.concatenate([prior, np.array([synthetic_bar])])
        mech_deltas[i] = _sharpe_annualised(synthetic_full) - sharpe_prior

    finite = mech_deltas[np.isfinite(mech_deltas)]
    if finite.size == 0:
        raise ValueError("Mechanical null produced no finite deltas; cannot test.")
    band = float(BAND_K * np.std(finite, ddof=1))
    p_value = float(np.mean(np.abs(finite) >= abs(delta_observed)))
    if not np.isfinite(delta_observed) or not np.isfinite(band):
        raise ValueError(f"Non-finite delta or band: delta={delta_observed}, band={band}")
    label = "REJECT" if abs(delta_observed) < band else "CONFIRMED"

    return DP3Result(
        bar=bar,
        sharpe_full=sharpe_full,
        sharpe_prior=sharpe_prior,
        delta_observed=delta_observed,
        band=band,
        p_value=p_value,
        label=label,
        n_returns=int(full.size),
    )


def _format(r: DP3Result) -> str:
    return (
        f"DP3 BAR {r.bar} | "
        f"Sharpe(N-1)={r.sharpe_prior:+.4f} → "
        f"Sharpe(N)={r.sharpe_full:+.4f} | "
        f"Δ={r.delta_observed:+.4f} | "
        f"band(2σ)={r.band:.4f} | "
        f"p={r.p_value:.4f} | "
        f"LABEL {r.label} | "
        f"n_returns={r.n_returns}"
    )


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Honest DP3 (snapshot-staleness) recovery test: compares "
            "observed bar-N→N+1 ΔSharpe against the mechanical small-n "
            "null. Emits REJECT or CONFIRMED."
        ),
    )
    ap.add_argument(
        "--honest",
        action="store_true",
        help=(
            "Required flag. Ensures callers acknowledge that this test "
            "replaces the earlier informal '31 %% recovery' claim."
        ),
    )
    ap.add_argument(
        "--bar",
        type=int,
        default=None,
        help=("Live bar number to test at. Defaults to the latest available bar in paper-state."),
    )
    ap.add_argument(
        "--equity-path",
        type=Path,
        default=PAPER_EQUITY,
        help="Override paper-state equity.csv path.",
    )
    ap.add_argument("--n-perm", type=int, default=DEFAULT_N_PERM, help="Permutations.")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help="RNG seed.")
    ap.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of human-readable line.",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    if not args.honest:
        ap.error(
            "DP3 test requires --honest flag (acknowledges this replaces "
            "the earlier informal '31 %% recovery' claim)."
        )

    bar = args.bar
    if bar is None:
        df = pd.read_csv(args.equity_path, parse_dates=["date"])
        bar = df.sort_values(["date", "day_n"]).drop_duplicates("date", keep="last").shape[0]

    r = evaluate(
        bar,
        equity_path=args.equity_path,
        n_perm=args.n_perm,
        seed=args.seed,
    )
    if args.json:
        payload = {
            "bar": r.bar,
            "sharpe_full": r.sharpe_full,
            "sharpe_prior": r.sharpe_prior,
            "delta_observed": r.delta_observed,
            "band": r.band,
            "p_value": r.p_value,
            "label": r.label,
            "n_returns": r.n_returns,
        }
        print(json.dumps(payload, sort_keys=True))
    else:
        print(_format(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
