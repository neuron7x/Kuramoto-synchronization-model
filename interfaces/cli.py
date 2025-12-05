# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Command-line interface orchestrating research and operations workflows.

The CLI glues together ingestion, indicator computation, backtesting, and live
trading bootstrap flows. It is the operational entry point referenced in
``docs/quickstart.md`` and ``docs/runbook_live_trading.md`` and emits tracing
metadata according to ``docs/monitoring.md``. Each command surfaces the
governance requirements outlined in ``docs/documentation_governance.md`` by
exposing structured outputs and traceparent propagation.

**What the CLI provides**

* Deterministic signal generation utilities mirroring the educational notebooks
  described in ``docs/examples/README.md``.
* Backtesting entry points that wrap :func:`backtest.engine.walk_forward` and
  export reports compatible with the runbooks in ``docs/runbook_release_validation.md``.
* Bootstrap helpers for live execution that enforce trace-context propagation
  so distributed systems monitoring can correlate CLI actions with downstream
  services.

**Usage expectations**

Operators should treat the CLI as the canonical automation surface: configuration
is pulled from YAML files described in ``docs/scenarios.md``, secrets are loaded
through the governance policies in ``SECURITY.md``, and tracing integrates with
``observability.tracing`` to maintain production-grade audit trails.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backtest.engine import walk_forward
from core.data.ingestion import DataIngestor
from core.indicators.entropy import delta_entropy, entropy
from core.indicators.hurst import hurst_exponent
from core.indicators.kuramoto import compute_phase, kuramoto_order
from core.indicators.ricci import build_price_graph, mean_ricci
from core.phase.detector import composite_transition, phase_flags
from observability.tracing import activate_traceparent, current_traceparent, get_tracer


def signal_from_indicators(
    prices: np.ndarray,
    window: int = 200,
    *,
    max_workers: int | None = None,
    ricci_delta: float = 0.005,
) -> np.ndarray:
    """Derive a regime-aware trading signal from synchrony and entropy features.

    Args:
        prices: One-dimensional price series.
        window: Lookback window for phase, entropy, and curvature indicators.
        max_workers: Optional thread pool size for indicator fan-out. ``None``
            defaults to three workers covering entropy, delta entropy, and Ricci
            curvature. Values ``<= 1`` disable parallelism.
        ricci_delta: Step size used when constructing the Ricci price graph.

    Returns:
        np.ndarray: Array of integer signals in ``{-1, 0, 1}`` aligned with
        ``prices``.

    Examples:
        >>> prices = np.linspace(100, 105, 256)
        >>> signals = signal_from_indicators(prices, window=32)
        >>> set(np.unique(signals)).issubset({-1, 0, 1})
        True

    Notes:
        This routine mirrors the composite signal recipe in ``docs/quickstart.md``
        and is meant for demonstrations rather than production alpha generation.
    """
    n = len(prices)
    sig = np.zeros(n, dtype=int)
    worker_count = max_workers if max_workers is not None else 3
    executor: ThreadPoolExecutor | None = None
    if worker_count is not None and worker_count > 1:
        executor = ThreadPoolExecutor(
            max_workers=worker_count, thread_name_prefix="signal-indicators"
        )

    def _compute_ricci(window_prices: np.ndarray) -> float:
        graph = build_price_graph(window_prices, delta=ricci_delta)
        return mean_ricci(graph)

    try:
        for t in range(window, n):
            prefix = prices[: t + 1]
            window_prices = prefix[-window:]

            phases = compute_phase(prefix)
            R = kuramoto_order(phases[-window:])

            if executor is None:
                H = entropy(window_prices)
                dH = delta_entropy(prefix, window=window)
                kappa = _compute_ricci(window_prices)
            else:
                futures = {
                    "entropy": executor.submit(entropy, window_prices),
                    "delta_entropy": executor.submit(
                        delta_entropy, prefix, window=window
                    ),
                    "ricci": executor.submit(_compute_ricci, window_prices),
                }
                H = futures["entropy"].result()
                dH = futures["delta_entropy"].result()
                kappa = futures["ricci"].result()

            comp = composite_transition(R, dH, kappa, H)
            if comp > 0.15 and dH < 0 and kappa < 0:
                sig[t] = 1
            elif comp < -0.15 and dH > 0:
                sig[t] = -1
            else:
                sig[t] = sig[t - 1]
    finally:
        if executor is not None:
            executor.shutdown(wait=True)
    return sig


