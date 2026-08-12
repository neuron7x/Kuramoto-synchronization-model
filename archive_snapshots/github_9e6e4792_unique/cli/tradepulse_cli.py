"""TradePulse CLI exposing ingest/backtest/optimize/exec/report workflows."""

from __future__ import annotations

import hashlib
import importlib
import itertools
import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Tuple

import click
import numpy as np
import pandas as pd

from analytics.regime.src.core import tradepulse_v21 as v21
from core.config.cli_models import (
    BacktestConfig,
    DeploymentConfig,
    ExecConfig,
    FeatureFrameSourceConfig,
    FeatureParityConfig,
    FeatureParitySpecConfig,
    IngestConfig,
    OptimizeConfig,
    ReportConfig,
    StrategyConfig,
)
from core.config.template_manager import ConfigTemplateManager
from core.data.feature_catalog import FeatureCatalog
from core.data.feature_store import OnlineFeatureStore
from core.data.parity import (
    FeatureParityCoordinator,
    FeatureParityError,
    FeatureParityReport,
    FeatureParitySpec,
)
from core.data.versioning import DataVersionManager
from core.reporting import (
    generate_markdown_report,
    render_markdown_to_html,
    render_markdown_to_pdf,
)
from core.strategies import (
    FETE,
    FETEBacktestEngine,
    FETEConfig,
    PaperTradingAccount,
    RiskGuard,
)
from core.utils.dataframe_io import (
    MissingParquetDependencyError,
    dataframe_to_parquet_bytes,
    read_dataframe,
)
from execution.watchdog import Watchdog

DEFAULT_TEMPLATES_DIR = Path("configs/templates")


class CLIError(click.ClickException):
    """Base class for typed CLI failures with deterministic exit codes."""

    exit_code = 1


class ConfigError(CLIError):
    exit_code = 2


class ArtifactError(CLIError):
    exit_code = 3


class ComputeError(CLIError):
    exit_code = 4


class ParityError(CLIError):
    exit_code = 5


@contextmanager
def step_logger(command: str, name: str) -> Iterator[None]:
    """Context manager emitting deterministic start/stop step logs."""

    click.echo(f"[{command}] ▶ {name}")
    start = time.perf_counter()
    try:
        yield
    except Exception:
        duration = time.perf_counter() - start
        click.echo(f"[{command}] ✖ {name} ({duration:.2f}s)", err=True)
        raise
    else:
        duration = time.perf_counter() - start
        click.echo(f"[{command}] ✓ {name} ({duration:.2f}s)")


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _existing_digest(path: Path) -> str | None:
    if not path.exists():
        return None
    return _hash_bytes(path.read_bytes())


