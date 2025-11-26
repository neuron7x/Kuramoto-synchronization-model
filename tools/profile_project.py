"""CLI utility to profile representative TradePulse workflows."""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

warnings.filterwarnings(
    "ignore",
    message='Field name "schema" in "QualityGateConfig" shadows',
)
warnings.filterwarnings(
    "ignore",
    message="SciPy unavailable; using discrete Wasserstein approximation",
)

from core.indicators.entropy import delta_entropy, entropy  # noqa: E402
from core.indicators.kuramoto import compute_phase, kuramoto_order  # noqa: E402
from core.indicators.ricci import build_price_graph, mean_ricci  # noqa: E402
from observability.profiling import ProfileCollector  # noqa: E402


def _default_dataset_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    return root / "sample.csv"


def profile_analytics_pipeline(
    *,
    data_path: Path,
    price_column: str,
    window: int,
    bins: int,
    delta: float,
) -> dict[str, Any]:
    """Profile the analytics pipeline using the provided dataset."""

    if not data_path.exists():
        raise FileNotFoundError(f"Dataset {data_path} does not exist")

    collector = ProfileCollector()
    dataset_meta: dict[str, Any] = {"path": str(data_path)}

    with collector.section("load-data", dataset_meta) as meta:
        frame = pd.read_csv(data_path, index_col=0)
        meta["rows"] = int(len(frame))
        meta["columns"] = list(frame.columns)
        if price_column not in frame.columns:
            available = list(frame.columns)
            meta["error"] = {
                "price_column": price_column,
                "available_columns": available,
            }
            raise ValueError(
                f"Price column '{price_column}' not found in dataset columns {available}"
            )
        prices = frame[price_column].to_numpy(dtype=float, copy=False)
        meta["price_column"] = price_column
        meta["series_length"] = int(prices.size)

    dataset_info = dict(dataset_meta)

    with collector.section(
        "compute-phase", {"series_length": dataset_info["series_length"]}
    ) as meta:
        phases = compute_phase(prices)
        meta["phase_samples"] = int(len(phases))

    window_prices: np.ndarray
    with collector.section("prepare-window", {"window": window}) as meta:
        if window <= 0:
            raise ValueError("window must be positive")
        if prices.size < window:
            meta["error"] = {
                "series_length": int(prices.size),
                "window": int(window),
            }
            raise ValueError(
                f"Not enough price observations ({prices.size}) for window size {window}"
            )
        window_prices = prices[-window:]
        window_phases = phases[-window:]
        meta["window_samples"] = int(window_prices.size)

    with collector.section("kuramoto-order", {"window": window}) as meta:
        order_parameter = float(kuramoto_order(window_phases))
        meta["order_parameter"] = order_parameter

    with collector.section("entropy", {"window": window, "bins": bins}) as meta:
        entropy_value = float(entropy(window_prices, bins=bins))
        delta_entropy_value = float(delta_entropy(prices, window=window))
        meta["entropy"] = entropy_value
        meta["delta_entropy"] = delta_entropy_value

    with collector.section(
        "ricci-curvature", {"window": window, "delta": delta}
    ) as meta:
        graph = build_price_graph(window_prices, delta=delta)
        curvature = float(mean_ricci(graph))
        meta["mean_ricci"] = curvature
        meta["nodes"] = int(graph.number_of_nodes())
        meta["edges"] = int(graph.number_of_edges())

    report = collector.build_report()
    summary = {
        "order_parameter": order_parameter,
        "entropy": entropy_value,
        "delta_entropy": delta_entropy_value,
        "mean_ricci": curvature,
    }

    return {
        "scenario": "analytics_pipeline",
        "dataset": dataset_info,
        "parameters": {
            "price_column": price_column,
            "window": window,
            "bins": bins,
            "delta": delta,
        },
        "summary": summary,
        "profiling": report.to_dict(),
        "human_readable": report.summary(),
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Profile representative TradePulse workflows and output structured metrics.",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=_default_dataset_path(),
        help="Path to the CSV dataset (default: repository sample).",
    )
    parser.add_argument(
        "--price-column",
        default="close",
        help="Column to use as the price series.",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=256,
        help="Window size for sliding computations.",
    )
    parser.add_argument(
        "--bins",
        type=int,
        default=64,
        help="Number of histogram bins for entropy calculation.",
    )
    parser.add_argument(
        "--delta",
        type=float,
        default=0.05,
        help="Graph delta parameter for Ricci curvature analysis.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the profiling result as JSON.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        result = profile_analytics_pipeline(
            data_path=args.data,
            price_column=args.price_column,
            window=args.window,
            bins=args.bins,
            delta=args.delta,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}")
        return 1

    print(result["human_readable"])
    print()
    payload = json.dumps(
        {k: v for k, v in result.items() if k != "human_readable"},
        indent=2,
        sort_keys=True,
    )
    print(payload)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
