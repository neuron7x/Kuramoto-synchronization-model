"""Transfer Entropy between symbols (binned estimator + surrogate null).

Transfer entropy (Schreiber 2000) is the directional information flow from
source Y to target X after conditioning on X's own past:

    TE(Y → X) = I(X_{t+h} ; Y_t | X_t)
              = H(X_{t+h} | X_t) − H(X_{t+h} | X_t, Y_t)

MI is symmetric; TE is not. If TE(Y→X) > TE(X→Y) significantly, Y carries
information about X's future beyond what X's past already provides —
Y leads X.

For the κ_min edge, pairwise TE across the symbol universe tells us
whether the curvature signal is driven by a lead-lag structure. A purely
cross-sectional signal would show near-zero asymmetry.

Estimator:
    Uniform quantile binning (equiprobable bins, n_bins=8 default) to
    normalize marginals. Joint 3-D histogram → plug-in entropy. MI bias
    ≈ (k−1)²/(2·n·ln 2); at n=10⁴, k=8: bias ≈ 5·10⁻³ nats.

Significance:
    Time-shuffled surrogates for Y preserve its marginal but destroy any
    temporal coupling to X. Empirical permutation p = Pr(TE_surrogate ≥
    TE_observed).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

DEFAULT_N_BINS: Final[int] = 8
DEFAULT_LAG_ROWS: Final[int] = 1
DEFAULT_N_SURROGATES: Final[int] = 200


@dataclass(frozen=True)
class TransferEntropyReport:
    te_y_to_x_nats: float
    te_x_to_y_nats: float
    asymmetry_nats: float  # signed: positive → Y→X dominant
    p_value_y_to_x: float  # Pr(surrogate TE ≥ observed)
    p_value_x_to_y: float
    n_bins: int
    lag_rows: int
    n_samples: int
    n_surrogates: int
    verdict: str  # "Y_LEADS_X" | "X_LEADS_Y" | "BIDIRECTIONAL" | "NO_FLOW" | "INCONCLUSIVE"


def _quantile_bin(values: NDArray[np.float64], n_bins: int) -> NDArray[np.int64]:
    """Equiprobable quantile binning; returns integer bin index ∈ [0, n_bins)."""
    ranks = np.argsort(np.argsort(values, kind="stable"), kind="stable")
    # Map ranks ∈ [0, n) → bins ∈ [0, n_bins)
    bins = (ranks * n_bins) // max(1, values.size)
    return np.clip(bins, 0, n_bins - 1).astype(np.int64)


def _transfer_entropy_from_bins(
    x_future: NDArray[np.int64],
    x_past: NDArray[np.int64],
    y_past: NDArray[np.int64],
    n_bins: int,
) -> float:
    """Plug-in TE(Y→X) = H(X_f|X_p) − H(X_f|X_p,Y_p) in nats.

    Uses 3-D joint histogram on the common support (0..n_bins-1)³.
    """
    # Joint (x_f, x_p, y_p)
    idx_fpq = (x_future * n_bins + x_past) * n_bins + y_past
    p_fpq = np.bincount(idx_fpq, minlength=n_bins**3).astype(np.float64)
    p_fpq /= max(1.0, p_fpq.sum())
    p_fpq_3d = p_fpq.reshape(n_bins, n_bins, n_bins)

    p_fp = p_fpq_3d.sum(axis=2)  # marginal over y_past  →  (n_bins, n_bins)
    p_pq = p_fpq_3d.sum(axis=0)  # marginal over x_future →  (n_bins, n_bins)
    p_p = p_pq.sum(axis=1)  # marginal (x_past,)
    # TE = Σ p(f,p,q) · log[ p(f,p,q) · p(p) / (p(f,p) · p(p,q)) ]
    te = 0.0
    for f in range(n_bins):
        for p in range(n_bins):
            for q in range(n_bins):
                joint = p_fpq_3d[f, p, q]
                if joint <= 0.0:
                    continue
                num = joint * p_p[p]
                den = p_fp[f, p] * p_pq[p, q]
                if den <= 0.0:
                    continue
                te += float(joint * np.log(num / den))
    return float(max(te, 0.0))


def transfer_entropy(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    *,
    n_bins: int = DEFAULT_N_BINS,
    lag_rows: int = DEFAULT_LAG_ROWS,
    n_surrogates: int = DEFAULT_N_SURROGATES,
    seed: int = 42,
) -> TransferEntropyReport:
    """Bivariate TE both directions + permutation p-values.

    Returns INCONCLUSIVE if either series has <200 finite samples post-lag.
    """
    if n_bins < 2:
        raise ValueError(f"n_bins must be ≥ 2, got {n_bins}")
    if lag_rows < 1:
        raise ValueError(f"lag_rows must be ≥ 1, got {lag_rows}")
    if n_surrogates < 10:
        raise ValueError(f"n_surrogates must be ≥ 10, got {n_surrogates}")

    xs = np.asarray(x, dtype=np.float64).ravel()
    ys = np.asarray(y, dtype=np.float64).ravel()
    if xs.shape != ys.shape:
        raise ValueError(f"shape mismatch: x={xs.shape} y={ys.shape}")

    mask = np.isfinite(xs) & np.isfinite(ys)
    xs = xs[mask]
    ys = ys[mask]
    n_effective = xs.size - lag_rows
    if n_effective < 200:
        return TransferEntropyReport(
            te_y_to_x_nats=float("nan"),
            te_x_to_y_nats=float("nan"),
            asymmetry_nats=float("nan"),
            p_value_y_to_x=float("nan"),
            p_value_x_to_y=float("nan"),
            n_bins=n_bins,
            lag_rows=lag_rows,
            n_samples=int(xs.size),
            n_surrogates=n_surrogates,
            verdict="INCONCLUSIVE",
        )

    x_bins = _quantile_bin(xs, n_bins)
    y_bins = _quantile_bin(ys, n_bins)

    x_future = x_bins[lag_rows:]
    x_past = x_bins[:-lag_rows]
    y_past = y_bins[:-lag_rows]
    y_future = y_bins[lag_rows:]

    te_yx = _transfer_entropy_from_bins(x_future, x_past, y_past, n_bins)
    te_xy = _transfer_entropy_from_bins(y_future, y_past, x_past, n_bins)

    rng = np.random.default_rng(seed)
    ge_yx = 0
    ge_xy = 0
    for _ in range(n_surrogates):
        perm = rng.permutation(y_past.size)
        te_yx_s = _transfer_entropy_from_bins(x_future, x_past, y_past[perm], n_bins)
        te_xy_s = _transfer_entropy_from_bins(y_future, y_past, x_past[perm], n_bins)
        if te_yx_s >= te_yx:
            ge_yx += 1
        if te_xy_s >= te_xy:
            ge_xy += 1
    p_yx = (1.0 + float(ge_yx)) / (1.0 + float(n_surrogates))
    p_xy = (1.0 + float(ge_xy)) / (1.0 + float(n_surrogates))

    asymmetry = te_yx - te_xy
    sig_yx = p_yx < 0.05
    sig_xy = p_xy < 0.05
    if sig_yx and sig_xy:
        verdict = "BIDIRECTIONAL"
    elif sig_yx and not sig_xy:
        verdict = "Y_LEADS_X"
    elif sig_xy and not sig_yx:
        verdict = "X_LEADS_Y"
    else:
        verdict = "NO_FLOW"

    return TransferEntropyReport(
        te_y_to_x_nats=te_yx,
        te_x_to_y_nats=te_xy,
        asymmetry_nats=float(asymmetry),
        p_value_y_to_x=float(p_yx),
        p_value_x_to_y=float(p_xy),
        n_bins=n_bins,
        lag_rows=lag_rows,
        n_samples=int(xs.size),
        n_surrogates=n_surrogates,
        verdict=verdict,
    )