def _write_bytes(
    destination: Path, payload: bytes, *, command: str
) -> Tuple[str, bool]:
    existing = _existing_digest(destination)
    digest = _hash_bytes(payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if existing == digest:
        click.echo(f"[{command}] • {destination} unchanged (sha256={digest})")
        return digest, False
    destination.write_bytes(payload)
    click.echo(f"[{command}] • wrote {destination} (sha256={digest})")
    return digest, True


def _resolve_path(base: Path, target: Path | str) -> Path:
    candidate = Path(target)
    if candidate.is_absolute():
        return candidate
    return (base / candidate).resolve()


def _resolve_kubectl_binary(base: Path, target: Path | str) -> Path:
    candidate = Path(target)
    if candidate.is_absolute():
        return candidate

    target_str = str(target)
    has_dir_component = any(
        sep and sep in target_str for sep in (os.sep, os.path.altsep)
    )
    if has_dir_component:
        return (base / candidate).resolve()

    resolved = shutil.which(target_str)
    if resolved is not None:
        return Path(resolved)

    return candidate


def _resolve_overlay_path(config_path: Path, cfg: DeploymentConfig) -> Path:
    manifests = cfg.manifests
    if manifests.path is not None:
        return _resolve_path(config_path.parent, manifests.path)

    name = manifests.name
    if name is None:
        name = DEFAULT_OVERLAY_NAMES.get(cfg.environment.value, cfg.environment.value)
    root = _resolve_path(config_path.parent, manifests.root)
    return (root / name).resolve()


def _build_kubectl_command(
    binary: Path,
    cfg: DeploymentConfig,
    *args: str,
) -> list[str]:
    command = [str(binary)]
    kubectl_cfg = cfg.kubectl
    if kubectl_cfg.context:
        command.extend(["--context", kubectl_cfg.context])
    if kubectl_cfg.namespace:
        command.extend(["--namespace", kubectl_cfg.namespace])
    if kubectl_cfg.extra_args:
        command.extend(kubectl_cfg.extra_args)
    command.extend(args)
    return command


def _run_kubectl(
    command_name: str,
    binary: Path,
    cfg: DeploymentConfig,
    env: dict[str, str],
    *args: str,
) -> None:
    command = _build_kubectl_command(binary, cfg, *args)
    click.echo(f"[{command_name}] $ {shlex.join(command)}")
    try:
        subprocess.run(command, check=True, env=env)
    except FileNotFoundError as exc:
        raise ComputeError(f"kubectl binary '{binary}' not found") from exc
    except subprocess.CalledProcessError as exc:
        raise ComputeError(
            f"kubectl command failed with exit code {exc.returncode}"
        ) from exc


def _load_callable(entrypoint: str) -> Callable[..., Any]:
    module_name, _, attr_path = entrypoint.partition(":")
    if not attr_path:
        raise ConfigError("Entrypoint must be in '<module>:<callable>' form")
    module = importlib.import_module(module_name)
    target: Any = module
    for part in attr_path.split("."):
        if not hasattr(target, part):
            raise ConfigError(f"Entrypoint '{entrypoint}' is invalid")
        target = getattr(target, part)
    if not callable(target):
        raise ConfigError(f"Entrypoint '{entrypoint}' does not reference a callable")
    return target


def _ensure_manager(ctx: click.Context, templates_dir: Path) -> ConfigTemplateManager:
    try:
        manager = ConfigTemplateManager(templates_dir)
    except FileNotFoundError as exc:  # pragma: no cover - user misconfiguration
        raise ConfigError(str(exc)) from exc
    ctx.ensure_object(dict)
    ctx.obj["manager"] = manager
    return manager


def _get_manager(ctx: click.Context) -> ConfigTemplateManager:
    manager = ctx.obj.get("manager")
    if manager is None:
        manager = _ensure_manager(ctx, DEFAULT_TEMPLATES_DIR)
    return manager


def _load_prices(cfg: IngestConfig | BacktestConfig | ExecConfig) -> pd.DataFrame:
    data_cfg = getattr(cfg, "source", None)
    if data_cfg is None:
        data_cfg = getattr(cfg, "data", None)
    if data_cfg is None:
        raise ConfigError("Configuration does not define a data source")
    if data_cfg.kind not in {"csv", "parquet"}:
        raise ConfigError(f"Unsupported data source '{data_cfg.kind}'")
    if not Path(data_cfg.path).exists():
        raise ArtifactError(f"Data source {data_cfg.path} does not exist")
    if data_cfg.kind == "csv":
        frame = pd.read_csv(data_cfg.path)
    else:
        try:
            frame = read_dataframe(Path(data_cfg.path), allow_json_fallback=False)
        except MissingParquetDependencyError as exc:
            raise ArtifactError(
                "Parquet sources require either pyarrow or polars. Install the 'tradepulse[feature_store]' extra."
            ) from exc
    if data_cfg.timestamp_field not in frame.columns:
        raise ConfigError("Timestamp column missing from data source")
    if data_cfg.value_field not in frame.columns:
        raise ConfigError("Value column missing from data source")
    timestamp_field = data_cfg.timestamp_field
    series = frame[timestamp_field]
    if not series.is_monotonic_increasing:
        # ``sort_values`` performs an ``argsort`` even when the data is already
        # ordered. Large backtests typically ingest pre-sorted market data, so
        # we avoid the expensive rearrangement when the monotonicity invariant
        # already holds.
        frame = frame.sort_values(timestamp_field)
    index = frame.index
    if not (isinstance(index, pd.RangeIndex) and index.start == 0 and index.step == 1):
        frame = frame.reset_index(drop=True)
    return frame


def _load_feature_frame(source: FeatureFrameSourceConfig) -> pd.DataFrame:
    if not source.path.exists():
        raise ArtifactError(f"Offline feature snapshot {source.path} does not exist")
    fmt = source.format
    if fmt == "auto":
        suffix = source.path.suffix.lower()
        fmt = "parquet" if suffix == ".parquet" else "csv"
    if fmt == "csv":
        frame = pd.read_csv(source.path)
    elif fmt == "parquet":
        try:
            frame = read_dataframe(source.path, allow_json_fallback=False)
        except MissingParquetDependencyError as exc:
            raise ArtifactError(
                "Parquet sources require either pyarrow or polars. Install the 'tradepulse[feature_store]' extra."
            ) from exc
    else:  # pragma: no cover - guarded by Pydantic literal
        raise ConfigError(f"Unsupported feature source format '{fmt}'")
    return frame


def _load_fete_inputs(
    csv_path: Path, price_col: str, prob_col: str | None
) -> tuple[np.ndarray, np.ndarray]:
    if not csv_path.exists():
        raise ArtifactError(f"Data source {csv_path} does not exist")
    frame = pd.read_csv(csv_path)
    if price_col not in frame.columns:
        raise ConfigError(f"Price column '{price_col}' not found in CSV")
    prices = frame[price_col].to_numpy(dtype=float, copy=False)
    if prices.size < 3:
        raise ConfigError("CSV must contain at least three price observations")
    if prob_col:
        if prob_col not in frame.columns:
            raise ConfigError(f"Probability column '{prob_col}' not found in CSV")
        probs = frame[prob_col].to_numpy(dtype=float, copy=False)
    else:
        rng = np.random.default_rng(42)
        time_index = np.arange(prices.size)
        probs = (
            0.5
            + 0.15 * np.sin(time_index / 50.0)
            + rng.normal(0.0, 0.08, size=prices.size)
        )
    probs = np.clip(probs, 0.0, 1.0)
    return prices, probs


def _build_parity_spec(spec_cfg: FeatureParitySpecConfig) -> FeatureParitySpec:
    return FeatureParitySpec(
        feature_view=spec_cfg.feature_view,
        entity_columns=tuple(spec_cfg.entity_columns),
        timestamp_column=spec_cfg.timestamp_column,
        timestamp_granularity=spec_cfg.timestamp_granularity,
        numeric_tolerance=spec_cfg.numeric_tolerance,
        max_clock_skew=spec_cfg.max_clock_skew,
        allow_schema_evolution=spec_cfg.allow_schema_evolution,
        value_columns=(
            None if spec_cfg.value_columns is None else tuple(spec_cfg.value_columns)
        ),
    )


def _resolve_strategy(
    strategy_cfg: StrategyConfig,
) -> Callable[[np.ndarray], np.ndarray]:
    fn = _load_callable(strategy_cfg.entrypoint)

    def _wrapped(prices: np.ndarray) -> np.ndarray:
        result = fn(prices, **strategy_cfg.parameters)
        return np.asarray(result, dtype=float)

    return _wrapped


def _write_frame(
    frame: pd.DataFrame, destination: Path, *, command: str = "cli"
) -> str:
    suffix = destination.suffix.lower()
    if suffix in {".csv", ""}:
        payload = frame.to_csv(index=False).encode("utf-8")
    elif suffix == ".parquet":
        try:
            payload = dataframe_to_parquet_bytes(frame, index=False)
        except MissingParquetDependencyError as exc:
            raise ConfigError(
                "Writing parquet outputs requires either pyarrow or polars. Install the 'tradepulse[feature_store]' extra."
            ) from exc
    else:
        raise ConfigError(f"Unsupported destination format '{suffix}'")
    digest, _ = _write_bytes(destination, payload, command=command)
    return digest


def _write_json(destination: Path, payload: Dict[str, Any], *, command: str) -> str:
    data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    digest, _ = _write_bytes(destination, data, command=command)
    return digest


def _write_text(destination: Path, text: str, *, command: str) -> str:
    digest, _ = _write_bytes(destination, text.encode("utf-8"), command=command)
    return digest


def _load_returns_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    ts_col = None
    for candidate in ("date", "ts", "timestamp"):
        if candidate in frame.columns:
            ts_col = candidate
            break
    if ts_col is not None:
        frame[ts_col] = pd.to_datetime(frame[ts_col])
        frame = frame.set_index(ts_col).sort_index()
    return frame


def _load_feature_dataset(path: Path) -> v21.StrictCausalFeatures:
    frame = pd.read_csv(path)
    ts_col = None
    for candidate in ("date", "ts", "timestamp"):
        if candidate in frame.columns:
            ts_col = candidate
            break
    if ts_col is not None:
        frame[ts_col] = pd.to_datetime(frame[ts_col])
        frame = frame.set_index(ts_col).sort_index()
    if "y" not in frame.columns:
        raise ComputeError("Features CSV must contain a 'y' label column.")
    feature_cols = [
        c
        for c in ("dr", "ricci_mean", "topo_intensity", "causal_strength")
        if c in frame.columns
    ]
    if len(feature_cols) != 4:
        raise ComputeError(
            "Features CSV must include dr, ricci_mean, topo_intensity and causal_strength columns."
        )
    features = frame[feature_cols]
    labels = frame["y"].astype(int).to_numpy()
    return v21.StrictCausalFeatures(features=features, labels=labels)


@click.group(
    epilog="""
Examples:
  # Generate a configuration template
  tradepulse_cli ingest --generate-config --template-output ingest.yaml

  # Run data ingestion from a config file
  tradepulse_cli ingest --config my_ingest.yaml

  # Run a backtest with output
  tradepulse_cli backtest --config backtest.yaml --output table

  # Generate shell completions
  tradepulse_cli completion bash

For more information, visit: https://github.com/neuron7x/TradePulse
"""
)
@click.option(
    "--templates-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_TEMPLATES_DIR,
    help="Directory containing YAML configuration templates (default: configs/templates).",
)
@click.pass_context
def cli(ctx: click.Context, templates_dir: Path) -> None:
    """TradePulse orchestration CLI.

    A comprehensive command-line tool for managing trading workflows including
    data ingestion, backtesting, optimization, live execution, and reporting.

    Use --help on any command to see detailed usage information and examples.
    """

    _ensure_manager(ctx, templates_dir)


@cli.command()
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
def completion(shell: str) -> None:
    """Generate shell completion snippet for the requested shell.

    This enables tab-completion for TradePulse CLI commands, options,
    and arguments in your terminal.

    \b
    Example:
      # For bash (add to ~/.bashrc)
      tradepulse_cli completion bash

      # For zsh (add to ~/.zshrc)
      tradepulse_cli completion zsh

      # For fish (add to ~/.config/fish/config.fish)
      tradepulse_cli completion fish
    """

    prog_name = Path(sys.argv[0]).name or "tradepulse_cli"
    env_prefix = prog_name.replace("-", "_").upper()
    env_var = f"{env_prefix}_COMPLETE"
    if shell == "bash":
        snippet = f'eval "$({env_var}=bash_source {prog_name})"'
    elif shell == "zsh":
        snippet = f'eval "$({env_var}=zsh_source {prog_name})"'
    else:  # fish
        snippet = f"eval (env {env_var}=fish_source {prog_name})"
    click.echo(f"# Add the following line to your {shell} configuration file")
    click.echo(snippet)


@cli.command()
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to ingest YAML config file containing data source and destination settings.",
)
@click.option(
    "--generate-config",
    is_flag=True,
    help="Generate a starter configuration template. Use with --template-output.",
)
@click.option(
    "--template-output",
    type=click.Path(path_type=Path),
    help="Output path for the generated configuration template file.",
)
@click.pass_context
def ingest(
    ctx: click.Context,
    config: Path | None,
    generate_config: bool,
    template_output: Path | None,
) -> None:
    """Run data ingestion and register the produced artifact.

    Ingests data from a source file (CSV or Parquet), validates it,
    and registers the output in the feature catalog for reproducibility.

    \b
    Examples:
      # Generate a starter configuration
      tradepulse_cli ingest --generate-config --template-output my_ingest.yaml

      # Run ingestion using a config file
      tradepulse_cli ingest --config my_ingest.yaml

    \b
    Configuration file should specify:
      - source: Input data path and format (csv/parquet)
      - destination: Where to save the processed data
      - catalog: Path to the feature catalog
      - versioning: Version control settings (e.g., DVC)
    """

    command = "ingest"
    manager = _get_manager(ctx)
    if generate_config:
        if template_output is None:
            raise click.UsageError(
                "--template-output is required when using --generate-config.\n"
                "Example: tradepulse_cli ingest --generate-config --template-output ingest.yaml"
            )
        manager.render("ingest", template_output)
        click.echo(f"[{command}] ✓ Template written to {template_output}")
        click.echo(f"[{command}] ℹ Edit the template and run: tradepulse_cli ingest --config {template_output}")
        return
    if config is None:
        raise click.UsageError(
            "--config is required to run ingestion.\n"
            "To generate a starter config: tradepulse_cli ingest --generate-config --template-output ingest.yaml"
        )

    completion = threading.Event()
    fatal_event = threading.Event()
    fatal_error: list[BaseException] = []
    result: Dict[str, Any] = {}

    def _ingest_worker(stop_event: threading.Event) -> None:
        fatal = False
        try:
            with step_logger(command, "load config"):
                cfg = manager.load_config(config, IngestConfig)
            with step_logger(command, "load source data"):
                frame = _load_prices(cfg)
                record_count = len(frame)
            with step_logger(command, "persist dataset"):
                digest = _write_frame(frame, cfg.destination, command=command)
            with step_logger(command, "register catalog"):
                catalog = FeatureCatalog(cfg.catalog)
                entry = catalog.register(
                    cfg.name,
                    cfg.destination,
                    config=cfg,
                    lineage=[str(cfg.source.path)],
                    metadata=cfg.metadata,
                )
                click.echo(f"[{command}] • catalog checksum={entry.checksum}")
            with step_logger(command, "snapshot version"):
                version_mgr = DataVersionManager(cfg.versioning)
                version_mgr.snapshot(
                    cfg.destination, metadata={"records": record_count}
                )

            result.clear()
            result.update(
                {
                    "records": record_count,
                    "digest": digest,
                    "destination": cfg.destination,
                }
            )
            completion.set()
        except (CLIError, click.ClickException) as exc:
            fatal_error.append(exc)
            fatal_event.set()
            fatal = True
        except BaseException as exc:
            fatal_error.append(exc)
            fatal_event.set()
            fatal = True
        finally:
            if fatal:
                return
            if not stop_event.is_set():
                stop_event.wait()

    with Watchdog(
        name="ingest-cli", monitor_interval=0.25, health_url=None
    ) as watchdog:
        watchdog.register("ingest-worker", _ingest_worker, args=(watchdog.stop_event,))

        while True:
            if completion.wait(timeout=0.1):
                break
            if fatal_event.is_set():
                watchdog.stop()
                exc = (
                    fatal_error[0]
                    if fatal_error
                    else RuntimeError("ingest worker failed")
                )
                raise exc

    if not result:
        raise RuntimeError("ingest worker terminated without producing a result")

    click.echo(
        f"[{command}] completed records={result['records']} dest={result['destination']} sha256={result['digest']}"
    )


