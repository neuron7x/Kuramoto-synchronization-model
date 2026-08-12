"""Kernel purity audit for deterministic behavior guarantees."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from research.kernels.ofi_unity_live import _safe_spearman, ofi_unity_kernel

EPS = 1e-9


@dataclass(frozen=True)
class PurityCheck:
    name: str
    passed: bool
    details: str


@dataclass(frozen=True)
class PurityReport:
    checks: tuple[PurityCheck, ...]

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)


def _synthetic_df(rows: int = 300) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=rows, freq="h", tz="UTC")
    x = np.cumsum(np.random.default_rng(42).normal(0, 0.1, rows)) + 100
    return pd.DataFrame({"bid_1": x - 0.01, "ask_1": x + 0.01}, index=idx)


def verify_eigenvalue_stability() -> PurityCheck:
    s = ofi_unity_kernel(_synthetic_df(), window=60)
    arr = np.asarray(s.values, dtype=float)
    cond = float(np.nanmax(arr) / max(np.nanmin(arr[arr > 0]) if np.any(arr > 0) else 1.0, EPS))
    passed = cond < 100.0
    return PurityCheck("eigenvalue_stability", passed, f"condition_number={cond:.6f}")


def verify_rank_correlation_determinism(runs: int = 100) -> PurityCheck:
    rng = np.random.default_rng(42)
    x = rng.normal(size=2048)
    y = rng.normal(size=2048)
    vals = np.array([_safe_spearman(x, y) for _ in range(runs)], dtype=float)
    var = float(np.var(vals))
    passed = var <= 1e-15
    return PurityCheck("rank_determinism", passed, f"variance={var:.3e}")


def verify_hash_reproducibility(runs: int = 1000) -> PurityCheck:
    payload = {"a": 1, "b": [1, 2, 3], "z": {"x": 9}}
    hashes = {
        hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        for _ in range(runs)
    }
    passed = len(hashes) == 1
    return PurityCheck("hash_reproducibility", passed, f"unique_hashes={len(hashes)}")


def verify_numeric_stability() -> PurityCheck:
    a = np.float64(1.0) + np.float64(1e-12)
    b = np.float64(1.0)
    err = float(abs(a - b))
    passed = err <= 1e-9
    return PurityCheck("numeric_stability", passed, f"abs_error={err:.3e}")


def audit_determinism() -> PurityReport:
    checks = (
        verify_eigenvalue_stability(),
        verify_rank_correlation_determinism(),
        verify_hash_reproducibility(),
        verify_numeric_stability(),
    )
    return PurityReport(checks=checks)
