#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""CLI utility for running the Kuramoto–Ricci composite integration pipeline."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_ENV = "KURAMOTO_RICCI_CONFIG"
DEFAULT_OUTPUT_ENV = "KURAMOTO_RICCI_OUTPUT_DIR"


def _resolve_path(candidate: Path, *, allow_missing: bool = False) -> Path:
    """Resolve *candidate* relative to the repository root when not absolute."""

    expanded = Path(candidate).expanduser()
    if not expanded.is_absolute():
        expanded = (REPO_ROOT / expanded).resolve()
    if not allow_missing and not expanded.exists():
        raise FileNotFoundError(expanded)
    return expanded


def _path_default(env_var: str, fallback: Path) -> Path:
    value = os.environ.get(env_var)
    if value:
        expanded = Path(value).expanduser()
        if not expanded.is_absolute():
            return (REPO_ROOT / expanded).resolve()
        return expanded
    return (REPO_ROOT / fallback).resolve()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        type=Path,
        required=True,
        help="Path to a CSV containing at least a 'close' column and optionally 'volume'.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=_path_default(DEFAULT_CONFIG_ENV, Path("configs/kuramoto_ricci_composite.yaml")),
        help=(
            "Configuration file for the composite engine. "
            f"Defaults to ${{{DEFAULT_CONFIG_ENV}}} or 'configs/kuramoto_ricci_composite.yaml'."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["analyze"],
        default="analyze",
        help="Integration mode to execute. Only 'analyze' is currently supported.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_path_default(DEFAULT_OUTPUT_ENV, Path("outputs/kuramoto_ricci")),
        help=(
            "Directory where generated artifacts will be stored. "
            f"Defaults to ${{{DEFAULT_OUTPUT_ENV}}} or 'outputs/kuramoto_ricci'."
        ),
    )
    parser.add_argument(
        "--config-override",
        action="append",
        dest="config_overrides",
        default=[],
        metavar="KEY=VALUE",
        help=(
            "Override configuration values using dot-delimited keys. "
            "Example: --config-override kuramoto.base_window=256"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and report planned actions without running the integration.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm potentially destructive actions such as overwriting output files.",
    )
    return parser.parse_args(argv)


def _ensure_output_dir(path: Path, *, confirm: bool) -> None:
    if path.exists():
        contains_items = any(path.iterdir())
        if contains_items and not confirm:
            raise RuntimeError(
                f"Output directory '{path}' is not empty. Use --yes to allow overwriting existing files."
            )
    else:
        path.mkdir(parents=True, exist_ok=True)


def _print_plan(
    data_path: Path, config_path: Path, output_dir: Path, overrides: Iterable[str]
) -> None:
    print("[dry-run] Kuramoto–Ricci composite integration plan")
    print(f"[dry-run] Data source: {data_path}")
    print(f"[dry-run] Configuration: {config_path}")
    print(f"[dry-run] Output directory: {output_dir}")
    if overrides:
        print(f"[dry-run] Configuration overrides: {', '.join(overrides)}")
    else:
        print("[dry-run] Configuration overrides: <none>")


def run_integration(
    *,
    data_path: Path,
    config_path: Path,
    output_dir: Path,
    config_overrides: Sequence[str],
) -> None:
    from core.config import load_kuramoto_ricci_config, parse_cli_overrides
    from core.indicators.kuramoto_ricci_composite import GeoSyncCompositeEngine

    df = pd.read_csv(data_path, index_col=0, parse_dates=True)
    if "volume" not in df.columns:
        df["volume"] = 1.0

    overrides = parse_cli_overrides(config_overrides)
    cfg = load_kuramoto_ricci_config(config_path, cli_overrides=overrides)
    engine = GeoSyncCompositeEngine(**cfg.to_engine_kwargs())
    sig = engine.analyze_market(df)

    # Save outputs
    engine.get_signal_dataframe().to_csv(output_dir / "signal_history.csv", index=False)
    df_out = df.copy()
    df_out.loc[df_out.index[-1], "phase"] = sig.phase.value
    df_out.loc[df_out.index[-1], "entry_signal"] = sig.entry_signal
    df_out.loc[df_out.index[-1], "confidence"] = sig.confidence
    df_out.to_csv(output_dir / "enhanced_features.csv")

    print(f"Phase: {sig.phase.value}")
    print(f"Confidence: {sig.confidence:.3f}")
    print(
        "Entry: "
        f"{sig.entry_signal:.3f} | Exit: {sig.exit_signal:.3f} | Risk: {sig.risk_multiplier:.3f}"
    )
    print(f"Kuramoto R: {sig.kuramoto_R:.3f}, Coherence: {sig.cross_scale_coherence:.3f}")
    print(
        "Static κ: "
        f"{sig.static_ricci:.4f}, Temporal κ_t: {sig.temporal_ricci:.4f}, "
        f"Transition: {sig.topological_transition:.3f}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        data_path = _resolve_path(args.data)
    except FileNotFoundError as exc:  # pragma: no cover - defensive guard
        raise SystemExit(f"Data source not found: {exc}") from exc

    try:
        config_path = _resolve_path(args.config)
    except FileNotFoundError as exc:  # pragma: no cover - defensive guard
        raise SystemExit(f"Configuration file not found: {exc}") from exc

    output_dir = _resolve_path(args.output, allow_missing=True)

    if args.dry_run:
        _print_plan(data_path, config_path, output_dir, args.config_overrides)
        return 0

    try:
        _ensure_output_dir(output_dir, confirm=args.yes)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    run_integration(
        data_path=data_path,
        config_path=config_path,
        output_dir=output_dir,
        config_overrides=args.config_overrides,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