def _run_backtest(cfg: BacktestConfig) -> Dict[str, Any]:
    frame = _load_prices(cfg)
    prices = frame[cfg.data.value_field].to_numpy(dtype=float)
    strategy = _resolve_strategy(cfg.strategy)
    signals = strategy(prices)
    if signals.size != prices.size:
        raise ComputeError("Strategy must return a signal for each price")
    prev_prices = np.concatenate(([prices[0]], prices[:-1]))
    denom = np.where(prev_prices == 0, 1.0, prev_prices)
    returns = (prices - prev_prices) / denom
    pnl = returns * signals
    equity = cfg.execution.starting_cash * (1 + pnl.cumsum())
    stats = {
        "total_return": float(pnl.sum()),
        "max_drawdown": float(np.min(equity / np.maximum.accumulate(equity) - 1.0)),
        "trades": int(np.count_nonzero(np.diff(signals) != 0)),
    }
    return {"stats": stats, "signals": signals.tolist(), "returns": pnl.tolist()}


def _emit_backtest_output(
    cfg: BacktestConfig,
    result: Dict[str, Any],
    output_format: str | None,
    *,
    command: str,
) -> None:
    if output_format is None:
        return
    if output_format == "table":
        click.echo("metric | value")
        click.echo("------ | -----")
        for metric, value in result["stats"].items():
            click.echo(f"{metric} | {value}")
        return
    if output_format == "jsonl":
        for metric, value in result["stats"].items():
            click.echo(json.dumps({"metric": metric, "value": value}))
        return
    if output_format == "parquet":
        frame = pd.DataFrame(
            {
                "step": np.arange(len(result["signals"])),
                "signal": result["signals"],
                "return": result["returns"],
            }
        )
        parquet_path = cfg.results_path.with_suffix(".parquet")
        _write_frame(frame, parquet_path, command=command)
        return
    raise ConfigError(f"Unsupported output format '{output_format}'")


