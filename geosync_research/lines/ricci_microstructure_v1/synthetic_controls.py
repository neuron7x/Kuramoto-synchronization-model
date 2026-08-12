"""Null baselines and falsification statistics for Ricci microstructure."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .graph_builder import build_l2_graph
from .ricci_kernel import RicciKernelConfig, compute_ricci_curvature, edge_curvature_records

# Each null destroys a specific hypothesised signal pathway (documented in
# surrogate_frame). `iaaft` is the DEFAULT primary null — it perturbs the per-
# level sizes the kernel actually consumes. `shuffled_timestamps` is retained for
# completeness but is weak for a mean-curvature statistic (row reorder leaves the
# mean invariant) and must not be the default.
NULL_MODELS = {
    "iaaft",
    "shuffled_timestamps",
    "random_walk",
    "volume_neutral",
    "size_permutation_within_side",
    "block_bootstrap",
}


@dataclass(frozen=True)
class StatisticalGate:
    p_threshold: float = 0.01
    cliffs_delta_threshold: float = 0.147


def curvature_series(
    frame: pd.DataFrame, *, depth: int, alpha: float, n_min_edges: int
) -> np.ndarray:
    values: list[float] = []
    for _, row in frame.iterrows():
        graph = build_l2_graph(row, depth=depth)
        curved = compute_ricci_curvature(
            graph, config=RicciKernelConfig(alpha=alpha, n_min_edges=n_min_edges)
        )
        records = edge_curvature_records(curved)
        values.append(float(np.mean([record["ricciCurvature"] for record in records])))
    if not values:
        raise RuntimeError("empty curvature output")
    return np.array(values, dtype=float)


def iaaft_surrogate(
    series: np.ndarray, rng: np.random.Generator, iterations: int = 20
) -> np.ndarray:
    target_sorted = np.sort(series)
    amplitudes = np.abs(np.fft.rfft(series))
    surrogate = rng.permutation(series)
    for _ in range(iterations):
        phases = np.angle(np.fft.rfft(surrogate))
        surrogate = np.fft.irfft(amplitudes * np.exp(1j * phases), n=len(series))
        ranks = np.argsort(np.argsort(surrogate))
        surrogate = target_sorted[ranks]
    return surrogate.astype(float)


def _size_columns(frame: pd.DataFrame, depth: int) -> list[str]:
    return [f"{side}_sz_{idx}" for idx in range(1, depth + 1) for side in ("bid", "ask")]


def surrogate_frame(
    frame: pd.DataFrame, *, depth: int, null_model: str, rng: np.random.Generator
) -> pd.DataFrame:
    if null_model not in NULL_MODELS:
        raise ValueError(f"unsupported null_model_type: {null_model}")
    out = frame.copy(deep=True)
    if null_model == "shuffled_timestamps":
        shuffled = out["timestamp"].to_numpy(copy=True)
        rng.shuffle(shuffled)
        out["timestamp"] = shuffled
        return out.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    if null_model == "random_walk":
        steps = rng.normal(0.0, float(out["price"].diff().dropna().std() or 1.0), size=len(out))
        out["price"] = float(out["price"].iloc[0]) + np.cumsum(steps)
        return out
    if null_model == "size_permutation_within_side":
        # Destroys: the level-ordering of depth. Per row, permute sizes ACROSS
        # levels within each side (preserving total side volume + the price
        # ladder). Kills the hypothesis that the specific depth-by-level size
        # arrangement — not just gross imbalance — drives curvature.
        for side in ("bid", "ask"):
            cols = [f"{side}_sz_{idx}" for idx in range(1, depth + 1)]
            # .to_numpy() may return a read-only view under newer pandas/numpy;
            # copy() guarantees a writable buffer for the in-place permutation.
            block = out[cols].to_numpy(dtype=float).copy()
            for r in range(block.shape[0]):
                block[r] = block[r][rng.permutation(block.shape[1])]
            out.loc[:, cols] = block
        return out
    if null_model == "block_bootstrap":
        # Destroys: long-range temporal alignment while preserving short-range
        # autocorrelation. Resample contiguous time blocks (~sqrt(n)) of the full
        # row, then restamp a monotonic timestamp grid so the schema holds.
        n = len(out)
        block = max(1, int(round(np.sqrt(n))))
        starts = rng.integers(0, n, size=int(np.ceil(n / block)))
        idx = np.concatenate([np.arange(s, s + block) % n for s in starts])[:n]
        resampled = out.iloc[idx].reset_index(drop=True)
        resampled["timestamp"] = out["timestamp"].to_numpy()[:n]
        return resampled
    if null_model == "volume_neutral":
        columns = _size_columns(out, depth)
        # copy() before reshape/shuffle: .to_numpy() may be a read-only view.
        flat = out[columns].to_numpy(dtype=float).copy().reshape(-1)
        rng.shuffle(flat)
        out.loc[:, columns] = flat.reshape(out[columns].shape)
        return out

    columns = _size_columns(out, depth)
    for column in columns:
        out[column] = iaaft_surrogate(out[column].to_numpy(dtype=float), rng)
        out[column] = np.maximum(out[column], 0.0)
    return out


def cliffs_delta(left: np.ndarray, right: np.ndarray) -> float:
    if len(left) == 0 or len(right) == 0:
        raise RuntimeError("Cliff's delta requires non-empty samples")
    gt = 0
    lt = 0
    for x in left:
        gt += int(np.sum(x > right))
        lt += int(np.sum(x < right))
    return float((gt - lt) / (len(left) * len(right)))


def effect_size_class(delta: float) -> str:
    magnitude = abs(delta)
    if magnitude < 0.147:
        return "negligible"
    if magnitude < 0.33:
        return "small"
    if magnitude < 0.474:
        return "medium"
    return "large"


def evaluate_null_gate(
    frame: pd.DataFrame,
    *,
    depth: int,
    alpha: float,
    n_min_edges: int,
    n_surrogates: int,
    null_model: str,
    seed: int,
    gate: StatisticalGate | None = None,
) -> dict[str, object]:
    if n_surrogates < 1000:
        raise ValueError("n_surrogates must be >= 1000")
    cfg = gate or StatisticalGate()
    rng = np.random.default_rng(seed)
    observed = curvature_series(frame, depth=depth, alpha=alpha, n_min_edges=n_min_edges)
    observed_mean = float(np.mean(observed))
    null_means = np.empty(n_surrogates, dtype=float)
    for idx in range(n_surrogates):
        candidate = surrogate_frame(frame, depth=depth, null_model=null_model, rng=rng)
        null_values = curvature_series(candidate, depth=depth, alpha=alpha, n_min_edges=n_min_edges)
        null_means[idx] = float(np.mean(null_values))
    p_value = float((np.sum(np.abs(null_means) >= abs(observed_mean)) + 1.0) / (n_surrogates + 1.0))
    delta = cliffs_delta(observed, null_means)
    supported = p_value < cfg.p_threshold and abs(delta) >= cfg.cliffs_delta_threshold
    return {
        "mean_curvature": observed_mean,
        "p_value": p_value,
        "cliffs_delta": float(delta),
        "effect_size_class": effect_size_class(float(delta)),
        "falsification_status": "SUPPORTED" if supported else "HYPOTHESIS_NOT_SUPPORTED",
        "observed_count": int(len(observed)),
        "null_mean": float(np.mean(null_means)),
        "null_std": float(np.std(null_means)),
    }
