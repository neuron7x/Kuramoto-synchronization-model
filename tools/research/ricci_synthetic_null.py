# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Synthetic-null falsifier instrument for ``ricci_microstructure_v1``.

This module proves a *negative control*: on **structureless** synthetic depth-5
order-book noise, the production Ricci/geometric descriptor
(:class:`core.indicators.ricci.MeanRicciFeature`) must NOT manufacture forward
predictive signal that beats a label-permutation null.

It is a *falsifier-adequacy* instrument, not a market-signal claim:

* The synthetic mid-price is a driftless Gaussian random walk → forward
  log-returns are i.i.d. and, by construction, unpredictable from any
  past-derived descriptor. The depth-5 book around it carries only i.i.d. size
  noise, so it injects no exploitable structure.
* The descriptor is the *real shipped* Ricci code path applied to the
  order-book-derived mid-price series.
* Forward returns are sampled on **non-overlapping** horizon blocks so the
  plain label-permutation null is statistically valid (no serial-overlap
  inflation).

Decision law (encoded in :func:`evaluate_synthetic_null`):

    If the descriptor's observed |IC| beats the permutation null on this
    structureless data, the descriptor is hallucinating signal → ``beats_null``
    is True and the falsifier FIRES. A firing falsifier is a real defect signal,
    never to be silenced by tuning the generator. On a sound descriptor the
    observed |IC| sits inside the null band and the control passes.

The instrument only computes and reports; the *policy* (what to assert) lives in
the test that consumes :class:`SyntheticNullResult`.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from core.indicators.ricci import MeanRicciFeature

__all__ = [
    "OrderBookNoise",
    "SyntheticNullConfig",
    "SyntheticNullResult",
    "generate_structureless_depth5_book",
    "ricci_descriptor_series",
    "permutation_null_decision",
    "evaluate_synthetic_null",
]


@dataclass(frozen=True)
class OrderBookNoise:
    """A deterministic, structureless synthetic depth-5 order-book tape.

    Attributes:
        mid: Mid-price series of length ``n`` (driftless random walk → martingale).
        bid: ``(n, 5)`` bid-level prices, best bid first.
        ask: ``(n, 5)`` ask-level prices, best ask first.
        bid_size: ``(n, 5)`` i.i.d. positive bid sizes (pure noise).
        ask_size: ``(n, 5)`` i.i.d. positive ask sizes (pure noise).
    """

    mid: np.ndarray
    bid: np.ndarray
    ask: np.ndarray
    bid_size: np.ndarray
    ask_size: np.ndarray


@dataclass(frozen=True)
class SyntheticNullConfig:
    """Pre-registered, frozen configuration for the synthetic-null control."""

    seed: int = 20260615
    n_ticks: int = 6000
    window: int = 64
    horizon: int = 16
    delta: float = 0.0005
    tick: float = 0.05
    n_permutations: int = 2000
    base_price: float = 100.0
    log_return_sigma: float = 8.0e-4
    null_band_pct: float = 95.0
    alpha: float = 0.05


@dataclass(frozen=True)
class SyntheticNullResult:
    """Outcome of the synthetic-null evaluation (instrument output only)."""

    observed_ic: float
    null_abs_ic_band: float
    p_value: float
    beats_null: bool
    n_samples: int
    n_permutations: int
    seed: int


def generate_structureless_depth5_book(cfg: SyntheticNullConfig) -> OrderBookNoise:
    """Generate a deterministic, structureless depth-5 order-book tape.

    The mid-price is a driftless Gaussian random walk on log-price (a martingale),
    so its forward returns are i.i.d. and carry no exploitable temporal structure.
    Five bid/ask levels are placed at fixed tick spacing around the mid with
    i.i.d. positive sizes — noise that adds no predictive content.

    Args:
        cfg: Frozen configuration (the ``seed`` makes this fully reproducible).

    Returns:
        OrderBookNoise: The synthetic tape.
    """
    rng = np.random.default_rng(cfg.seed)
    log_returns = rng.normal(0.0, cfg.log_return_sigma, size=cfg.n_ticks)
    mid = cfg.base_price * np.exp(np.cumsum(log_returns))

    levels = np.arange(1, 6, dtype=float)  # depth-5
    # Best bid/ask straddle the mid by half a tick; deeper levels step by `tick`.
    bid = mid[:, None] - (0.5 * cfg.tick + (levels[None, :] - 1.0) * cfg.tick)
    ask = mid[:, None] + (0.5 * cfg.tick + (levels[None, :] - 1.0) * cfg.tick)

    bid_size = rng.lognormal(mean=0.0, sigma=1.0, size=(cfg.n_ticks, 5))
    ask_size = rng.lognormal(mean=0.0, sigma=1.0, size=(cfg.n_ticks, 5))

    return OrderBookNoise(mid=mid, bid=bid, ask=ask, bid_size=bid_size, ask_size=ask_size)