@cli.command()
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to backtest YAML config with strategy and data settings.",
)
@click.option(
    "--generate-config",
    is_flag=True,
    help="Generate a starter backtest configuration template.",
)
@click.option(
    "--template-output",
    type=click.Path(path_type=Path),
    help="Output path for the generated configuration template file.",
)
@click.option(
    "--output-format",
    "--output",
    type=click.Choice(["table", "jsonl", "parquet"]),
    help="Output format for results: table (readable), jsonl (machine-parseable), or parquet (analysis).",
)
@click.pass_context
def backtest(
    ctx: click.Context,
    config: Path | None,
    generate_config: bool,
    template_output: Path | None,
    output_format: str | None,
) -> None:
    """Execute a simple vectorized backtest.

    Runs a trading strategy simulation on historical data and computes
    performance metrics like total return, max drawdown, and trade count.

    \b
    Examples:
      # Generate a starter configuration
      tradepulse_cli backtest --generate-config --template-output backtest.yaml

      # Run backtest and display results as a table
      tradepulse_cli backtest --config backtest.yaml --output table

      # Run backtest with JSON Lines output (for pipelines)
      tradepulse_cli backtest --config backtest.yaml --output jsonl

    \b
    Output Metrics:
      - total_return: Overall strategy return
      - max_drawdown: Worst peak-to-trough decline
      - trades: Number of position changes
    """

    command = "backtest"
    manager = _get_manager(ctx)
    if generate_config:
        if template_output is None:
            raise click.UsageError(
                "--template-output is required when using --generate-config.\n"
                "Example: tradepulse_cli backtest --generate-config --template-output backtest.yaml"
            )
        manager.render("backtest", template_output)
        click.echo(f"[{command}] ✓ Template written to {template_output}")
        click.echo(f"[{command}] ℹ Edit the template and run: tradepulse_cli backtest --config {template_output}")
        return
    if config is None:
        raise click.UsageError(
            "--config is required to run backtesting.\n"
            "To generate a starter config: tradepulse_cli backtest --generate-config --template-output backtest.yaml"
        )

    with step_logger(command, "load config"):
        cfg = manager.load_config(config, BacktestConfig)
    with step_logger(command, "run backtest"):
        result = _run_backtest(cfg)
    with step_logger(command, "persist results"):
        digest = _write_json(cfg.results_path, result, command=command)
    with step_logger(command, "register catalog"):
        catalog = FeatureCatalog(cfg.catalog)
        entry = catalog.register(
            cfg.name,
            cfg.results_path,
            config=cfg,
            lineage=[str(cfg.data.path)],
            metadata=cfg.metadata,
        )
        click.echo(f"[{command}] • catalog checksum={entry.checksum}")
    with step_logger(command, "snapshot version"):
        version_mgr = DataVersionManager(cfg.versioning)
        version_mgr.snapshot(cfg.results_path, metadata=result["stats"])
    _emit_backtest_output(cfg, result, output_format, command=command)
    click.echo(
        f"[{command}] completed stats={json.dumps(result['stats'], sort_keys=True)} sha256={digest}"
    )


def _iterate_grid(search_space: Dict[str, Iterable[Any]]) -> Iterable[Dict[str, Any]]:
    keys = list(search_space.keys())
    for key in keys:
        values = search_space[key]
        if not isinstance(values, Iterable):
            raise ConfigError("Search space values must be iterable")
    for combo in itertools.product(*(search_space[key] for key in keys)):
        yield dict(zip(keys, combo))


def _emit_optimize_output(
    cfg: OptimizeConfig,
    payload: Dict[str, Any],
    output_format: str | None,
    *,
    command: str,
) -> None:
    if output_format is None:
        return
    if output_format == "table":
        click.echo("metric | value")
        click.echo("------ | -----")
        click.echo(f"best_score | {payload['best_score']}")
        if payload["best_params"]:
            for key, value in payload["best_params"].items():
                click.echo(f"param:{key} | {value}")
        click.echo(f"trials | {len(payload['trials'])}")
        return
    if output_format == "jsonl":
        click.echo(json.dumps({"metric": "best_score", "value": payload["best_score"]}))
        if payload["best_params"]:
            click.echo(
                json.dumps({"metric": "best_params", "value": payload["best_params"]})
            )
        for trial in payload["trials"]:
            click.echo(json.dumps({"metric": "trial", "value": trial}))
        return
    if output_format == "parquet":
        frame = pd.json_normalize(payload["trials"])
        parquet_path = cfg.results_path.with_suffix(".parquet")
        _write_frame(frame, parquet_path, command=command)
        return
    raise ConfigError(f"Unsupported output format '{output_format}'")