def _load_yaml() -> Any:
    """Return the PyYAML module, raising a helpful error when missing.

    Returns:
        Any: The imported PyYAML module.

    Raises:
        RuntimeError: If PyYAML is not installed.
    """

    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised in minimal envs
        raise RuntimeError(
            "YAML configuration support requires the 'PyYAML' package. "
            "Install it via 'pip install PyYAML' or omit the --config option."
        ) from exc
    return yaml


def _apply_config(args: argparse.Namespace) -> argparse.Namespace:
    """Merge configuration overrides from a YAML file into CLI arguments.

    Args:
        args: Namespace produced by :mod:`argparse`.

    Returns:
        argparse.Namespace: Updated namespace reflecting YAML overrides.
    """

    config_path = getattr(args, "config", None)
    if not config_path:
        return args

    yaml = _load_yaml()
    path = Path(config_path)
    config: dict[str, Any] = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)
            if isinstance(loaded, Mapping):
                config = dict(loaded)

    indicators = config.get("indicators", {})
    if isinstance(indicators, Mapping):
        for key in ("window", "bins", "delta"):
            if key in indicators:
                setattr(args, key, indicators[key])

    data_section = config.get("data", {})
    if (
        isinstance(data_section, Mapping)
        and "path" in data_section
        and not getattr(args, "csv", None)
    ):
        args.csv = data_section["path"]

    return args


def _make_data_ingestor(csv_path: str | None = None) -> DataIngestor:
    """Return a :class:`DataIngestor` constrained to directories derived from ``csv_path``.

    Args:
        csv_path: Optional CSV location used to infer allowed directories.

    Returns:
        DataIngestor: Configured ingestor with restricted roots per
        ``docs/documentation_governance.md``.
    """

    allowed = None
    if csv_path:
        allowed = [Path(csv_path).expanduser().resolve(strict=False).parent]
    return DataIngestor(allowed_roots=allowed)


def _enrich_with_trace(payload: dict[str, Any]) -> dict[str, Any]:
    """Attach the active traceparent to ``payload`` when available."""
    traceparent = current_traceparent()
    if not traceparent:
        return payload
    enriched = dict(payload)
    enriched["traceparent"] = traceparent
    return enriched


