"""Statistical drift utilities used across TradePulse analytics.

The module focuses on providing numerically stable implementations of the
metrics most commonly used to quantify dataset drift: Jensen–Shannon
Divergence (JSD), Kolmogorov–Smirnov (KS) two-sample test, and Population
Stability Index (PSI).  In addition to the raw metrics it offers helpers for
loading dynamic thresholds, generating synthetic datasets for tests, and
parallelising drift computation across large collections of features.

The functions follow a defensive programming style – validating inputs,
removing NaNs, and surfacing issues via :mod:`logging`.  The intention is to
make them safe for usage within CI pipelines where unexpected input should not
cause unhandled exceptions.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype
from scipy.spatial.distance import jensenshannon
from scipy.stats import ks_2samp

logger = logging.getLogger(__name__)


ArrayLike = Sequence[float] | np.ndarray | pd.Series


@dataclass(frozen=True)
class DriftTestResult:
    """Result of a two-sample statistical test."""

    statistic: float
    pvalue: float
    valid: bool
    message: str

    def drift_detected(self, *, alpha: float) -> bool:
        """Return ``True`` if the null hypothesis is rejected."""

        if not self.valid:
            return False
        return self.pvalue < alpha


@dataclass(frozen=True)
class DriftMetric:
    """Container aggregating multiple drift measurements for a feature."""

    feature: str
    js_divergence: float
    ks: DriftTestResult
    psi: float

    @property
    def drifted(self) -> bool:
        """Whether any of the metrics indicates drift."""

        return any(
            (
                np.isfinite(self.js_divergence) and self.js_divergence > 0,
                self.ks.valid and self.ks.pvalue < 0.05,
                np.isfinite(self.psi) and self.psi > 0,
            )
        )


@dataclass(frozen=True)
class DriftThresholds:
    """Dynamic thresholds loaded from configuration files."""

    default_jsd: float = 0.1
    default_ks: float = 0.05
    per_signal: Mapping[str, Mapping[str, float]] | None = None

    def threshold_for(self, signal: str, metric: str) -> float:
        """Return the configured threshold for ``metric`` on ``signal``."""

        if self.per_signal and signal in self.per_signal:
            return float(self.per_signal[signal].get(metric, self._default(metric)))
        return self._default(metric)

    def _default(self, metric: str) -> float:
        if metric == "jsd":
            return self.default_jsd
        if metric in {"ks", "ks_pvalue"}:
            return self.default_ks
        raise KeyError(metric)


def _as_array(values: ArrayLike, *, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        logger.warning("%s array is empty; returning NaN", name)
        return np.array([], dtype=float)
    if not np.all(np.isfinite(array) | np.isnan(array)):
        raise ValueError(f"{name} contains non-finite values")
    return array


def _coerce_numeric_series(series: pd.Series, *, column: str, frame: str) -> tuple[np.ndarray | None, str | None]:
    """Return a float array for *series* or an error message if conversion fails."""

    if is_numeric_dtype(series.dtype):
        array = series.to_numpy(dtype=float, copy=False)
    else:
        coerced = pd.to_numeric(series, errors="coerce")
        if not coerced.notna().any():
            return None, f"{frame} column contains no numeric values"
        array = coerced.to_numpy(dtype=float)

    valid = np.isfinite(array)
    if valid.all():
        return array, None

    filtered = array[valid]
    if filtered.size == 0:
        return None, f"{frame} column contains no numeric values"
    return filtered, None


def compute_js_divergence(data1: ArrayLike, data2: ArrayLike) -> float:
    """Return the Jensen–Shannon divergence between two distributions.

    The SciPy implementation returns the distance, so we square it to obtain
    the divergence.  Empty inputs produce ``np.nan`` and emit a warning to
    simplify CI usage where lack of data should not raise.
    """

    arr1 = _as_array(data1, name="data1")
    arr2 = _as_array(data2, name="data2")

    # Treat NaNs independently for each sample array.  In practice the baseline
    # and current datasets rarely have the same number of observations, so we
    # must not assume positional alignment.
    arr1 = arr1[np.isfinite(arr1)]
    arr2 = arr2[np.isfinite(arr2)]

    if arr1.size == 0 or arr2.size == 0:
        return float("nan")

    def _looks_like_probability_mass(array: np.ndarray) -> bool:
        """Best-effort detection of already-normalised probability vectors."""

        if array.size == 0:
            return False
        if np.any(array < 0):
            return False
        total = array.sum()
        return np.isfinite(total) and np.isclose(total, 1.0, rtol=1e-3, atol=1e-6)

    if arr1.shape == arr2.shape and _looks_like_probability_mass(arr1) and _looks_like_probability_mass(arr2):
        prob1 = arr1
        prob2 = arr2
    else:
        combined = np.concatenate([arr1, arr2])
        # Degenerate case: both arrays collapse to a single constant value.
        if np.allclose(combined.min(), combined.max()):
            return 0.0

        bin_edges = np.histogram_bin_edges(combined, bins="auto")
        if bin_edges.size < 2:
            # ``np.histogram_bin_edges`` can return a single edge when ``combined``
            # contains identical values due to floating point rounding.  Fallback
            # to two edges spanning the observed range.
            unique = np.unique(combined)
            if unique.size == 1:
                return 0.0
            span = unique[[0, -1]]
            bin_edges = np.linspace(span[0], span[1], 2)

        hist1, _ = np.histogram(arr1, bins=bin_edges, density=False)
        hist2, _ = np.histogram(arr2, bins=bin_edges, density=False)

        total1 = hist1.sum()
        total2 = hist2.sum()
        if total1 == 0 or total2 == 0:
            return float("nan")

        prob1 = hist1 / total1
        prob2 = hist2 / total2

    distance = jensenshannon(prob1, prob2)
    divergence = float(distance ** 2)
    logger.debug("Computed JSD divergence: %s", divergence)
    return divergence


def compute_ks_test(data1: ArrayLike, data2: ArrayLike) -> DriftTestResult:
    """Execute the two-sample Kolmogorov–Smirnov test.

    NaN values are removed prior to the test.  If insufficient data remains the
    function returns a non-valid result with explanatory message.
    """

    arr1 = _as_array(data1, name="data1")
    arr2 = _as_array(data2, name="data2")
    arr1 = arr1[np.isfinite(arr1)]
    arr2 = arr2[np.isfinite(arr2)]
    if arr1.size < 2 or arr2.size < 2:
        message = "insufficient data for KS test"
        logger.warning(message)
        return DriftTestResult(statistic=float("nan"), pvalue=float("nan"), valid=False, message=message)
    statistic, pvalue = ks_2samp(arr1, arr2)
    message = "ok"
    logger.debug("KS test statistic=%s pvalue=%s", statistic, pvalue)
    return DriftTestResult(float(statistic), float(pvalue), True, message)


def compute_psi(
    baseline: ArrayLike,
    current: ArrayLike,
    *,
    bins: int | Sequence[float] = 10,
    clip: float = 1e-12,
) -> float:
    """Compute the Population Stability Index (PSI).

    Parameters
    ----------
    baseline, current:
        Arrays describing the reference and candidate samples.
    bins:
        Either the number of equally spaced bins or explicit bin edges shared
        between both histograms.  A higher bin count increases sensitivity at
        the cost of noise.
    clip:
        Lower bound for probabilities to prevent ``log(0)`` issues.
    """

    ref = _as_array(baseline, name="baseline")
    cur = _as_array(current, name="current")
    if ref.size == 0 or cur.size == 0:
        return float("nan")
    if isinstance(bins, Sequence) and not isinstance(bins, (str, bytes)):
        bin_edges = np.asarray(bins, dtype=float)
    else:
        combined = np.concatenate([ref, cur])
        bin_edges = np.linspace(combined.min(), combined.max(), int(bins) + 1)
    ref_hist, _ = np.histogram(ref, bins=bin_edges, density=False)
    cur_hist, _ = np.histogram(cur, bins=bin_edges, density=False)
    ref_total = ref_hist.sum()
    cur_total = cur_hist.sum()
    if ref_total == 0 or cur_total == 0:
        return float("nan")
    ref_pct = np.clip(ref_hist / ref_total, clip, None)
    cur_pct = np.clip(cur_hist / cur_total, clip, None)
    psi = np.sum((ref_pct - cur_pct) * np.log(ref_pct / cur_pct))
    logger.debug("PSI=%s", psi)
    return float(psi)


def compute_parallel_drift(
    baseline: pd.DataFrame,
    current: pd.DataFrame,
    *,
    metrics: Sequence[str] = ("jsd", "ks", "psi"),
    workers: int | None = None,
    thresholds: DriftThresholds | None = None,
) -> Mapping[str, DriftMetric]:
    """Compute drift metrics for all shared columns in parallel."""

    columns = [col for col in baseline.columns if col in current.columns]
    thresholds = thresholds or DriftThresholds()
    metrics_set = frozenset(metrics)
    non_numeric_message = "non-numeric column"

    def _compute(column: str) -> tuple[str, DriftMetric]:
        base, base_error = _coerce_numeric_series(baseline[column], column=column, frame="baseline")
        curr, curr_error = _coerce_numeric_series(current[column], column=column, frame="current")
        if base is None or curr is None:
            message = base_error or curr_error or non_numeric_message
            logger.warning(
                "Column %s cannot be processed for drift metrics: %s", column, message
            )
            skipped = DriftTestResult(float("nan"), float("nan"), False, non_numeric_message)
            return column, DriftMetric(column, float("nan"), skipped, float("nan"))

        jsd_value = compute_js_divergence(base, curr) if "jsd" in metrics_set else float("nan")
        if "ks" in metrics_set:
            ks_result = compute_ks_test(base, curr)
        else:
            ks_result = DriftTestResult(float("nan"), float("nan"), False, "skipped")
        psi_value = compute_psi(base, curr) if "psi" in metrics_set else float("nan")
        return column, DriftMetric(column, jsd_value, ks_result, psi_value)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = dict(executor.map(_compute, columns))
    return results


class DriftDetector:
    """High level orchestration for drift detection workflows."""

    def __init__(
        self,
        *,
        thresholds: DriftThresholds | None = None,
        alpha: float = 0.05,
        workers: int | None = None,
    ) -> None:
        self.thresholds = thresholds or DriftThresholds()
        self.alpha = alpha
        self.workers = workers

    def compare(self, baseline: pd.DataFrame, current: pd.DataFrame) -> Mapping[str, DriftMetric]:
        """Return drift metrics for aligned columns."""

        results = compute_parallel_drift(
            baseline,
            current,
            thresholds=self.thresholds,
            workers=self.workers,
        )
        return results

    def summary(self, results: Mapping[str, DriftMetric]) -> Mapping[str, Any]:
        summary: MutableMapping[str, Any] = {}
        for feature, metric in results.items():
            summary[feature] = {
                "jsd": metric.js_divergence,
                "ks_pvalue": metric.ks.pvalue,
                "psi": metric.psi,
                "drifted": self._is_drifted(feature, metric),
            }
        return summary

    def _is_drifted(self, feature: str, metric: DriftMetric) -> bool:
        jsd_threshold = self.thresholds.threshold_for(feature, "jsd")
        ks_threshold = self.thresholds.threshold_for(feature, "ks")
        drift_flags = []
        if np.isfinite(metric.js_divergence):
            drift_flags.append(metric.js_divergence > jsd_threshold)
        if metric.ks.valid:
            drift_flags.append(metric.ks.pvalue < ks_threshold)
        if np.isfinite(metric.psi):
            drift_flags.append(metric.psi > 0)
        return any(drift_flags)


def generate_synthetic_data(
    rows: int,
    cols: int,
    drift_level: float,
    *,
    seed: int | None = None,
    include_categorical: bool = False,
    categories: Sequence[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate baseline/current datasets with optional drift."""

    if rows <= 0 or cols <= 0:
        raise ValueError("rows and cols must be positive")
    rng = np.random.default_rng(seed)
    base = rng.normal(loc=0.0, scale=1.0, size=(rows, cols))
    drifted = rng.normal(loc=drift_level, scale=1.0 + abs(drift_level) * 0.5, size=(rows, cols))
    base_df = pd.DataFrame(base, columns=[f"f{i}" for i in range(cols)])
    drift_df = pd.DataFrame(drifted, columns=base_df.columns)
    if include_categorical:
        categories = tuple(categories or ("A", "B", "C"))
        probs = np.ones(len(categories)) / len(categories)
        base_cat = rng.choice(categories, size=rows, p=probs)
        shifted_probs = np.clip(probs + drift_level / 10, 0.01, None)
        shifted_probs /= shifted_probs.sum()
        drift_cat = rng.choice(categories, size=rows, p=shifted_probs)
        base_df["category"] = base_cat
        drift_df["category"] = drift_cat
    return base_df, drift_df


def load_thresholds(path: str | Path | None) -> DriftThresholds:
    """Load drift thresholds from YAML or JSON configuration."""

    if path is None:
        return DriftThresholds()
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    text = path.read_text()
    data: Mapping[str, Any]
    if path.suffix.lower() in {".yaml", ".yml"}:
        import yaml  # Lazy import to avoid hard dependency when unused

        loaded = yaml.safe_load(text)
        data = loaded if loaded is not None else {}
    else:
        text = text.strip()
        data = json.loads(text) if text else {}
    if not isinstance(data, Mapping):
        raise TypeError("threshold configuration must be a mapping")
    default_jsd = float(data.get("jsd_threshold", 0.1))
    default_ks = float(data.get("ks_pvalue_threshold", 0.05))
    per_signal = data.get("thresholds")
    return DriftThresholds(default_jsd, default_ks, per_signal)


__all__ = [
    "compute_js_divergence",
    "compute_ks_test",
    "compute_psi",
    "compute_parallel_drift",
    "DriftDetector",
    "DriftMetric",
    "DriftTestResult",
    "DriftThresholds",
    "generate_synthetic_data",
    "load_thresholds",
]