@cli.command()
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to optimization YAML config with parameter search space.",
)
@click.option(
    "--generate-config",
    is_flag=True,
    help="Generate a starter optimization configuration template.",
)
@click.option(
    "--template-output",
    type=click.Path(path_type=Path),
    help="Output path for the generated configuration template file.",
)
@click.option(
    "--output-format",
    "--output",
    type=click.Choice(["table", "jsonl", "parquet"]),
    help="Output format for results: table, jsonl, or parquet.",
)
@click.pass_context
def optimize(
    ctx: click.Context,
    config: Path | None,
    generate_config: bool,
    template_output: Path | None,
    output_format: str | None,
) -> None:
    """Perform a brute-force search across a parameter grid.

    Evaluates all combinations of strategy parameters defined in the
    search space and identifies the best-performing configuration.

    \b
    Examples:
      # Generate a starter configuration
      tradepulse_cli optimize --generate-config --template-output optimize.yaml

      # Run optimization with table output
      tradepulse_cli optimize --config optimize.yaml --output table

    \b
    Configuration should include:
      - search_space: Parameter ranges to explore
      - objective: Function to maximize (e.g., Sharpe ratio)
      - backtest: Embedded backtest configuration
    """

    command = "optimize"
    manager = _get_manager(ctx)
    if generate_config:
        if template_output is None:
            raise click.UsageError(
                "--template-output is required when using --generate-config.\n"
                "Example: tradepulse_cli optimize --generate-config --template-output optimize.yaml"
            )
        manager.render("optimize", template_output)
        click.echo(f"[{command}] ✓ Template written to {template_output}")
        click.echo(f"[{command}] ℹ Edit the template and run: tradepulse_cli optimize --config {template_output}")
        return
    if config is None:
        raise click.UsageError(
            "--config is required to run optimization.\n"
            "To generate a starter config: tradepulse_cli optimize --generate-config --template-output optimize.yaml"
        )

    with step_logger(command, "load config"):
        cfg = manager.load_config(config, OptimizeConfig)
    backtest_cfg = (
        BacktestConfig.model_validate(cfg.metadata.get("backtest"))
        if "backtest" in cfg.metadata
        else None
    )
    if backtest_cfg is None:
        raise ConfigError("Optimize config requires embedded backtest metadata")

    with step_logger(command, "load objective"):
        objective_fn = _load_callable(cfg.objective)
    trials: List[Dict[str, Any]] = []
    best_score = float("-inf")
    best_params: Dict[str, Any] | None = None
    with step_logger(command, "grid search"):
        for params in _iterate_grid(cfg.search_space):
            trial_cfg = backtest_cfg.model_copy(deep=True)
            trial_cfg.strategy.parameters.update(params)
            trial_result = _run_backtest(trial_cfg)
            returns = np.asarray(trial_result["returns"], dtype=float)
            score = float(objective_fn(returns))
            trials.append(
                {"params": params, "score": score, "stats": trial_result["stats"]}
            )
            if score > best_score:
                best_score = score
                best_params = params

    payload = {"best_score": best_score, "best_params": best_params, "trials": trials}
    with step_logger(command, "persist results"):
        digest = _write_json(cfg.results_path, payload, command=command)
    with step_logger(command, "snapshot version"):
        version_mgr = DataVersionManager(cfg.versioning)
        version_mgr.snapshot(cfg.results_path, metadata={"trials": len(trials)})
    _emit_optimize_output(cfg, payload, output_format, command=command)
    click.echo(
        f"[{command}] completed trials={len(trials)} best_score={best_score} sha256={digest}"
    )


def _emit_exec_output(
    cfg: ExecConfig,
    result: Dict[str, Any],
    signals: np.ndarray,
    output_format: str | None,
    *,
    command: str,
) -> None:
    if output_format is None:
        return
    if output_format == "table":
        click.echo("metric | value")
        click.echo("------ | -----")
        for metric, value in result.items():
            click.echo(f"{metric} | {value}")
        return
    if output_format == "jsonl":
        for metric, value in result.items():
            click.echo(json.dumps({"metric": metric, "value": value}))
        return
    if output_format == "parquet":
        frame = pd.DataFrame({"step": np.arange(signals.size), "signal": signals})
        parquet_path = cfg.results_path.with_suffix(".parquet")
        _write_frame(frame, parquet_path, command=command)
        return
    raise ConfigError(f"Unsupported output format '{output_format}'")


@cli.command()
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to execution YAML config with strategy and data settings.",
)
@click.option(
    "--generate-config",
    is_flag=True,
    help="Generate a starter execution configuration template.",
)
@click.option(
    "--template-output",
    type=click.Path(path_type=Path),
    help="Output path for the generated configuration template file.",
)
@click.option(
    "--output-format",
    "--output",
    type=click.Choice(["table", "jsonl", "parquet"]),
    help="Output format for results: table, jsonl, or parquet.",
)
@click.pass_context
def exec(  # noqa: A001
    ctx: click.Context,
    config: Path | None,
    generate_config: bool,
    template_output: Path | None,
    output_format: str | None,
) -> None:
    """Evaluate the latest signal and persist it to disk.

    Computes the current trading signal based on the configured strategy
    and persists the result for downstream consumption.

    \b
    Examples:
      # Generate a starter configuration
      tradepulse_cli exec --generate-config --template-output exec.yaml

      # Run signal evaluation
      tradepulse_cli exec --config exec.yaml

      # Run with human-readable table output
      tradepulse_cli exec --config exec.yaml --output table

    \b
    Tip: Use the 'serve' alias for the same functionality:
      tradepulse_cli serve --config exec.yaml
    """

    command = "exec"
    manager = _get_manager(ctx)
    if generate_config:
        if template_output is None:
            raise click.UsageError(
                "--template-output is required when using --generate-config.\n"
                "Example: tradepulse_cli exec --generate-config --template-output exec.yaml"
            )
        manager.render("exec", template_output)
        click.echo(f"[{command}] ✓ Template written to {template_output}")
        click.echo(f"[{command}] ℹ Edit the template and run: tradepulse_cli exec --config {template_output}")
        return
    if config is None:
        raise click.UsageError(
            "--config is required to run signal evaluation.\n"
            "To generate a starter config: tradepulse_cli exec --generate-config --template-output exec.yaml"
        )

    with step_logger(command, "load config"):
        cfg = manager.load_config(config, ExecConfig)
    with step_logger(command, "load data"):
        frame = _load_prices(cfg)
        prices = frame[cfg.data.value_field].to_numpy(dtype=float)
    with step_logger(command, "evaluate strategy"):
        strategy = _resolve_strategy(cfg.strategy)
        signals = strategy(prices)
    latest = float(signals[-1])
    result = {"latest_signal": latest, "count": int(signals.size)}
    with step_logger(command, "persist results"):
        digest = _write_json(cfg.results_path, result, command=command)
    with step_logger(command, "register catalog"):
        catalog = FeatureCatalog(cfg.catalog)
        entry = catalog.register(
            cfg.name,
            cfg.results_path,
            config=cfg,
            lineage=[str(cfg.data.path)],
            metadata=cfg.metadata,
        )
        click.echo(f"[{command}] • catalog checksum={entry.checksum}")
    with step_logger(command, "snapshot version"):
        version_mgr = DataVersionManager(cfg.versioning)
        version_mgr.snapshot(cfg.results_path, metadata=result)
    _emit_exec_output(cfg, result, signals, output_format, command=command)
    click.echo(f"[{command}] completed latest_signal={latest} sha256={digest}")


