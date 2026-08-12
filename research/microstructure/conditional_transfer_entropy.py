"""Conditional Transfer Entropy with common-factor conditioning.

The unconditional pairwise TE verdict (45/45 BIDIRECTIONAL) cannot
distinguish between two hypotheses:

    H_A:  Each symbol pair (A, B) genuinely exchanges private information
          at 1-second lag.
    H_B:  Every symbol follows a common market-wide factor Z (e.g. BTC
          price, aggregate OFI, macro drift). Pairwise TE reflects common
          response to Z, not A↔B coupling.

Conditional Transfer Entropy (Schreiber 2000 §IV; Wibral et al. 2014)
tests H_A against H_B by removing information that is redundantly
explained by the conditioning factor Z_t:

    TE(Y → X | Z) = H(X_{t+h} | X_t, Z_t) − H(X_{t+h} | X_t, Y_t, Z_t)
                  = I(X_{t+h} ; Y_t | X_t, Z_t)

If TE_unconditional is large but TE_conditional collapses to ≈ 0,
the pairwise flow was a common-factor artifact. If TE_conditional
stays significant, there is genuine pairwise-private coupling.

Estimator:
    4-D joint histogram on quantile-binned (x_future, x_past, y_past,
    z_past). Plug-in entropy from marginals. Bias O((k−1)³/n ln 2) —
    at k=6, n=10⁴: bias ≈ 0.018 nats.

Null:
    Time-shuffled Y_past preserves Y's own marginal and Y↔Z coupling;
    destroys any Y→X path that survives Z-conditioning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

DEFAULT_N_BINS: Final[int] = 6
DEFAULT_LAG_ROWS: Final[int] = 1
DEFAULT_N_SURROGATES: Final[int] = 100


@dataclass(frozen=True)
class ConditionalTEReport:
    te_unconditional_y_to_x_nats: float
    te_conditional_y_to_x_nats: float
    reduction_nats: float  # TE_uncond − TE_cond
    reduction_fraction: float  # (TE_uncond − TE_cond) / TE_uncond
    p_value_conditional: float
    n_bins: int
    lag_rows: int
    n_samples: int
    n_surrogates: int
    verdict: str  # "PRIVATE_FLOW" | "COMMON_FACTOR" | "PARTIAL" | "NO_FLOW" | "INCONCLUSIVE"


def _quantile_bin(values: NDArray[np.float64], n_bins: int) -> NDArray[np.int64]:
    """Equiprobable quantile binning; returns integer bin index ∈ [0, n_bins)."""
    ranks = np.argsort(np.argsort(values, kind="stable"), kind="stable")
    bins = (ranks * n_bins) // max(1, values.size)
    return np.clip(bins, 0, n_bins - 1).astype(np.int64)


def _conditional_mi_4d(
    x_future: NDArray[np.int64],
    x_past: NDArray[np.int64],
    y_past: NDArray[np.int64],
    z_past: NDArray[np.int64],
    n_bins: int,
) -> float:
    """I(X_f ; Y_p | X_p, Z_p) in nats via 4-D joint histogram plug-in.

    CMI = Σ p(f,p,q,r) · log[ p(f,p,q,r) · p(p,r) / (p(f,p,r) · p(p,q,r)) ]
    """
    k = n_bins
    idx = ((x_future * k + x_past) * k + y_past) * k + z_past
    p_joint = np.bincount(idx, minlength=k**4).astype(np.float64)
    total = max(1.0, p_joint.sum())
    p_joint /= total
    p4 = p_joint.reshape(k, k, k, k)  # (x_f, x_p, y_p, z_p)

    p_fpz = p4.sum(axis=2)  # (f, p, z)  — marginal over y_past
    p_pqz = p4.sum(axis=0)  # (p, q, z)  — marginal over x_future
    p_pz = p_pqz.sum(axis=1)  # (p, z)

    cmi = 0.0
    for f in range(k):
        for p in range(k):
            for q in range(k):
                for r in range(k):
                    joint = p4[f, p, q, r]
                    if joint <= 0.0:
                        continue
                    num = joint * p_pz[p, r]
                    den = p_fpz[f, p, r] * p_pqz[p, q, r]
                    if den <= 0.0:
                        continue
                    cmi += float(joint * np.log(num / den))
    return float(max(cmi, 0.0))


def _unconditional_te_3d(
    x_future: NDArray[np.int64],
    x_past: NDArray[np.int64],
    y_past: NDArray[np.int64],
    n_bins: int,
) -> float:
    k = n_bins
    idx = (x_future * k + x_past) * k + y_past
    p_joint = np.bincount(idx, minlength=k**3).astype(np.float64)
    p_joint /= max(1.0, p_joint.sum())
    p3 = p_joint.reshape(k, k, k)
    p_fp = p3.sum(axis=2)
    p_pq = p3.sum(axis=0)
    p_p = p_pq.sum(axis=1)
    te = 0.0
    for f in range(k):
        for p in range(k):
            for q in range(k):
                joint = p3[f, p, q]
                if joint <= 0.0:
                    continue
                num = joint * p_p[p]
                den = p_fp[f, p] * p_pq[p, q]
                if den <= 0.0:
                    continue
                te += float(joint * np.log(num / den))
    return float(max(te, 0.0))


def conditional_transfer_entropy(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    z: NDArray[np.float64],
    *,
    n_bins: int = DEFAULT_N_BINS,
    lag_rows: int = DEFAULT_LAG_ROWS,
    n_surrogates: int = DEFAULT_N_SURROGATES,
    seed: int = 42,
) -> ConditionalTEReport:
    """TE(Y→X | Z) conditioned on common factor Z, with surrogate p-value."""
    if n_bins < 2:
        raise ValueError(f"n_bins must be ≥ 2, got {n_bins}")
    if lag_rows < 1:
        raise ValueError(f"lag_rows must be ≥ 1, got {lag_rows}")
    if n_surrogates < 10:
        raise ValueError(f"n_surrogates must be ≥ 10, got {n_surrogates}")

    xs = np.asarray(x, dtype=np.float64).ravel()
    ys = np.asarray(y, dtype=np.float64).ravel()
    zs = np.asarray(z, dtype=np.float64).ravel()
    if not (xs.shape == ys.shape == zs.shape):
        raise ValueError(f"shape mismatch: x={xs.shape} y={ys.shape} z={zs.shape}")

    mask = np.isfinite(xs) & np.isfinite(ys) & np.isfinite(zs)
    xs = xs[mask]
    ys = ys[mask]
    zs = zs[mask]
    n_effective = xs.size - lag_rows
    if n_effective < 500:
        return ConditionalTEReport(
            te_unconditional_y_to_x_nats=float("nan"),
            te_conditional_y_to_x_nats=float("nan"),
            reduction_nats=float("nan"),
            reduction_fraction=float("nan"),
            p_value_conditional=float("nan"),
            n_bins=n_bins,
            lag_rows=lag_rows,
            n_samples=int(xs.size),
            n_surrogates=n_surrogates,
            verdict="INCONCLUSIVE",
        )

    x_bins = _quantile_bin(xs, n_bins)
    y_bins = _quantile_bin(ys, n_bins)
    z_bins = _quantile_bin(zs, n_bins)

    x_future = x_bins[lag_rows:]
    x_past = x_bins[:-lag_rows]
    y_past = y_bins[:-lag_rows]
    z_past = z_bins[:-lag_rows]

    te_uncond = _unconditional_te_3d(x_future, x_past, y_past, n_bins)
    te_cond = _conditional_mi_4d(x_future, x_past, y_past, z_past, n_bins)

    rng = np.random.default_rng(seed)
    ge_cond = 0
    for _ in range(n_surrogates):
        perm = rng.permutation(y_past.size)
        te_cond_s = _conditional_mi_4d(x_future, x_past, y_past[perm], z_past, n_bins)
        if te_cond_s >= te_cond:
            ge_cond += 1
    p_cond = (1.0 + float(ge_cond)) / (1.0 + float(n_surrogates))

    reduction = te_uncond - te_cond
    reduction_frac = reduction / te_uncond if te_uncond > 0.0 else float("nan")

    sig_cond = p_cond < 0.05
    # Verdict taxonomy:
    #   - COMMON_FACTOR: unconditional was significant but conditional collapses
    #   - PRIVATE_FLOW: conditional still significant after Z-conditioning
    #   - PARTIAL: both present but large reduction
    #   - NO_FLOW: neither significant
    if te_uncond < 1e-4 and te_cond < 1e-4:
        verdict = "NO_FLOW"
    elif sig_cond and np.isfinite(reduction_frac) and reduction_frac < 0.30:
        verdict = "PRIVATE_FLOW"
    elif sig_cond and np.isfinite(reduction_frac) and reduction_frac >= 0.30:
        verdict = "PARTIAL"
    else:
        verdict = "COMMON_FACTOR"

    return ConditionalTEReport(
        te_unconditional_y_to_x_nats=te_uncond,
        te_conditional_y_to_x_nats=te_cond,
        reduction_nats=float(reduction),
        reduction_fraction=float(reduction_frac) if np.isfinite(reduction_frac) else float("nan"),
        p_value_conditional=float(p_cond),
        n_bins=n_bins,
        lag_rows=lag_rows,
        n_samples=int(xs.size),
        n_surrogates=n_surrogates,
        verdict=verdict,
    )