def cmd_analyze(args):
    """Compute indicator diagnostics for a CSV price series.

    Args:
        args: Parsed :class:`argparse.Namespace` with CLI options. Expected
            attributes include ``csv``, ``price_col``, ``window``, ``bins``,
            ``delta``, ``gpu``, and ``traceparent``.

    Returns:
        None: Writes a JSON payload to stdout.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        ValueError: If required columns are missing or data is invalid.
        Exception: For other unexpected errors during analysis.

    Notes:
        Outputs a JSON payload suitable for audit pipelines described in
        ``docs/documentation_governance.md``. GPU acceleration is attempted when
        the ``--gpu`` flag is set and the CuPy-backed implementation is available.
    """
    args = _apply_config(args)

    # Validate CSV file exists
    csv_path = Path(args.csv).expanduser().resolve()
    if not csv_path.exists():
        print(
            json.dumps(
                {
                    "error": "FileNotFoundError",
                    "message": f"CSV file not found: {csv_path}",
                    "suggestion": "Check that the file path is correct and the file exists.",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(
            json.dumps(
                {
                    "error": type(e).__name__,
                    "message": f"Failed to read CSV file: {str(e)}",
                    "suggestion": "Ensure the file is a valid CSV with proper formatting.",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate required columns
    if args.price_col not in df.columns:
        print(
            json.dumps(
                {
                    "error": "ValueError",
                    "message": f"Column '{args.price_col}' not found in CSV",
                    "available_columns": list(df.columns),
                    "suggestion": f"Use --price-col to specify the correct column name, or ensure your CSV has a '{args.price_col}' column.",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    prices = df[args.price_col].to_numpy()

    # Validate data quality
    if len(prices) < args.window:
        print(
            json.dumps(
                {
                    "error": "ValueError",
                    "message": f"Insufficient data: {len(prices)} rows < window size {args.window}",
                    "suggestion": f"Provide a dataset with at least {args.window} rows or reduce the --window parameter.",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    # Check for NaN values
    nan_count = np.isnan(prices).sum()
    if nan_count > 0:
        print(
            json.dumps(
                {
                    "warning": "Data contains NaN values",
                    "nan_count": int(nan_count),
                    "total_rows": len(prices),
                    "suggestion": "Consider cleaning your data before analysis.",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        # Remove NaN values
        prices = prices[~np.isnan(prices)]

    # Check for constant prices
    if np.std(prices) == 0:
        print(
            json.dumps(
                {
                    "error": "ValueError",
                    "message": "Price data has no variation (all values are constant)",
                    "suggestion": "Verify that your data contains actual price movements.",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        from core.indicators.kuramoto import compute_phase_gpu

        phases = (
            compute_phase_gpu(prices)
            if getattr(args, "gpu", False)
            else compute_phase(prices)
        )
        R = kuramoto_order(phases[-args.window :])
        H = entropy(prices[-args.window :], bins=args.bins)
        dH = delta_entropy(prices, window=args.window, bins_range=(10, 50))
        kappa = mean_ricci(build_price_graph(prices[-args.window :], delta=args.delta))
        Hs = hurst_exponent(prices[-args.window :])
        phase = phase_flags(R, dH, kappa, H)

        print(
            json.dumps(
                _enrich_with_trace(
                    {
                        "R": float(R),
                        "H": float(H),
                        "delta_H": float(dH),
                        "kappa_mean": float(kappa),
                        "Hurst": float(Hs),
                        "phase": phase,
                        "metadata": {
                            "window_size": args.window,
                            "data_points": len(prices),
                            "bins": args.bins,
                            "delta": args.delta,
                            "gpu_enabled": getattr(args, "gpu", False),
                        },
                    }
                ),
                indent=2,
            )
        )
    except Exception as e:
        print(
            json.dumps(
                {
                    "error": type(e).__name__,
                    "message": f"Error computing indicators: {str(e)}",
                    "suggestion": "Check that your data is valid and all dependencies are properly installed.",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        sys.exit(1)


def cmd_backtest(args):
    """Run a walk-forward backtest using the indicator composite signal.

    Args:
        args: Parsed :class:`argparse.Namespace` with options ``csv``,
            ``price_col``, ``window``, ``fee``, ``config``, ``gpu``, and
            ``traceparent``.

    Returns:
        None: Emits JSON summary statistics to stdout.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        ValueError: If data is insufficient or invalid.
        Exception: For other unexpected errors during backtesting.

    Notes:
        Returns backtest statistics in JSON form to comply with
        ``docs/performance.md`` reporting guidance. The walk-forward engine is the
        same implementation invoked by automation in ``docs/runbook_live_trading.md``.
    """
    args = _apply_config(args)

    # Validate CSV file
    csv_path = Path(args.csv).expanduser().resolve()
    if not csv_path.exists():
        print(
            json.dumps(
                {
                    "error": "FileNotFoundError",
                    "message": f"CSV file not found: {csv_path}",
                    "suggestion": "Check that the file path is correct and the file exists.",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(
            json.dumps(
                {
                    "error": type(e).__name__,
                    "message": f"Failed to read CSV file: {str(e)}",
                    "suggestion": "Ensure the file is a valid CSV with proper formatting.",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate column exists
    if args.price_col not in df.columns:
        print(
            json.dumps(
                {
                    "error": "ValueError",
                    "message": f"Column '{args.price_col}' not found in CSV",
                    "available_columns": list(df.columns),
                    "suggestion": "Use --price-col to specify the correct column name.",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    prices = df[args.price_col].to_numpy()

    # Data quality checks
    if len(prices) < args.window * 2:
        print(
            json.dumps(
                {
                    "error": "ValueError",
                    "message": f"Insufficient data for backtesting: {len(prices)} rows < {args.window * 2} (2x window)",
                    "suggestion": f"Provide more data or reduce the --window parameter. Recommended: at least {args.window * 3} rows.",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    # Remove NaN values
    nan_count = np.isnan(prices).sum()
    if nan_count > 0:
        print(
            json.dumps(
                {
                    "warning": f"Removed {nan_count} NaN values from data",
                    "original_length": len(prices),
                    "cleaned_length": len(prices) - nan_count,
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        prices = prices[~np.isnan(prices)]

    try:
        sig = signal_from_indicators(prices, window=args.window)
        res = walk_forward(prices, lambda _: sig, fee=args.fee)

        # Calculate additional statistics
        sharpe = res.sharpe_ratio if hasattr(res, "sharpe_ratio") else None
        win_rate = res.win_rate if hasattr(res, "win_rate") else None

        out = {
            "pnl": res.pnl,
            "max_dd": res.max_dd,
            "trades": res.trades,
            "metadata": {
                "window_size": args.window,
                "fee": args.fee,
                "data_points": len(prices),
            },
        }

        if sharpe is not None:
            out["sharpe_ratio"] = sharpe
        if win_rate is not None:
            out["win_rate"] = win_rate

        print(json.dumps(_enrich_with_trace(out), indent=2))

    except Exception as e:
        print(
            json.dumps(
                {
                    "error": type(e).__name__,
                    "message": f"Error during backtesting: {str(e)}",
                    "suggestion": "Verify data quality and ensure all indicators can be computed.",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        sys.exit(1)


def cmd_live(args):
    """Bootstrap the live trading runner with risk and tracing configuration.

    Args:
        args: Parsed :class:`argparse.Namespace` including ``config``, ``venue``,
            ``state_dir``, ``cold_start``, ``metrics_port``, and ``traceparent``
            attributes.

    Returns:
        None: Executes the live runner with side effects only.

    Notes:
        Delegates to :class:`interfaces.live_runner.LiveTradingRunner`, ensuring
        the kill-switch and telemetry expectations from ``docs/admin_remote_control.md``
        and ``docs/monitoring.md`` are met. Raises :class:`FileNotFoundError` if
        the configuration file is missing.
    """
    from interfaces.live_runner import LiveTradingRunner

    config_path = Path(args.config).expanduser() if args.config else None
    venues = tuple(args.venue or ()) or None
    state_dir = Path(args.state_dir).expanduser() if args.state_dir else None
    metrics_port = args.metrics_port
    cold_start = bool(args.cold_start)

    runner = LiveTradingRunner(
        config_path,
        venues=venues,
        state_dir_override=state_dir,
        metrics_port=metrics_port,
    )
    runner.run(cold_start=cold_start)


def _run_with_trace_context(cmd_name: str, args: argparse.Namespace) -> None:
    """Execute a CLI command with traceparent propagation.

    Args:
        cmd_name: Name of the command for tracer labelling.
        args: Parsed arguments namespace.

    Returns:
        None.

    Notes:
        This helper ensures every CLI invocation participates in distributed
        tracing as outlined in ``docs/monitoring.md``.
    """
    tracer = get_tracer("tradepulse.cli")
    inbound = getattr(args, "traceparent", None) or os.environ.get(
        "TRADEPULSE_TRACEPARENT"
    )
    with activate_traceparent(inbound):
        with tracer.start_as_current_span(
            f"cli.{cmd_name}",
            attributes={"cli.command": cmd_name},
        ):
            outbound = current_traceparent()
            previous = os.environ.get("TRADEPULSE_TRACEPARENT")
            if outbound:
                os.environ["TRADEPULSE_TRACEPARENT"] = outbound
            try:
                args.func(args)
            finally:
                if outbound:
                    if previous is None:
                        os.environ.pop("TRADEPULSE_TRACEPARENT", None)
                    else:
                        os.environ["TRADEPULSE_TRACEPARENT"] = previous


def main():
    """Main entry point for the TradePulse CLI.

    Provides three main commands:
    - analyze: Compute market indicators from price data
    - backtest: Run walk-forward backtesting with indicator signals
    - live: Launch live trading with risk management
    """
    p = argparse.ArgumentParser(
        prog="tradepulse",
        description="TradePulse - Advanced Algorithmic Trading Framework with Geometric Market Indicators",
        epilog="""
Examples:
  # Analyze a CSV file with default settings
  tradepulse analyze --csv prices.csv

  # Analyze with custom window and column
  tradepulse analyze --csv data.csv --price-col close --window 100

  # Run a backtest on historical data
  tradepulse backtest --csv historical.csv --fee 0.001

  # Launch live trading (requires configuration)
  tradepulse live --config configs/live/binance.toml

For detailed documentation, visit: https://github.com/neuron7x/TradePulse
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(
        dest="cmd", required=True, help="Available commands", metavar="COMMAND"
    )

    trace_arg_help = "W3C traceparent header used to join an existing distributed trace"

    # Analyze command
    pa = sub.add_parser(
        "analyze",
        help="Compute geometric and technical indicators from price data",
        description="""
Analyze market data using TradePulse's suite of geometric indicators including:
- Kuramoto Order Parameter (phase synchronization)
- Shannon Entropy (information content)
- Hurst Exponent (long-term memory)
- Ricci Curvature (geometric manifold properties)

Outputs comprehensive JSON analysis suitable for pipelines and auditing.
        """,
        epilog="""
Examples:
  # Basic analysis with default settings
  tradepulse analyze --csv prices.csv

  # Use a custom price column and window size
  tradepulse analyze --csv data.csv --price-col close --window 100

  # Enable GPU acceleration for faster processing
  tradepulse analyze --csv large_dataset.csv --gpu

  # Use configuration from YAML file
  tradepulse analyze --csv prices.csv --config settings.yaml

Output is JSON-formatted and includes:
  - R: Kuramoto order parameter (0-1, higher = more synchronized)
  - H: Shannon entropy
  - delta_H: Entropy change over window
  - kappa_mean: Mean Ricci curvature
  - Hurst: Hurst exponent (>0.5 = trending, <0.5 = mean-reverting)
  - phase: Detected market phase
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pa.add_argument(
        "--csv", required=True, help="Path to CSV file containing price data (required)"
    )
    pa.add_argument(
        "--price-col",
        default="price",
        help="Name of the column containing price values (default: 'price')",
    )
    pa.add_argument(
        "--window",
        type=int,
        default=200,
        help="Analysis window size in periods (default: 200, recommended: 100-300)",
    )
    pa.add_argument(
        "--bins",
        type=int,
        default=30,
        help="Number of bins for entropy calculation (default: 30)",
    )
    pa.add_argument(
        "--delta",
        type=float,
        default=0.005,
        help="Step size for Ricci curvature calculation (default: 0.005)",
    )
    pa.add_argument(
        "--config", help="Path to YAML configuration file (optional)", default=None
    )
    pa.add_argument(
        "--gpu",
        action="store_true",
        help="Enable GPU acceleration for phase computation (requires CUDA)",
    )
    pa.add_argument("--traceparent", default=None, help=trace_arg_help)
    pa.set_defaults(func=cmd_analyze)

    # Backtest command
    pb = sub.add_parser(
        "backtest",
        help="Run walk-forward backtesting with indicator-based signals",
        description="""
Execute a walk-forward backtest using composite indicator signals.
The backtest simulates trading based on Kuramoto synchronization,
entropy measures, and geometric curvature indicators.

Outputs performance metrics including PnL, max drawdown, and trade count.
        """,
        epilog="""
Examples:
  # Run backtest with default settings
  tradepulse backtest --csv historical.csv

  # Specify custom fee and window
  tradepulse backtest --csv data.csv --fee 0.001 --window 150

  # Use custom price column from OHLCV data
  tradepulse backtest --csv ohlcv.csv --price-col close

Output metrics:
  - pnl: Total profit/loss
  - max_dd: Maximum drawdown percentage
  - trades: Number of executed trades
  - sharpe_ratio: Risk-adjusted return (if available)
  - win_rate: Percentage of profitable trades (if available)
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pb.add_argument(
        "--csv",
        required=True,
        help="Path to CSV file containing historical price data (required)",
    )
    pb.add_argument(
        "--price-col",
        default="price",
        help="Name of the column containing price values (default: 'price')",
    )
    pb.add_argument(
        "--window",
        type=int,
        default=200,
        help="Lookback window for indicator calculation (default: 200)",
    )
    pb.add_argument(
        "--fee",
        type=float,
        default=0.0005,
        help="Transaction fee as a fraction (default: 0.0005 = 0.05%%)",
    )
    pb.add_argument(
        "--config", help="Path to YAML configuration file (optional)", default=None
    )
    pb.add_argument(
        "--gpu", action="store_true", help="Enable GPU acceleration (requires CUDA)"
    )
    pb.add_argument("--traceparent", default=None, help=trace_arg_help)
    pb.set_defaults(func=cmd_backtest)

    # Live trading command
    pl = sub.add_parser(
        "live",
        help="Launch live trading with risk management and monitoring",
        description="""
Bootstrap the live trading system with comprehensive risk controls:
- Position limits and exposure caps
- Circuit breakers and kill switches
- Real-time monitoring and alerting
- State reconciliation and recovery

Requires proper configuration including venue credentials and risk parameters.
        """,
        epilog="""
Examples:
  # Start with default configuration
  tradepulse live

  # Use custom configuration file
  tradepulse live --config configs/live/binance.toml

  # Restrict to specific venues
  tradepulse live --venue binance --venue coinbase

  # Cold start (skip position reconciliation)
  tradepulse live --config prod.toml --cold-start

  # Expose Prometheus metrics
  tradepulse live --metrics-port 9090

IMPORTANT: Always test with paper trading before using real funds.
Configure risk limits appropriately in your TOML configuration file.
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pl.add_argument(
        "--config",
        default="configs/live/default.toml",
        help="Path to TOML configuration file describing venues and risk limits (default: configs/live/default.toml)",
    )
    pl.add_argument(
        "--venue",
        action="append",
        default=None,
        help="Restrict execution to specific venue(s). Can be specified multiple times. Example: --venue binance --venue coinbase",
    )
    pl.add_argument(
        "--state-dir",
        default=None,
        help="Override the state directory for OMS persistence (optional)",
    )
    pl.add_argument(
        "--cold-start",
        action="store_true",
        help="Skip position reconciliation on startup (use with caution)",
    )
    pl.add_argument(
        "--metrics-port",
        type=int,
        default=None,
        help="Port to expose Prometheus metrics on (optional)",
    )
    pl.add_argument("--traceparent", default=None, help=trace_arg_help)
    pl.set_defaults(func=cmd_live)

    # Parse and execute
    try:
        args = p.parse_args()
        _run_with_trace_context(args.cmd, args)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting gracefully...", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(
            json.dumps(
                {
                    "error": type(e).__name__,
                    "message": str(e),
                    "suggestion": "Run 'tradepulse COMMAND --help' for usage information.",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