def _emit_report_output(
    cfg: ReportConfig,
    report_text: str,
    output_format: str | None,
    *,
    command: str,
) -> None:
    if output_format is None:
        return
    if output_format == "table":
        click.echo("section | source")
        click.echo("------- | ------")
        for idx, path in enumerate(cfg.inputs, start=1):
            click.echo(f"section-{idx} | {path}")
        click.echo(f"length | {len(report_text.splitlines())}")
        return
    if output_format == "jsonl":
        for idx, path in enumerate(cfg.inputs, start=1):
            click.echo(json.dumps({"section": idx, "source": str(path)}))
        click.echo(
            json.dumps({"metric": "line_count", "value": len(report_text.splitlines())})
        )
        return
    if output_format == "parquet":
        frame = pd.DataFrame(
            {
                "section": range(1, len(cfg.inputs) + 1),
                "source": [str(p) for p in cfg.inputs],
            }
        )
        parquet_path = cfg.output_path.with_suffix(".parquet")
        _write_frame(frame, parquet_path, command=command)
        return
    raise ConfigError(f"Unsupported output format '{output_format}'")


def _emit_parity_summary(report: FeatureParityReport, *, command: str) -> None:
    click.echo(
        f"[{command}] • feature_view={report.feature_view} "
        f"inserted={report.inserted_rows} updated={report.updated_rows} dropped={report.dropped_rows}"
    )
    integrity = report.integrity
    click.echo(
        f"[{command}] • integrity hash_differs={integrity.hash_differs} "
        f"offline_rows={integrity.offline_rows} online_rows={integrity.online_rows} "
        f"row_diff={integrity.row_count_diff}"
    )
    if report.max_value_drift is not None:
        click.echo(f"[{command}] • max_value_drift={report.max_value_drift:.6g}")
    if report.clock_skew is not None:
        click.echo(
            f"[{command}] • clock_skew={report.clock_skew} "
            f"abs={report.clock_skew_abs}"
        )
    if report.columns_added:
        click.echo(f"[{command}] • columns_added={', '.join(report.columns_added)}")
    if report.columns_removed:
        click.echo(f"[{command}] • columns_removed={', '.join(report.columns_removed)}")


@cli.command()
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to report YAML config with input artifacts and output paths.",
)
@click.option(
    "--generate-config",
    is_flag=True,
    help="Generate a starter report configuration template.",
)
@click.option(
    "--template-output",
    type=click.Path(path_type=Path),
    help="Output path for the generated configuration template file.",
)
@click.option(
    "--output-format",
    "--output",
    type=click.Choice(["table", "jsonl", "parquet"]),
    help="Additional output format for metadata (markdown is always generated).",
)
@click.pass_context
def report(
    ctx: click.Context,
    config: Path | None,
    generate_config: bool,
    template_output: Path | None,
    output_format: str | None,
) -> None:
    """Aggregate JSON artifacts into a markdown summary.

    Combines backtest, exec, and other JSON outputs into a single
    comprehensive markdown report. Optionally renders to HTML or PDF.

    \b
    Examples:
      # Generate a starter configuration
      tradepulse_cli report --generate-config --template-output report.yaml

      # Generate a report from multiple inputs
      tradepulse_cli report --config report.yaml

      # Show report metadata as a table
      tradepulse_cli report --config report.yaml --output table

    \b
    Supported output formats in config:
      - Markdown (.md): Always generated
      - HTML (.html): Set html_output_path in config
      - PDF (.pdf): Set pdf_output_path in config
    """

    command = "report"
    manager = _get_manager(ctx)
    if generate_config:
        if template_output is None:
            raise click.UsageError(
                "--template-output is required when using --generate-config.\n"
                "Example: tradepulse_cli report --generate-config --template-output report.yaml"
            )
        manager.render("report", template_output)
        click.echo(f"[{command}] ✓ Template written to {template_output}")
        click.echo(f"[{command}] ℹ Edit the template and run: tradepulse_cli report --config {template_output}")
        return
    if config is None:
        raise click.UsageError(
            "--config is required to generate a report.\n"
            "To generate a starter config: tradepulse_cli report --generate-config --template-output report.yaml"
        )

    with step_logger(command, "load config"):
        cfg = manager.load_config(config, ReportConfig)
    with step_logger(command, "generate markdown"):
        try:
            report_text = generate_markdown_report(cfg)
        except FileNotFoundError as exc:
            raise ArtifactError(str(exc)) from exc
    with step_logger(command, "persist markdown"):
        digest = _write_text(cfg.output_path, report_text, command=command)
    if cfg.html_output_path is not None:
        with step_logger(command, "render html"):
            render_markdown_to_html(report_text, cfg.html_output_path)
            html_digest = _existing_digest(cfg.html_output_path)
            if html_digest:
                click.echo(f"[{command}] • html sha256={html_digest}")
    if cfg.pdf_output_path is not None:
        with step_logger(command, "render pdf"):
            render_markdown_to_pdf(report_text, cfg.pdf_output_path)
            pdf_digest = _existing_digest(cfg.pdf_output_path)
            if pdf_digest:
                click.echo(f"[{command}] • pdf sha256={pdf_digest}")
    with step_logger(command, "snapshot version"):
        version_mgr = DataVersionManager(cfg.versioning)
        version_mgr.snapshot(cfg.output_path, metadata={"sections": len(cfg.inputs)})
    _emit_report_output(cfg, report_text, output_format, command=command)
    click.echo(f"[{command}] completed sections={len(cfg.inputs)} sha256={digest}")


