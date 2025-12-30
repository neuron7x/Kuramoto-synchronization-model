#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
try:
    import sitecustomize  # type: ignore  # noqa: F401
except ImportError:
    pass
# Preload legacy observability shim to avoid circular imports during certification entrypoint
try:
    import core.neuro.serotonin.observability  # type: ignore  # noqa: F401
except ImportError:
    pass

os.environ.setdefault("TRADEPULSE_LIGHT_DATA_IMPORT", "1")

from tradepulse.core.neuro.serotonin.certify import (
    RegimeMetrics,
    run_basal_ganglia_integration,
    run_regime,
    write_certificate,
)
from tradepulse.core.neuro.serotonin.regimes import build_regimes
from tradepulse.core.neuro.serotonin.serotonin_controller import SerotoninController
from core.data.dataset_contracts import contract_by_path
from core.data.fingerprint import record_run_fingerprint


def _load_series(path: Path, *, fast: bool) -> np.ndarray:
    df = pd.read_csv(path)
    lower_cols = {c.lower(): c for c in df.columns}
    close_col = None
    for key in ("close", "adj_close", "price"):
        if key in lower_cols:
            close_col = lower_cols[key]
            break
    if close_col is None:
        # Fallback to last column if schema differs
        close_col = df.columns[-1]
    series = df[close_col].astype(float).to_numpy()
    if fast:
        series = series[: min(len(series), 256)]
    return series


def _git_commit() -> str | None:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True)
            .strip()
            .lower()
        )
    except Exception:
        return None


def certify(
    dataset: Path,
    out_dir: Path,
    seed: int,
    *,
    fast: bool,
    flip_window: int,
    flip_limit: int,
) -> tuple[list[RegimeMetrics], list[str]]:
    prices = _load_series(dataset, fast=fast)
    regimes = build_regimes(prices, seed)
    controller = SerotoninController()

    results: list[RegimeMetrics] = []
    for name, series in regimes.items():
        results.append(
            run_regime(
                name=name,
                prices=series,
                controller=controller,
                flip_window=flip_window,
                flip_limit=flip_limit,
            )
        )

    integration_violations = run_basal_ganglia_integration(seed)
    write_certificate(
        out_dir=out_dir,
        seed=seed,
        dataset=str(dataset),
        regime_results=results,
        integration_violations=integration_violations,
        commit=_git_commit(),
    )
    return results, integration_violations


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serotonin robustness certification")
    parser.add_argument("--dataset", required=True, help="Path to OHLCV dataset CSV")
    parser.add_argument(
        "--out", default="artifacts/serotonin-cert", help="Output directory for artifacts"
    )
    parser.add_argument("--seed", type=int, default=123, help="Deterministic seed")
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Enable fast mode (shorter series, smaller flip window)",
    )
    parser.add_argument(
        "--flip-window",
        type=int,
        default=None,
        help="Override flip window size (defaults depend on --fast)",
    )
    parser.add_argument(
        "--flip-limit",
        type=int,
        default=None,
        help="Override flip limit (defaults depend on --fast)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    fast = bool(args.fast)
    flip_window = args.flip_window or (12 if fast else 24)
    flip_limit = args.flip_limit or (10 if fast else 12)
    dataset_path = Path(args.dataset)
    out_dir = Path(args.out)

    if not dataset_path.exists():
        raise SystemExit(f"Dataset not found: {dataset_path}")

    contract = contract_by_path(dataset_path)
    if contract:
        record_run_fingerprint(contract, run_type="certification")

    results, integration_violations = certify(
        dataset=dataset_path,
        out_dir=out_dir,
        seed=args.seed,
        fast=fast,
        flip_window=flip_window,
        flip_limit=flip_limit,
    )

    any_fail = integration_violations or any(r.violations for r in results)
    if any_fail:
        lines = ["Certification failed due to:"]
        for r in results:
            if r.violations:
                lines.append(f"- {r.name}: {', '.join(r.violations)}")
        for v in integration_violations:
            lines.append(f"- integration: {v}")
        print("\n".join(lines))
        return 1

    print(f"Certification successful. Artifacts written to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