def ricci_descriptor_series(mid: np.ndarray, cfg: SyntheticNullConfig) -> np.ndarray:
    """Roll the production Ricci descriptor over the mid-price series.

    For each tick ``t`` (with a full trailing window) the descriptor value is the
    mean Ollivier–Ricci curvature of the price graph built from the trailing
    ``window`` mids — exactly the shipped :class:`MeanRicciFeature` code path.

    Args:
        mid: Mid-price series (order-book derived).
        cfg: Frozen configuration.

    Returns:
        np.ndarray: Curvature value per tick; the first ``window - 1`` entries are
        NaN (insufficient trailing data).
    """
    feature = MeanRicciFeature(delta=cfg.delta)
    out = np.full(mid.shape[0], np.nan, dtype=float)
    for t in range(cfg.window - 1, mid.shape[0]):
        window = mid[t - cfg.window + 1 : t + 1]
        out[t] = feature.transform(window).value
    return out


def _non_overlapping_pairs(
    signal: np.ndarray, mid: np.ndarray, cfg: SyntheticNullConfig
) -> tuple[np.ndarray, np.ndarray]:
    """Pair descriptor values with forward returns on non-overlapping blocks.

    Sampling at a stride of ``horizon`` makes consecutive forward log-returns
    disjoint, so they are (under the i.i.d. martingale) mutually independent and
    the plain label-permutation null is valid.
    """
    first = cfg.window - 1
    last = mid.shape[0] - cfg.horizon - 1
    idx = np.arange(first, last + 1, cfg.horizon)
    sig = signal[idx]
    fwd = np.log(mid[idx + cfg.horizon]) - np.log(mid[idx])
    finite = np.isfinite(sig) & np.isfinite(fwd)
    return sig[finite], fwd[finite]


def _abs_spearman(x: np.ndarray, y: np.ndarray) -> float:
    rho = spearmanr(x, y).statistic
    return 0.0 if not np.isfinite(rho) else abs(float(rho))


def permutation_null_decision(
    sig: np.ndarray, fwd: np.ndarray, cfg: SyntheticNullConfig
) -> SyntheticNullResult:
    """Decide whether ``sig``'s |IC| beats a seeded label-permutation null.

    Pure statistical core shared by the end-to-end control and by adequacy
    ("teeth") tests that inject a planted signal to prove the falsifier can fire.

    Args:
        sig: Descriptor values.
        fwd: Forward returns paired 1:1 with ``sig``.
        cfg: Frozen configuration (seed, permutation count, band, alpha).

    Returns:
        SyntheticNullResult: Observed |IC|, null band, p-value and ``beats_null``.
    """
    if sig.size < 8 or sig.size != fwd.size:
        raise ValueError(f"need >=8 aligned samples, got sig={sig.size} fwd={fwd.size}")

    observed = _abs_spearman(sig, fwd)

    rng = np.random.default_rng(cfg.seed + 1)
    null = np.empty(cfg.n_permutations, dtype=float)
    for i in range(cfg.n_permutations):
        null[i] = _abs_spearman(sig, rng.permutation(fwd))

    band = float(np.percentile(null, cfg.null_band_pct))
    # +1 smoothing keeps the p-value strictly positive (Monte-Carlo convention).
    p_value = float((np.count_nonzero(null >= observed) + 1) / (cfg.n_permutations + 1))
    beats_null = bool(observed > band and p_value < cfg.alpha)

    return SyntheticNullResult(
        observed_ic=observed,
        null_abs_ic_band=band,
        p_value=p_value,
        beats_null=beats_null,
        n_samples=int(sig.size),
        n_permutations=cfg.n_permutations,
        seed=cfg.seed,
    )


def evaluate_synthetic_null(cfg: SyntheticNullConfig | None = None) -> SyntheticNullResult:
    """Run the full deterministic synthetic-null control.

    Builds the structureless book, rolls the Ricci descriptor, computes the
    observed information coefficient (|Spearman IC| of descriptor vs. forward
    return), and compares it against a seeded label-permutation null.

    Args:
        cfg: Optional configuration; defaults to the frozen pre-registered config.

    Returns:
        SyntheticNullResult: Observed IC, null band, permutation p-value, and the
        ``beats_null`` falsifier flag.
    """
    cfg = cfg or SyntheticNullConfig()
    book = generate_structureless_depth5_book(cfg)
    signal = ricci_descriptor_series(book.mid, cfg)
    sig, fwd = _non_overlapping_pairs(signal, book.mid, cfg)
    return permutation_null_decision(sig, fwd, cfg)


def main(argv: list[str] | None = None) -> int:
    """Run the control and emit a deterministic JSON evidence artifact.

    Exit code mirrors the falsifier: ``0`` when the descriptor stays inside the
    null band (control passes), ``1`` when it beats the null (falsifier fires).
    """
    argv = sys.argv[1:] if argv is None else argv
    out_path = Path(
        argv[0] if argv else "artifacts/runs/ricci_microstructure_v1/synthetic_null_falsifier.json"
    )
    result = evaluate_synthetic_null()
    payload = {
        "line_id": "ricci_microstructure_v1",
        "kind": "synthetic_null_falsifier",
        "status": "INSTRUMENTED",
        "claim": "Ricci descriptor does not beat permutation null on structureless depth-5 noise.",
        "result": dataclasses.asdict(result),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload["result"], indent=2, sort_keys=True))
    return 1 if result.beats_null else 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