@cli.command()
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to deployment YAML config with Kubernetes settings.",
)
@click.option(
    "--generate-config",
    is_flag=True,
    help="Generate a starter deployment configuration template.",
)
@click.option(
    "--template-output",
    type=click.Path(path_type=Path),
    help="Output path for the generated configuration template file.",
)
@click.pass_context
def deploy(
    ctx: click.Context,
    config: Path | None,
    generate_config: bool,
    template_output: Path | None,
) -> None:
    """Apply TradePulse Kubernetes manifests via kubectl.

    Deploys TradePulse to a Kubernetes cluster using Kustomize overlays.
    Supports dry-run mode, rollout waiting, and deployment annotations.

    \b
    Examples:
      # Generate a starter deployment config
      tradepulse_cli deploy --generate-config --template-output deploy.yaml

      # Deploy to staging environment
      tradepulse_cli deploy --config deploy.yaml

    \b
    Prerequisites:
      - kubectl configured with cluster access
      - Kustomize overlays in deploy/kustomize/overlays/

    \b
    Configuration options:
      - environment: stage, prod, etc.
      - kubectl.context: Kubernetes context to use
      - kubectl.namespace: Target namespace
      - kubectl.dry_run: client, server, or none
    """

    command = "deploy"
    manager = _get_manager(ctx)
    if generate_config:
        if template_output is None:
            raise click.UsageError(
                "--template-output is required when using --generate-config.\n"
                "Example: tradepulse_cli deploy --generate-config --template-output deploy.yaml"
            )
        manager.render("deploy", template_output)
        click.echo(f"[{command}] ✓ Template written to {template_output}")
        click.echo(f"[{command}] ℹ Edit the template and run: tradepulse_cli deploy --config {template_output}")
        return
    if config is None:
        raise click.UsageError(
            "--config is required to deploy.\n"
            "To generate a starter config: tradepulse_cli deploy --generate-config --template-output deploy.yaml"
        )

    with step_logger(command, "load config"):
        cfg = manager.load_config(config, DeploymentConfig)

    with step_logger(command, "resolve manifests"):
        overlay_path = _resolve_overlay_path(config, cfg)
        if not overlay_path.exists():
            raise ArtifactError(f"Manifests directory {overlay_path} does not exist")

    kubectl_binary = _resolve_kubectl_binary(config.parent, cfg.kubectl.binary)
    kubectl_env = os.environ.copy()
    kubectl_env.update(cfg.kubectl.env)

    dry_run_mode = cfg.kubectl.dry_run
    if dry_run_mode != "none":
        with step_logger(command, "dry-run apply"):
            _run_kubectl(
                command,
                kubectl_binary,
                cfg,
                kubectl_env,
                "apply",
                "-k",
                str(overlay_path),
                f"--dry-run={dry_run_mode}",
            )

    with step_logger(command, "apply manifests"):
        _run_kubectl(
            command,
            kubectl_binary,
            cfg,
            kubectl_env,
            "apply",
            "-k",
            str(overlay_path),
        )

    annotations = {
        "tradepulse.dev/artifact-digest": cfg.artifact,
        "tradepulse.dev/strategy-id": cfg.strategy,
    }
    annotations.update(cfg.annotations)

    if annotations:
        with step_logger(command, "annotate deployment"):
            annotate_args = ["annotate", f"deployment/{cfg.deployment_name}"]
            for key, value in sorted(annotations.items()):
                annotate_args.append(f"{key}={value}")
            annotate_args.append("--overwrite")
            _run_kubectl(command, kubectl_binary, cfg, kubectl_env, *annotate_args)

    if cfg.wait_for_rollout:
        with step_logger(command, "wait for rollout"):
            _run_kubectl(
                command,
                kubectl_binary,
                cfg,
                kubectl_env,
                "rollout",
                "status",
                f"deployment/{cfg.deployment_name}",
                f"--timeout={cfg.rollout_timeout_seconds}s",
            )

    summary_path = _resolve_path(config.parent, cfg.summary_path)
    with step_logger(command, "write summary"):
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_payload = {
            "name": cfg.name,
            "environment": cfg.environment.value,
            "strategy": cfg.strategy,
            "artifact": cfg.artifact,
            "deployment_name": cfg.deployment_name,
            "overlay_path": str(overlay_path),
            "kubectl_binary": str(kubectl_binary),
            "kubectl_context": cfg.kubectl.context,
            "kubectl_namespace": cfg.kubectl.namespace,
            "dry_run": dry_run_mode,
            "wait_for_rollout": cfg.wait_for_rollout,
            "rollout_timeout_seconds": cfg.rollout_timeout_seconds,
            "annotations": dict(sorted(annotations.items())),
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
        summary_path.write_text(
            json.dumps(summary_payload, indent=2) + "\n", encoding="utf-8"
        )
        click.echo(f"[{command}] • wrote deployment summary to {summary_path}")

    click.echo(
        f"[{command}] completed environment={cfg.environment.value} deployment={cfg.deployment_name}"
    )


@cli.command()
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to feature parity YAML config with store synchronization settings.",
)
@click.option(
    "--generate-config",
    is_flag=True,
    help="Generate a starter feature parity configuration template.",
)
@click.option(
    "--template-output",
    type=click.Path(path_type=Path),
    help="Output path for the generated configuration template file.",
)
@click.pass_context
def parity(
    ctx: click.Context,
    config: Path | None,
    generate_config: bool,
    template_output: Path | None,
) -> None:
    """Reconcile offline feature snapshots with the online feature store.

    Synchronizes features computed offline (e.g., from backtesting) with
    the online feature store used for live inference. Detects drift and
    schema changes.

    \b
    Examples:
      # Generate a starter configuration
      tradepulse_cli parity --generate-config --template-output parity.yaml

      # Synchronize features with the online store
      tradepulse_cli parity --config parity.yaml

    \b
    Synchronization modes:
      - overwrite: Replace all online features with offline data
      - merge: Add new records, update existing ones
      - append: Only add new records

    \b
    Reports include:
      - Row counts (inserted, updated, dropped)
      - Value drift detection
      - Schema evolution (added/removed columns)
    """

    command = "parity"
    manager = _get_manager(ctx)
    if generate_config:
        if template_output is None:
            raise click.UsageError(
                "--template-output is required when using --generate-config.\n"
                "Example: tradepulse_cli parity --generate-config --template-output parity.yaml"
            )
        manager.render("parity", template_output)
        click.echo(f"[{command}] ✓ Template written to {template_output}")
        click.echo(f"[{command}] ℹ Edit the template and run: tradepulse_cli parity --config {template_output}")
        return
    if config is None:
        raise click.UsageError(
            "--config is required to run parity check.\n"
            "To generate a starter config: tradepulse_cli parity --generate-config --template-output parity.yaml"
        )

    with step_logger(command, "load config"):
        cfg = manager.load_config(config, FeatureParityConfig)
    with step_logger(command, "load offline features"):
        offline_frame = _load_feature_frame(cfg.offline)

    spec = _build_parity_spec(cfg.spec)
    store = OnlineFeatureStore(cfg.online_store)
    coordinator = FeatureParityCoordinator(store)

    with step_logger(command, "synchronize online store"):
        try:
            report = coordinator.synchronize(spec, offline_frame, mode=cfg.mode)
        except FeatureParityError as exc:
            raise ParityError(str(exc)) from exc

    _emit_parity_summary(report, command=command)


