# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Kuramoto frozen-artifact contract.

Loads the cross-asset Kuramoto evidence bundle, verifies each file's
SHA-256 against ``results/cross_asset_kuramoto/offline_robustness/SOURCE_HASHES.json``,
and exposes typed views on the demo equity curve, fold metrics, and
parameter lock.

Fail-closed: any missing file or hash mismatch raises
:class:`FrozenArtifactMismatch` and the gate runner records a
``FAIL`` verdict on the hash-integrity axis.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST: Final[Path] = (
    REPO_ROOT / "results" / "cross_asset_kuramoto" / "offline_robustness" / "SOURCE_HASHES.json"
)
DEMO_EQUITY_REL: Final[str] = "results/cross_asset_kuramoto/demo/equity_curve.csv"
DEMO_FOLDS_REL: Final[str] = "results/cross_asset_kuramoto/demo/fold_metrics.csv"
DEMO_RISK_REL: Final[str] = "results/cross_asset_kuramoto/demo/risk_metrics.csv"
PARAM_LOCK_REL: Final[str] = "results/cross_asset_kuramoto/PARAMETER_LOCK.json"

# Extension manifest: hash-verified auxiliary artifacts that are *outside*
# the original 28-artifact SOURCE_HASHES.json contract. Adding a new
# auxiliary input requires appending here AND in the inline hash constant
# below — both must move together, so drift is caught at load time.
LOO_GRID_REL: Final[str] = "results/cross_asset_kuramoto/offline_robustness/leave_one_asset_out.csv"
LOO_GRID_SHA256: Final[str] = "9fdb19129630bddcda7499cd6a1ec20b68b34715d8c52c72bd286676e8156a61"


class FrozenArtifactMismatch(RuntimeError):
    """Raised when a frozen artifact fails sha256 verification or is missing."""


def _load_loo_grid_if_present(repo_root: Path) -> pd.DataFrame | None:
    """Load + hash-verify the LOO grid; return None if the file is absent.

    A present-but-mismatched file is fail-closed (raises
    :class:`FrozenArtifactMismatch`); a missing file is tolerated so the
    framework can run on a minimal frozen bundle.
    """
    path = repo_root / LOO_GRID_REL
    if not path.is_file():
        return None
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if sha != LOO_GRID_SHA256:
        raise FrozenArtifactMismatch(f"{LOO_GRID_REL}: got {sha}, expected {LOO_GRID_SHA256}")
    return pd.read_csv(path)


@dataclass(frozen=True)
class FrozenArtifactManifest:
    """Parsed SOURCE_HASHES.json plus the repo root used to resolve rels."""

    generated_utc: str
    regenerated_utc: str | None
    hashes: dict[str, str]
    repo_root: Path

    @classmethod
    def load(
        cls,
        manifest_path: Path = DEFAULT_MANIFEST,
        repo_root: Path = REPO_ROOT,
    ) -> FrozenArtifactManifest:
        if not manifest_path.is_file():
            raise FrozenArtifactMismatch(f"frozen-artifact manifest missing: {manifest_path}")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return cls(
            generated_utc=str(data["generated_utc"]),
            regenerated_utc=data.get("regenerated_utc"),
            hashes=dict(data["hashes"]),
            repo_root=repo_root,
        )

    def verify_all(self) -> None:
        """Raise :class:`FrozenArtifactMismatch` on any missing/mismatched file."""
        mismatches: list[str] = []
        missing: list[str] = []
        for rel, expected in self.hashes.items():
            path = self.repo_root / rel
            if not path.is_file():
                missing.append(rel)
                continue
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            if sha != expected:
                mismatches.append(f"{rel}: got {sha}, expected {expected}")
        if missing or mismatches:
            parts: list[str] = []
            if missing:
                parts.append("missing:\n  " + "\n  ".join(missing))
            if mismatches:
                parts.append("sha256 mismatch:\n  " + "\n  ".join(mismatches))
            raise FrozenArtifactMismatch("\n".join(parts))