@cli.command("fete-backtest")
@click.option(
    "--csv",
    "csv_path",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Input CSV path containing price history (required).",
)
@click.option(
    "--price-col",
    default="price",
    show_default=True,
    help="Name of the column containing price values.",
)
@click.option(
    "--prob-col",
    default=None,
    help="Optional column with model probabilities (0-1). If not provided, synthetic probabilities are generated.",
)
@click.option(
    "--out",
    "out_path",
    type=click.Path(path_type=Path),
    help="Optional output path for the equity curve CSV file.",
)
def fete_backtest(
    csv_path: Path, price_col: str, prob_col: str | None, out_path: Path | None
) -> None:
    """Run the FETE engine on a CSV dataset and display risk metrics.

    FETE (Fast Ensemble Trading Engine) is a probability-aware backtester
    that includes risk management, circuit breakers, and comprehensive
    performance metrics.

    \b
    Examples:
      # Basic backtest with default price column
      tradepulse_cli fete-backtest --csv data/prices.csv

      # Custom column names and output
      tradepulse_cli fete-backtest --csv data.csv --price-col close --out equity.csv

      # With model probabilities
      tradepulse_cli fete-backtest --csv data.csv --prob-col signal_prob

    \b
    Displayed Metrics:
      - Final Equity: End-of-backtest portfolio value
      - Total Return: Overall percentage gain/loss
      - Sharpe Ratio: Risk-adjusted return measure
      - Max Drawdown: Worst peak-to-trough decline
      - Win Rate: Percentage of profitable trades
      - Audit Metrics: Brier score, ECE, Entropy, Kendall's τ
    """

    command = "fete-backtest"
    prices, probs = _load_fete_inputs(csv_path, price_col, prob_col)
    fete_engine = FETE(FETEConfig())
    account = PaperTradingAccount()
    risk_guard = RiskGuard()
    backtester = FETEBacktestEngine(fete_engine, account, risk_guard)
    report = backtester.run(prices, probs, symbol=csv_path.stem or "asset")

    click.echo("=== FETE Backtest ===")
    click.echo(f"Final Equity : {report.final_equity:,.2f}")
    click.echo(f"Total Return : {report.total_return: .2%}")
    click.echo(f"Sharpe       : {report.sharpe: .3f}")
    click.echo(f"Volatility   : {report.volatility: .3%}")
    click.echo(f"Max Drawdown : {report.max_drawdown: .3%}")
    click.echo(f"Trades       : {report.num_trades} (win rate {report.win_rate: .1%})")
    audit = report.audit
    click.echo(
        "Audit  → Brier: {brier:.4f}  ECE: {ece:.4f}  Entropy: {entropy:.3f}  τ: {tau:.3f}".format(
            brier=audit["brier"],
            ece=audit["ece"],
            entropy=audit["entropy"],
            tau=audit["tau"],
        )
    )
    if risk_guard.circuit_breaker_active:
        click.echo(f"Circuit breaker engaged: {risk_guard.circuit_reason}")
    if report.risk_events:
        click.echo("Risk events:")
        for event in report.risk_events[-5:]:
            click.echo(
                f"  {event.timestamp.isoformat()} • {event.code} • {event.message}"
            )

    if out_path is not None:
        curve = pd.DataFrame(
            {
                "timestamp": [ts.isoformat() for ts, _ in report.equity_curve],
                "equity": [value for _, value in report.equity_curve],
            }
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        curve.to_csv(out_path, index=False)
        click.echo(f"[{command}] • wrote {out_path}")


@cli.command("causal-pipeline")
@click.option(
    "--returns-csv",
    type=click.Path(exists=True, path_type=Path),
    help="CSV file with log returns. Include ticker columns and optionally a timestamp column.",
)
@click.option(
    "--features-csv",
    type=click.Path(exists=True, path_type=Path),
    help="CSV file with precomputed features and labels (alternative to returns-csv).",
)
@click.option(
    "--window",
    default=252,
    show_default=True,
    help="Rolling window length for feature generation (trading days).",
)
@click.option(
    "--horizon",
    default=5,
    show_default=True,
    help="Forward horizon in periods for label creation.",
)
@click.option(
    "--lambda-base",
    default=0.6,
    show_default=True,
    help="Ensemble weight for base calibrated probability (0-1).",
)
@click.option(
    "--hmm-states",
    type=click.Choice(["2", "3"]),
    default="2",
    show_default=True,
    help="Number of hidden states for regime detection (2=bull/bear, 3=bull/bear/neutral).",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    help="Optional JSON output file path. Results are also printed to stdout.",
)
def causal_pipeline(
    returns_csv: Path | None,
    features_csv: Path | None,
    window: int,
    horizon: int,
    lambda_base: float,
    hmm_states: str,
    output: Path | None,
) -> None:
    """Execute the causal early-warning pipeline with optional backtest.

    Runs the TradePulse V21 causal inference pipeline for market regime
    detection and early warning signals. Supports both raw returns input
    and precomputed features.

    \b
    Examples:
      # Run pipeline from log returns CSV
      tradepulse_cli causal-pipeline --returns-csv returns.csv --output results.json

      # Run from precomputed features
      tradepulse_cli causal-pipeline --features-csv features.csv

      # Custom window and horizon
      tradepulse_cli causal-pipeline --returns-csv data.csv --window 126 --horizon 10

    \b
    Input Requirements:
      --returns-csv: Columns for tickers + optional timestamp column
      --features-csv: Must include dr, ricci_mean, topo_intensity,
                      causal_strength, and y (label) columns

    \b
    Note: Provide exactly one of --returns-csv or --features-csv.
    """

    command = "causal-pipeline"
    if bool(returns_csv) == bool(features_csv):
        raise click.UsageError(
            "Provide exactly one of --returns-csv or --features-csv.\n"
            "Example with returns: tradepulse_cli causal-pipeline --returns-csv returns.csv\n"
            "Example with features: tradepulse_cli causal-pipeline --features-csv features.csv"
        )

    feature_builder = v21.StrictCausalFeatureBuilder(
        v21.FeatureBuilderConfig(window=window, horizon=horizon)
    )
    trainer = v21.LogisticIsotonicTrainer(v21.ModelTrainingConfig())
    hmm = v21.RegimeHMMAdapter(v21.RegimeHMMConfig(states=int(hmm_states)))
    backtester = v21.ProbabilityBacktester(v21.BacktestConfig())
    pipeline = v21.TradePulseV21Pipeline(
        feature_builder,
        trainer,
        hmm,
        backtester,
        v21.EnsembleConfig(lambda_base=lambda_base),
    )

    if returns_csv is not None:
        with step_logger(command, "load returns"):
            returns = _load_returns_frame(returns_csv)
        with step_logger(command, "build features"):
            features = feature_builder.build(returns)
        with step_logger(command, "run pipeline"):
            result = pipeline.run(features, returns)
    else:
        with step_logger(command, "load features"):
            features = _load_feature_dataset(features_csv)  # type: ignore[arg-type]
        with step_logger(command, "run pipeline"):
            result = pipeline.run(features, returns=None, evaluate_backtest=False)

    payload = v21.result_to_json(result)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
        click.echo(f"[{command}] • wrote {output}")
    click.echo(payload)


# ---------------------------------------------------------------------------
# Developer-friendly aliases
# ---------------------------------------------------------------------------

#
# The CLI historically exposed commands named ``optimize`` and ``exec`` for the
# parameter search and signal serving workflows respectively. The wider
# TradePulse documentation, however, now standardises on the verbs ``train`` and
# ``serve``. To keep backward compatibility while matching the new terminology
# we register lightweight aliases that forward to the original commands. A
# ``materialize`` alias is also provided for teams that prefer that verb for the
# ingestion workflow.
#
cli.add_command(ingest, name="materialize")
cli.add_command(optimize, name="train")
cli.add_command(exec, name="serve")
DEFAULT_OVERLAY_NAMES = {
    "stage": "staging",
    "prod": "production",
}