@dataclass(frozen=True)
class KuramotoRobustnessContract:
    """Typed view on the frozen evidence bundle for robustness suites."""

    manifest: FrozenArtifactManifest
    equity_curve: pd.DataFrame
    fold_metrics: pd.DataFrame
    risk_metrics: pd.DataFrame
    parameter_lock: dict[str, object]
    loo_grid: pd.DataFrame | None = None

    @classmethod
    def from_frozen_artifacts(
        cls,
        manifest_path: Path = DEFAULT_MANIFEST,
        repo_root: Path = REPO_ROOT,
    ) -> KuramotoRobustnessContract:
        """Load contract and verify hashes in one fail-closed step.

        Also loads the optional leave-one-asset-out grid when the file
        is present on disk; its sha256 is verified against the inline
        :data:`LOO_GRID_SHA256` constant. A missing LOO file is tolerated
        (``loo_grid`` stays None); a present-but-mismatched file is a
        fail-closed error.
        """
        manifest = FrozenArtifactManifest.load(manifest_path, repo_root)
        manifest.verify_all()

        equity = pd.read_csv(
            repo_root / DEMO_EQUITY_REL,
            parse_dates=["date"],
        )
        folds = pd.read_csv(
            repo_root / DEMO_FOLDS_REL,
            parse_dates=["is_start", "os_start", "os_end"],
        )
        risk = pd.read_csv(repo_root / DEMO_RISK_REL)
        param_lock = json.loads((repo_root / PARAM_LOCK_REL).read_text(encoding="utf-8"))
        loo_grid = _load_loo_grid_if_present(repo_root)
        contract = cls(
            manifest=manifest,
            equity_curve=equity,
            fold_metrics=folds,
            risk_metrics=risk,
            parameter_lock=param_lock,
            loo_grid=loo_grid,
        )
        contract.assert_frozen_consistency()
        return contract

    def assert_frozen_consistency(self) -> None:
        """Sanity checks that panic on drift inside the loaded frames."""
        required_equity = {"date", "strategy_cumret", "benchmark_cumret", "drawdown"}
        missing = required_equity - set(self.equity_curve.columns)
        if missing:
            raise FrozenArtifactMismatch(f"equity_curve.csv missing columns: {sorted(missing)}")
        required_folds = {"fold_id", "sharpe", "max_dd", "pass_fail"}
        missing = required_folds - set(self.fold_metrics.columns)
        if missing:
            raise FrozenArtifactMismatch(f"fold_metrics.csv missing columns: {sorted(missing)}")
        if len(self.fold_metrics) < 2:
            raise FrozenArtifactMismatch(
                f"fold_metrics.csv needs at least 2 folds, has {len(self.fold_metrics)}"
            )
        if self.loo_grid is not None:
            required_loo = {
                "loo_type",
                "omitted_asset",
                "oos_sharpe",
                "fold1",
                "fold2",
                "fold3",
                "fold4",
                "fold5",
            }
            missing = required_loo - set(self.loo_grid.columns)
            if missing:
                raise FrozenArtifactMismatch(
                    f"leave_one_asset_out.csv missing columns: {sorted(missing)}"
                )

    def daily_strategy_returns(self) -> pd.Series:
        """Strategy daily log-returns from ``strategy_cumret``.

        Computed as ``diff(log(strategy_cumret))``: this is the canonical
        time-additive representation of a multiplicative equity curve and
        is *mathematically exact* for the hypothetical raw ``net_ret``
        series that produced the wealth trajectory (no approximation).

        Log returns are chosen over simple ``pct_change`` because they
        are the honest input to stationary bootstraps and Sharpe-ratio
        nulls: they are time-additive, symmetric under sign inversion,
        and preserve independence under permutation.
        """
        eq = self.equity_curve["strategy_cumret"].astype(float).to_numpy()
        log_ret = np.log(eq[1:]) - np.log(eq[:-1])
        s = pd.Series(log_ret, name="strategy_log_ret")
        s.index = self.equity_curve["date"].iloc[1:].to_numpy()
        return s

    def daily_benchmark_returns(self) -> pd.Series:
        """Benchmark daily log-returns from ``benchmark_cumret``.

        Same derivation as :meth:`daily_strategy_returns` for symmetry.
        """
        eq = self.equity_curve["benchmark_cumret"].astype(float).to_numpy()
        log_ret = np.log(eq[1:]) - np.log(eq[:-1])
        s = pd.Series(log_ret, name="benchmark_log_ret")
        s.index = self.equity_curve["date"].iloc[1:].to_numpy()
        return s
