# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Prometheus metrics collection for TradePulse.

This module provides instrumentation for all critical entrypoints and
performance-sensitive operations.
"""
from __future__ import annotations

import math
import multiprocessing
import os
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    Iterator,
    Mapping,
    Optional,
    Sequence,
)

_NUMPY_AVAILABLE = False
_accelerated_quantiles: Any | None = None

try:  # pragma: no cover - exercised indirectly in environments without numpy
    import numpy as np
    from numpy.typing import NDArray
except ModuleNotFoundError:  # pragma: no cover - handled in fallback logic
    np = None  # type: ignore[assignment]
    NDArray = Any  # type: ignore[assignment]
else:  # pragma: no cover - covered via normal test environment
    _NUMPY_AVAILABLE = True
    from core.accelerators.numeric import quantiles as _numpy_quantiles

    _accelerated_quantiles = _numpy_quantiles

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        generate_latest,
        start_http_server,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


def _fallback_quantiles(
    values: list[float], quantiles: tuple[float, ...]
) -> Dict[float, float]:
    """Compute quantiles without numpy."""

    if not values:
        return {}

    sorted_values = sorted(values)
    n = len(sorted_values)
    results: Dict[float, float] = {}

    for q in quantiles:
        if not 0.0 <= q <= 1.0:
            continue

        position = q * (n - 1)
        lower_index = math.floor(position)
        upper_index = math.ceil(position)

        lower = sorted_values[lower_index]
        upper = sorted_values[upper_index]

        if lower_index == upper_index:
            results[q] = float(lower)
            continue

        weight = position - lower_index
        results[q] = float(lower + (upper - lower) * weight)

    return results


if TYPE_CHECKING:  # pragma: no cover - import cycle guard for type hints
    from analytics.environment_parity import MetricDeviation


class MetricsCollector:
    """Centralized metrics collection for TradePulse."""

    def __init__(self, registry: Optional[Any] = None):
        """Initialize metrics collector.

        Args:
            registry: Prometheus registry (uses default if None)
        """
        if not PROMETHEUS_AVAILABLE:
            self._enabled = False
            self.registry = None
            return

        self._enabled = True
        self.registry = registry
        if self.registry is not None:
            multiprocess_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
            should_register_defaults = True

            if multiprocess_dir:
                try:
                    from prometheus_client import multiprocess  # noqa: F401
                except ImportError:
                    # Multiprocess collector isn't available; fall back to defaults.
                    pass
                else:
                    # When the multiprocess module is available and the directory is
                    # configured, the deployment is expected to register
                    # ``multiprocess.MultiProcessCollector`` which exposes the same
                    # metrics as the default collectors. Registering both would raise
                    # ``ValueError: Duplicated timeseries`` so we skip registering the
                    # defaults in that case.
                    should_register_defaults = False

            if should_register_defaults:
                # Ensure the default collectors are registered on the provided registry
                # so standard Prometheus process/platform metrics are emitted.
                try:
                    from prometheus_client import (
                        GCCollector,
                        PlatformCollector,
                        ProcessCollector,
                    )

                    for collector_cls in (
                        ProcessCollector,
                        PlatformCollector,
                        GCCollector,
                    ):
                        try:
                            collector_cls(registry=self.registry)
                        except ValueError:
                            # Collector already registered – ignore duplicate.
                            continue
                except Exception:  # pragma: no cover - defensive guard
                    # If collector registration fails we still expose custom metrics
                    # rather than breaking application startup.
                    pass
        self._equity_curve_max_points = int(
            os.getenv("TRADEPULSE_METRICS_MAX_EQUITY_POINTS", "1024")
        )

        # API/service metrics
        self.api_request_latency = Histogram(
            "tradepulse_api_request_latency_seconds",
            "Latency observed for HTTP API requests",
            ["route", "method"],
            registry=registry,
        )

        self.api_requests_total = Counter(
            "tradepulse_api_requests_total",
            "Total number of HTTP API requests grouped by status",
            ["route", "method", "status"],
            registry=registry,
        )

        self.api_requests_in_flight = Gauge(
            "tradepulse_api_requests_in_flight",
            "Number of HTTP API requests currently being processed",
            ["route", "method"],
            registry=registry,
        )

        self.api_queue_depth = Gauge(
            "tradepulse_api_queue_depth",
            "Depth of internal queues servicing the API",
            ["queue"],
            registry=registry,
        )

        self.api_queue_latency = Histogram(
            "tradepulse_api_queue_latency_seconds",
            "Observed latency experienced by API servicing queues",
            ["queue"],
            registry=registry,
        )

        self.process_cpu_percent = Gauge(
            "tradepulse_process_cpu_percent",
            "CPU utilisation percent for the serving process",
            ["process"],
            registry=registry,
        )

        self.process_memory_bytes = Gauge(
            "tradepulse_process_memory_bytes",
            "Resident memory footprint of the serving process in bytes",
            ["process"],
            registry=registry,
        )

        self.process_memory_percent = Gauge(
            "tradepulse_process_memory_percent",
            "Memory utilisation percent for the serving process",
            ["process"],
            registry=registry,
        )

        # Feature/Indicator metrics
        self.feature_transform_duration = Histogram(
            "tradepulse_feature_transform_duration_seconds",
            "Time spent computing feature transformations",
            ["feature_name", "feature_type"],
            registry=registry,
        )

        self.feature_transform_total = Counter(
            "tradepulse_feature_transform_total",
            "Total number of feature transformations",
            ["feature_name", "feature_type", "status"],
            registry=registry,
        )

        self.feature_value = Gauge(
            "tradepulse_feature_value",
            "Current feature value",
            ["feature_name"],
            registry=registry,
        )

        self.indicator_compute_duration = Histogram(
            "tradepulse_indicator_compute_duration_seconds",
            "Time spent computing indicator values",
            ["indicator_name"],
            registry=registry,
        )

        self.indicator_compute_total = Counter(
            "tradepulse_indicator_compute_total",
            "Total number of indicator computations",
            ["indicator_name", "status"],
            registry=registry,
        )

        self.indicator_value = Gauge(
            "tradepulse_indicator_value",
            "Latest computed value for an indicator",
            ["indicator_name"],
            registry=registry,
        )

        self.indicator_sample_size = Gauge(
            "tradepulse_indicator_sample_size",
            "Number of samples processed during the last indicator computation",
            ["indicator_name"],
            registry=registry,
        )

        self.indicator_window_size = Gauge(
            "tradepulse_indicator_window_size",
            "Sliding window or bucket span configured for the indicator",
            ["indicator_name"],
            registry=registry,
        )

        self.indicator_quality_ratio = Gauge(
            "tradepulse_indicator_quality_ratio",
            "Quality ratios emitted by indicators (e.g. finite input share, valid coverage)",
            ["indicator_name", "metric"],
            registry=registry,
        )

        # Backtest metrics
        self.backtest_duration = Histogram(
            "tradepulse_backtest_duration_seconds",
            "Time spent running backtests",
            ["strategy"],
            registry=registry,
        )

        self.backtest_total = Counter(
            "tradepulse_backtest_total",
            "Total number of backtests run",
            ["strategy", "status"],
            registry=registry,
        )

        self.backtest_pnl = Gauge(
            "tradepulse_backtest_pnl",
            "Backtest profit and loss",
            ["strategy"],
            registry=registry,
        )

        self.backtest_max_drawdown = Gauge(
            "tradepulse_backtest_max_drawdown",
            "Backtest maximum drawdown",
            ["strategy"],
            registry=registry,
        )

        self.backtest_trades = Gauge(
            "tradepulse_backtest_trades",
            "Number of trades in backtest",
            ["strategy"],
            registry=registry,
        )
        self._equity_curve_cache: dict[str, list[str]] = defaultdict(list)

        # Environment parity metrics
        self.environment_parity_checks = Counter(
            "tradepulse_environment_parity_checks_total",
            "Total number of environment parity evaluations grouped by status",
            ["strategy", "status"],
            registry=registry,
        )

        self.environment_parity_metric_deviation = Gauge(
            "tradepulse_environment_parity_metric_deviation",
            "Absolute deviation observed between environment metric pairs",
            ["strategy", "metric", "baseline", "comparison"],
            registry=registry,
        )

        # Model observability metrics
        self.model_inference_latency = Histogram(
            "tradepulse_model_inference_latency_seconds",
            "Latency observed for model inference requests",
            ["model_name", "deployment"],
            registry=registry,
        )

        self.model_inference_latency_quantiles = Gauge(
            "tradepulse_model_inference_latency_quantiles_seconds",
            "Latency quantiles for model inference requests",
            ["model_name", "deployment", "quantile"],
            registry=registry,
        )

        self.model_inference_total = Counter(
            "tradepulse_model_inference_total",
            "Total number of model inference requests grouped by outcome",
            ["model_name", "deployment", "status"],
            registry=registry,
        )

        self.model_inference_throughput = Gauge(
            "tradepulse_model_inference_throughput_per_second",
            "Rolling throughput of model inference requests",
            ["model_name", "deployment"],
            registry=registry,
        )

        self.model_inference_error_ratio = Gauge(
            "tradepulse_model_inference_error_ratio",
            "Observed error ratio for model inference requests",
            ["model_name", "deployment"],
            registry=registry,
        )

        # Response quality metrics
        self.response_quality_run_total = Counter(
            "tradepulse_response_quality_run_total",
            "Total number of response quality verification runs",
            ["model_name", "deployment", "dataset", "mode", "status"],
            registry=registry,
        )

        self.response_quality_run_duration = Histogram(
            "tradepulse_response_quality_run_duration_seconds",
            "Duration of response quality verification runs",
            ["model_name", "deployment", "dataset", "mode"],
            registry=registry,
        )

        self.response_quality_contract_violations = Counter(
            "tradepulse_response_quality_contract_violations_total",
            "Number of response quality contract violations observed",
            ["model_name", "deployment", "dataset", "contract"],
            registry=registry,
        )

        self.response_quality_degradation_events = Counter(
            "tradepulse_response_quality_degradation_events_total",
            "Number of response quality degradations emitted",
            ["model_name", "deployment", "dataset", "reason"],
            registry=registry,
        )

        self.response_quality_pending_reviews = Gauge(
            "tradepulse_response_quality_pending_reviews",
            "Number of pending human reviews for response quality",
            ["model_name", "deployment"],
            registry=registry,
        )

        self.response_quality_complaints = Counter(
            "tradepulse_response_quality_complaints_total",
            "Number of complaints routed for response quality",
            ["model_name", "deployment", "category", "route"],
            registry=registry,
        )

        self.response_quality_reason_total = Counter(
            "tradepulse_response_quality_reason_total",
            "Count of reasons identified during response quality assurance",
            ["model_name", "deployment", "reason"],
            registry=registry,
        )

        self.model_saturation = Gauge(
            "tradepulse_model_saturation",
            "Saturation level of model serving infrastructure",
            ["model_name", "deployment"],
            registry=registry,
        )

        # RL stability metrics
        self.rl_update_scale = Gauge(
            "tradepulse_rl_update_scale",
            "Applied scaling factor for RL parameter updates",
            ["agent", "component"],
            registry=registry,
        )

        self.rl_grad_norm = Gauge(
            "tradepulse_rl_grad_norm",
            "Gradient norm observed during RL updates",
            ["agent", "component"],
            registry=registry,
        )

        self.rl_policy_kl = Gauge(
            "tradepulse_rl_policy_kl",
            "Observed KL divergence between successive policy updates",
            ["agent"],
            registry=registry,
        )

        self.rl_policy_drift = Gauge(
            "tradepulse_rl_policy_drift",
            "Relative parameter drift from the last stable checkpoint",
            ["agent"],
            registry=registry,
        )

        self.rl_rollback_total = Counter(
            "tradepulse_rl_rollback_total",
            "Total number of RL policy rollbacks",
            ["agent", "reason"],
            registry=registry,
        )

        self.rl_modulation_scale = Gauge(
            "tradepulse_rl_modulation_scale",
            "Effective modulation scale applied to RL updates",
            ["agent", "component", "signal"],
            registry=registry,
        )

        self.rl_modulation_risk = Gauge(
            "tradepulse_rl_modulation_risk",
            "Risk score derived for RL modulation controllers",
            ["agent", "signal"],
            registry=registry,
        )

        self.rl_modulation_arousal = Gauge(
            "tradepulse_rl_modulation_arousal",
            "Arousal boost component for RL modulation controllers",
            ["agent", "signal"],
            registry=registry,
        )

        self.model_cpu_percent = Gauge(
            "tradepulse_model_cpu_percent",
            "Process CPU utilisation percent for model serving",
            ["model_name", "deployment"],
            registry=registry,
        )

        self.model_gpu_percent = Gauge(
            "tradepulse_model_gpu_percent",
            "GPU utilisation percent for model serving workloads",
            ["model_name", "deployment"],
            registry=registry,
        )

        self.model_memory_bytes = Gauge(
            "tradepulse_model_memory_bytes",
            "Resident memory footprint of the model serving process",
            ["model_name", "deployment"],
            registry=registry,
        )

        self.model_memory_percent = Gauge(
            "tradepulse_model_memory_percent",
            "Memory utilisation percent for the model serving process",
            ["model_name", "deployment"],
            registry=registry,
        )

        self.model_cache_hit_ratio = Gauge(
            "tradepulse_model_cache_hit_ratio",
            "Hit ratio observed for model-specific caches",
            ["model_name", "deployment", "cache_name"],
            registry=registry,
        )

        self.model_cache_entries = Gauge(
            "tradepulse_model_cache_entries",
            "Number of live entries stored in model caches",
            ["model_name", "deployment", "cache_name"],
            registry=registry,
        )

        self.model_cache_evictions = Counter(
            "tradepulse_model_cache_evictions_total",
            "Total number of cache evictions triggered for model caches",
            ["model_name", "deployment", "cache_name"],
            registry=registry,
        )

        self.model_quality_interval_lower = Gauge(
            "tradepulse_model_quality_interval_lower",
            "Lower bound of quality metric confidence interval",
            ["model_name", "deployment", "metric", "confidence"],
            registry=registry,
        )

        self.model_quality_interval_upper = Gauge(
            "tradepulse_model_quality_interval_upper",
            "Upper bound of quality metric confidence interval",
            ["model_name", "deployment", "metric", "confidence"],
            registry=registry,
        )

        self.model_quality_interval_mean = Gauge(
            "tradepulse_model_quality_interval_mean",
            "Mean value for quality metric confidence interval",
            ["model_name", "deployment", "metric", "confidence"],
            registry=registry,
        )

        self.model_quality_interval_width = Gauge(
            "tradepulse_model_quality_interval_width",
            "Width of the quality metric confidence interval",
            ["model_name", "deployment", "metric", "confidence"],
            registry=registry,
        )

        self.model_quality_degradation_events = Counter(
            "tradepulse_model_quality_degradation_events_total",
            "Number of quality degradation signals emitted for a model",
            ["model_name", "deployment", "metric", "reason"],
            registry=registry,
        )

        self.model_triage_total = Counter(
            "tradepulse_model_triage_total",
            "Number of automated triage workflows launched for model incidents",
            ["model_name", "deployment", "metric", "reason"],
            registry=registry,
        )

        self.model_metric_correlation = Gauge(
            "tradepulse_model_metric_correlation",
            "Pearson correlation coefficient between pairs of model metrics",
            ["model_name", "deployment", "metric_a", "metric_b"],
            registry=registry,
        )

        # Data ingestion metrics
        self.data_ingestion_duration = Histogram(
            "tradepulse_data_ingestion_duration_seconds",
            "Time spent ingesting data",
            ["source", "symbol"],
            registry=registry,
        )

        self.data_ingestion_total = Counter(
            "tradepulse_data_ingestion_total",
            "Total number of data ingestion operations",
            ["source", "symbol", "status"],
            registry=registry,
        )

        self.data_ingestion_latency_quantiles = Gauge(
            "tradepulse_data_ingestion_latency_quantiles_seconds",
            "Data ingestion latency quantiles",
            ["source", "symbol", "quantile"],
            registry=registry,
        )

        self.data_ingestion_throughput = Gauge(
            "tradepulse_data_ingestion_throughput_ticks_per_second",
            "Instantaneous ingestion throughput expressed as ticks per second",
            ["source", "symbol"],
            registry=registry,
        )

        self.ticks_processed = Counter(
            "tradepulse_ticks_processed_total",
            "Total number of ticks processed",
            ["source", "symbol"],
            registry=registry,
        )

        # Watchdog metrics
        self.watchdog_worker_restarts = Counter(
            "tradepulse_watchdog_worker_restarts_total",
            "Total number of worker restarts triggered by watchdog supervision",
            ["watchdog", "worker"],
            registry=registry,
        )

        self.watchdog_live_probe_status = Gauge(
            "tradepulse_watchdog_live_probe_status",
            "Outcome of the most recent watchdog live probe (1=healthy, 0=unhealthy)",
            ["watchdog"],
            registry=registry,
        )

        self.watchdog_last_heartbeat = Gauge(
            "tradepulse_watchdog_last_heartbeat_timestamp",
            "Unix timestamp of the last watchdog heartbeat publish",
            ["watchdog"],
            registry=registry,
        )

        # Execution metrics
        self.order_placement_duration = Histogram(
            "tradepulse_order_placement_duration_seconds",
            "Time spent placing orders",
            ["exchange", "symbol"],
            registry=registry,
        )

        self.orders_placed = Counter(
            "tradepulse_orders_placed_total",
            "Total number of orders placed",
            ["exchange", "symbol", "order_type", "status"],
            registry=registry,
        )

        self.order_submission_latency_quantiles = Gauge(
            "tradepulse_order_submission_latency_quantiles_seconds",
            "Order submission latency quantiles",
            ["exchange", "symbol", "quantile"],
            registry=registry,
        )

        self.order_ack_latency_quantiles = Gauge(
            "tradepulse_order_ack_latency_quantiles_seconds",
            "Latency between order submission and broker acknowledgement",
            ["exchange", "symbol", "quantile"],
            registry=registry,
        )

        self.risk_validation_total = Counter(
            "tradepulse_risk_validations_total",
            "Total risk validation outcomes",
            ["symbol", "outcome"],
            registry=registry,
        )

        self.kill_switch_triggers_total = Counter(
            "tradepulse_kill_switch_triggers_total",
            "Kill switch triggers grouped by reason",
            ["reason"],
            registry=registry,
        )

        self.drawdown_percent = Gauge(
            "tradepulse_drawdown_percent",
            "Current portfolio drawdown expressed as a percentage",
            registry=registry,
        )

        self.compliance_checks_total = Counter(
            "tradepulse_compliance_checks_total",
            "Compliance check outcomes",
            ["symbol", "status"],
            registry=registry,
        )

        self.compliance_violations_total = Counter(
            "tradepulse_compliance_violations_total",
            "Compliance violations by type",
            ["symbol", "violation_type"],
            registry=registry,
        )

        self.order_fill_latency_quantiles = Gauge(
            "tradepulse_order_fill_latency_quantiles_seconds",
            "Order fill latency quantiles",
            ["exchange", "symbol", "quantile"],
            registry=registry,
        )

        self.signal_to_fill_latency_quantiles = Gauge(
            "tradepulse_signal_to_fill_latency_quantiles_seconds",
            "Aggregate latency from signal emission to final fill",
            ["strategy", "exchange", "symbol", "quantile"],
            registry=registry,
        )

        self.open_positions = Gauge(
            "tradepulse_open_positions",
            "Number of open positions",
            ["exchange", "symbol"],
            registry=registry,
        )

        # Incident and lifecycle metrics
        self.incidents_open = Gauge(
            "tradepulse_incidents_open",
            "Number of open incidents grouped by severity",
            ["severity"],
            registry=registry,
        )

        self.incident_ack_latency = Histogram(
            "tradepulse_incident_ack_latency_seconds",
            "Time between alert trigger and acknowledgement",
            ["severity"],
            registry=registry,
        )

        self.incident_resolution_latency = Histogram(
            "tradepulse_incident_resolution_latency_seconds",
            "Time between incident declaration and resolution",
            ["severity"],
            registry=registry,
        )

        self.runbook_executions_total = Counter(
            "tradepulse_runbook_executions_total",
            "Runbook executions grouped by outcome",
            ["runbook", "outcome"],
            registry=registry,
        )

        self.lifecycle_phase_state = Gauge(
            "tradepulse_lifecycle_phase_state",
            "Lifecycle phase state (1 when phase is in the given state)",
            ["phase", "state"],
            registry=registry,
        )

        self.lifecycle_checkpoint_status = Gauge(
            "tradepulse_lifecycle_checkpoint_status",
            "Lifecycle checkpoint status (1 when checkpoint is in the given status)",
            ["checkpoint", "status"],
            registry=registry,
        )

        self.lifecycle_transition_total = Counter(
            "tradepulse_lifecycle_transition_total",
            "Lifecycle transitions grouped by from/to phase and outcome",
            ["from_phase", "to_phase", "outcome"],
            registry=registry,
        )

        # Strategy metrics
        self.strategy_score = Gauge(
            "tradepulse_strategy_score",
            "Strategy performance score",
            ["strategy_name"],
            registry=registry,
        )

        self.strategy_memory_size = Gauge(
            "tradepulse_strategy_memory_size",
            "Number of strategies in memory",
            registry=registry,
        )

        self.backtest_equity_curve = Gauge(
            "tradepulse_backtest_equity_curve",
            "Equity curve samples for backtests",
            ["strategy", "step"],
            registry=registry,
        )

        self.regression_metrics = Gauge(
            "tradepulse_regression_metric",
            "Regression quality metrics (e.g. MAE, RMSE, R2)",
            ["model", "metric"],
            registry=registry,
        )

        self.signal_generation_latency_quantiles = Gauge(
            "tradepulse_signal_generation_latency_quantiles_seconds",
            "Signal generation latency quantiles",
            ["strategy", "quantile"],
            registry=registry,
        )

        self.signal_generation_total = Counter(
            "tradepulse_signal_generation_total",
            "Total number of signal generation calls",
            ["strategy", "status"],
            registry=registry,
        )

        self.health_check_latency = Histogram(
            "tradepulse_health_check_latency_seconds",
            "Latency of periodic system health probes",
            ["check_name"],
            registry=registry,
        )

        self.health_check_status = Gauge(
            "tradepulse_health_check_status",
            "Outcome of the latest health probe (1=healthy, 0=unhealthy)",
            ["check_name"],
            registry=registry,
        )

        # Database metrics
        self.database_size_bytes = Gauge(
            "tradepulse_database_size_bytes",
            "Current size of the database in bytes",
            ["database", "host"],
            registry=registry,
        )

        self.database_size_growth = Gauge(
            "tradepulse_database_size_growth_bytes",
            "Growth in database size since the previous measurement",
            ["database", "host"],
            registry=registry,
        )

        self.database_query_latency = Histogram(
            "tradepulse_database_query_latency_seconds",
            "Latency observed for database queries",
            ["database", "host", "statement_type", "status"],
            registry=registry,
        )

        self.database_query_total = Counter(
            "tradepulse_database_query_total",
            "Total database queries executed grouped by outcome",
            ["database", "host", "statement_type", "status"],
            registry=registry,
        )

        # Cache warm-up and cold-start metrics
        self.cache_warmup_duration = Histogram(
            "tradepulse_cache_warmup_duration_seconds",
            "Latency of cache warm-up executions",
            ["cache_name", "strategy"],
            registry=registry,
        )

        self.cache_warmup_rows = Gauge(
            "tradepulse_cache_warmup_rows",
            "Number of rows materialised during cache warm-up",
            ["cache_name", "strategy"],
            registry=registry,
        )

        self.cache_readiness_status = Gauge(
            "tradepulse_cache_readiness_status",
            "Readiness state of managed caches (1=ready, 0=not ready)",
            ["cache_name"],
            registry=registry,
        )

        self.cache_hit_rate = Gauge(
            "tradepulse_cache_hit_rate",
            "Rolling hit rate observed for caches",
            ["cache_name"],
            registry=registry,
        )

        self.cache_cold_latency = Histogram(
            "tradepulse_cache_cold_latency_seconds",
            "Latency observed when serving cold cache requests",
            ["cache_name"],
            registry=registry,
        )

        self.cache_cold_requests = Counter(
            "tradepulse_cache_cold_requests_total",
            "Count of cold cache requests grouped by outcome",
            ["cache_name", "outcome"],
            registry=registry,
        )

        self.cache_degradation_events = Counter(
            "tradepulse_cache_degradation_events_total",
            "Number of cache degradation signals emitted grouped by reason",
            ["cache_name", "reason"],
            registry=registry,
        )

        self._model_latency_samples: Dict[tuple[str, str], deque[float]] = defaultdict(
            lambda: deque(maxlen=512)
        )
        self._ingestion_latency_samples: Dict[tuple[str, str], deque[float]] = (
            defaultdict(lambda: deque(maxlen=256))
        )
        self._signal_latency_samples: Dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=256)
        )
        self._order_submission_latency_samples: Dict[tuple[str, str], deque[float]] = (
            defaultdict(lambda: deque(maxlen=256))
        )
        self._order_ack_latency_samples: Dict[tuple[str, str], deque[float]] = (
            defaultdict(lambda: deque(maxlen=256))
        )
        self._order_fill_latency_samples: Dict[tuple[str, str], deque[float]] = (
            defaultdict(lambda: deque(maxlen=256))
        )
        self._signal_to_fill_latency_samples: Dict[
            tuple[str, str, str], deque[float]
        ] = defaultdict(lambda: deque(maxlen=256))
        self._database_size_cache: Dict[tuple[str, str], float] = {}

        # Agent/optimization metrics
        self.optimization_duration = Histogram(
            "tradepulse_optimization_duration_seconds",
            "Time spent on strategy optimization",
            ["optimizer_type"],
            registry=registry,
        )

        self.optimization_iterations = Counter(
            "tradepulse_optimization_iterations_total",
            "Total number of optimization iterations",
            ["optimizer_type"],
            registry=registry,
        )

    @property
    def enabled(self) -> bool:
        """Check if metrics collection is enabled."""
        return self._enabled

    def _resolve_status(self, ctx: Dict[str, Any], status: str) -> str:
        """Resolve the final status for metrics labels.

        When an exception occurs the contextual status must *always* be
        recorded as ``"error"`` regardless of any values stored on the
        context dictionary. For successful executions we still allow callers to
        provide a custom status value via ``ctx["status"]`` while gracefully
        handling ``None``/empty values by falling back to the default status.
        """

        if status == "error":
            return "error"

        override = ctx.get("status")
        if override is None:
            return status

        final_status = str(override).strip()
        return final_status or status

    # ------------------------------------------------------------------
    # API/service helpers

    def observe_api_request(
        self, route: str, method: str, status_code: int, duration: float
    ) -> None:
        """Record latency and counters for an API request."""

        if not self._enabled:
            return

        route_label = self._normalise_label(route, default="unknown")
        method_label = self._normalise_label(method, default="other").upper()
        status_label = self._normalise_label(status_code, default="unknown")

        bounded_duration = max(0.0, float(duration))
        self.api_request_latency.labels(route=route_label, method=method_label).observe(
            bounded_duration
        )
        self.api_requests_total.labels(
            route=route_label, method=method_label, status=status_label
        ).inc()

    def track_api_in_flight(self, route: str, method: str, delta: float) -> None:
        """Adjust the in-flight gauge for API requests."""

        if not self._enabled or delta == 0:
            return

        route_label = self._normalise_label(route, default="unknown")
        method_label = self._normalise_label(method, default="other").upper()
        gauge = self.api_requests_in_flight.labels(
            route=route_label, method=method_label
        )
        change = float(delta)
        if change > 0:
            gauge.inc(change)
        else:
            gauge.dec(abs(change))

    def set_queue_depth(self, queue_name: str, depth: float) -> None:
        """Update the observed depth of an internal queue."""

        if not self._enabled:
            return

        queue_label = self._normalise_label(queue_name, default="default")
        bounded_depth = max(0.0, float(depth))
        self.api_queue_depth.labels(queue=queue_label).set(bounded_depth)

    def observe_queue_latency(self, queue_name: str, latency: float) -> None:
        """Record latency experienced within an internal queue."""

        if not self._enabled:
            return

        queue_label = self._normalise_label(queue_name, default="default")
        bounded_latency = max(0.0, float(latency))
        self.api_queue_latency.labels(queue=queue_label).observe(bounded_latency)

    def set_process_resource_usage(
        self,
        process_name: str,
        *,
        cpu_percent: float | None = None,
        memory_bytes: float | None = None,
        memory_percent: float | None = None,
    ) -> None:
        """Update CPU and memory gauges for the serving process."""

        if not self._enabled:
            return

        process_label = self._normalise_label(process_name, default="main")

        if cpu_percent is not None:
            self.process_cpu_percent.labels(process=process_label).set(
                max(0.0, float(cpu_percent))
            )

        if memory_bytes is not None:
            self.process_memory_bytes.labels(process=process_label).set(
                max(0.0, float(memory_bytes))
            )

        if memory_percent is not None:
            bounded = max(0.0, min(100.0, float(memory_percent)))
            self.process_memory_percent.labels(process=process_label).set(bounded)

    @contextmanager
    def measure_feature_transform(
        self,
        feature_name: str,
        feature_type: str = "generic",
    ) -> Iterator[None]:
        """Context manager for measuring feature transformation time.

        Args:
            feature_name: Name of the feature being transformed
            feature_type: Type/category of the feature

        Example:
            >>> collector = MetricsCollector()
            >>> with collector.measure_feature_transform("RSI", "momentum"):
            ...     result = compute_rsi(prices)
        """
        if not self._enabled:
            yield
            return

        start_time = time.time()
        status = "success"

        try:
            yield
        except Exception:
            status = "error"
            raise
        finally:
            duration = time.time() - start_time
            self.feature_transform_duration.labels(
                feature_name=feature_name, feature_type=feature_type
            ).observe(duration)
            self.feature_transform_total.labels(
                feature_name=feature_name, feature_type=feature_type, status=status
            ).inc()

    @contextmanager
    def measure_indicator_compute(
        self, indicator_name: str
    ) -> Iterator[Dict[str, Any]]:
        """Context manager for measuring indicator computations."""

        if not self._enabled:
            yield {}
            return

        start_time = time.time()
        status = "success"
        ctx: Dict[str, Any] = {}

        try:
            yield ctx
        except Exception:
            status = "error"
            raise
        finally:
            duration = time.time() - start_time
            self.indicator_compute_duration.labels(
                indicator_name=indicator_name
            ).observe(duration)
            self.indicator_compute_total.labels(
                indicator_name=indicator_name, status=status
            ).inc()
            if status == "success":
                value = ctx.get("value")
                if value is not None:
                    try:
                        numeric: float | None = float(value)
                    except (TypeError, ValueError):
                        numeric = None
                    if numeric is not None and math.isfinite(numeric):
                        self.indicator_value.labels(indicator_name=indicator_name).set(
                            numeric
                        )
                diagnostics = ctx.get("diagnostics")
                if diagnostics:
                    self.record_indicator_diagnostics(indicator_name, diagnostics)

    @contextmanager
    def measure_backtest(self, strategy: str) -> Iterator[Dict[str, Any]]:
        """Context manager for measuring backtest execution.

        Args:
            strategy: Name of the strategy being backtested

        Yields:
            Dictionary to store backtest results

        Example:
            >>> collector = MetricsCollector()
            >>> with collector.measure_backtest("momentum_strategy") as ctx:
            ...     result = run_backtest(...)
            ...     ctx["pnl"] = result.pnl
            ...     ctx["max_dd"] = result.max_dd
            ...     ctx["trades"] = result.trades
        """
        if not self._enabled:
            yield {}
            return

        start_time = time.time()
        status = "success"
        ctx: Dict[str, Any] = {}

        try:
            yield ctx
        except Exception:
            status = "error"
            raise
        finally:
            duration = time.time() - start_time
            self.backtest_duration.labels(strategy=strategy).observe(duration)
            self.backtest_total.labels(strategy=strategy, status=status).inc()

            if status == "success" and ctx:
                if "pnl" in ctx:
                    self.backtest_pnl.labels(strategy=strategy).set(ctx["pnl"])
                if "max_dd" in ctx:
                    self.backtest_max_drawdown.labels(strategy=strategy).set(
                        abs(ctx["max_dd"])
                    )
                if "trades" in ctx:
                    self.backtest_trades.labels(strategy=strategy).set(ctx["trades"])

    def record_feature_value(self, feature_name: str, value: float) -> None:
        """Record a feature value.

        Args:
            feature_name: Name of the feature
            value: Feature value
        """
        if not self._enabled:
            return
        self.feature_value.labels(feature_name=feature_name).set(value)

    def record_indicator_value(self, indicator_name: str, value: float) -> None:
        """Record the last value emitted by an indicator."""

        if not self._enabled:
            return
        self.indicator_value.labels(indicator_name=indicator_name).set(float(value))

    def record_indicator_diagnostics(
        self,
        indicator_name: str,
        diagnostics: Mapping[str, Any] | None = None,
    ) -> None:
        """Persist diagnostic metadata reported by indicator computations."""

        if not self._enabled or not diagnostics:
            return

        def _as_float(value: Any) -> float | None:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return None
            if not math.isfinite(numeric):
                return None
            return numeric

        sample_size = diagnostics.get("sample_size") or diagnostics.get("samples")
        numeric_sample = _as_float(sample_size) if sample_size is not None else None
        if numeric_sample is not None and numeric_sample >= 0.0:
            self.indicator_sample_size.labels(indicator_name=indicator_name).set(
                numeric_sample
            )

        window = diagnostics.get("window") or diagnostics.get("span")
        numeric_window = _as_float(window) if window is not None else None
        if numeric_window is not None and numeric_window >= 0.0:
            self.indicator_window_size.labels(indicator_name=indicator_name).set(
                numeric_window
            )

        ratios: Dict[str, float] = {}
        ratio_container = diagnostics.get("ratios") or diagnostics.get("quality")
        if isinstance(ratio_container, Mapping):
            for key, value in ratio_container.items():
                numeric = _as_float(value)
                if numeric is None:
                    continue
                ratios[str(key)] = float(min(max(numeric, 0.0), 1.0))

        if not ratios:
            for key, value in diagnostics.items():
                if not isinstance(key, str) or not key.endswith("_ratio"):
                    continue
                metric = key[: -len("_ratio")]
                numeric = _as_float(value)
                if numeric is None:
                    continue
                ratios[metric] = float(min(max(numeric, 0.0), 1.0))

        for metric, numeric in ratios.items():
            metric_label = self._normalise_label(metric, default="quality")
            self.indicator_quality_ratio.labels(
                indicator_name=indicator_name, metric=metric_label
            ).set(numeric)

    def _update_latency_quantiles(
        self,
        gauge: Gauge,
        labels: Dict[str, str],
        samples: deque[float],
    ) -> None:
        if not self._enabled or not samples:
            return
        values = list(map(float, samples))
        if not values:
            return

        quantiles = (0.5, 0.95, 0.99)
        if _NUMPY_AVAILABLE and np is not None and _accelerated_quantiles is not None:
            arr = np.fromiter(values, dtype=float, count=len(values))
            if arr.size == 0:
                return
            accelerated = _accelerated_quantiles(arr, quantiles)
            quantile_values = {
                q: float(value)
                for q, value in zip(quantiles, accelerated, strict=False)
            }
        else:
            quantile_values = _fallback_quantiles(values, quantiles)

        for quantile, name in zip(quantiles, ("p50", "p95", "p99")):
            value = quantile_values.get(quantile)
            if value is None:
                continue
            gauge.labels(**labels, quantile=name).set(value)

    # ------------------------------------------------------------------
    # Model observability helpers

    def observe_model_inference_latency(
        self, model_name: str, deployment: str, duration: float
    ) -> None:
        """Observe latency for a model inference request."""

        if not self._enabled:
            return

        bounded_duration = max(0.0, float(duration))
        self.model_inference_latency.labels(
            model_name=model_name, deployment=deployment
        ).observe(bounded_duration)

        samples = self._model_latency_samples[(model_name, deployment)]
        samples.append(bounded_duration)
        self._update_latency_quantiles(
            self.model_inference_latency_quantiles,
            {"model_name": model_name, "deployment": deployment},
            samples,
        )

    def increment_model_inference_total(
        self, model_name: str, deployment: str, status: str
    ) -> None:
        """Increment inference counters for the supplied status."""

        if not self._enabled:
            return
        final_status = status.strip().lower() or "unknown"
        self.model_inference_total.labels(
            model_name=model_name, deployment=deployment, status=final_status
        ).inc()

    def set_model_inference_throughput(
        self, model_name: str, deployment: str, throughput: float
    ) -> None:
        """Set the rolling throughput gauge for inference."""

        if not self._enabled:
            return
        self.model_inference_throughput.labels(
            model_name=model_name, deployment=deployment
        ).set(max(0.0, float(throughput)))

    def set_model_inference_error_ratio(
        self, model_name: str, deployment: str, error_ratio: float
    ) -> None:
        """Update the error ratio gauge for model inference."""

        if not self._enabled:
            return
        bounded = max(0.0, min(1.0, float(error_ratio)))
        self.model_inference_error_ratio.labels(
            model_name=model_name, deployment=deployment
        ).set(bounded)

    def set_model_saturation(
        self, model_name: str, deployment: str, saturation: float
    ) -> None:
        """Record the saturation level of the serving infrastructure."""

        if not self._enabled:
            return
        bounded = max(0.0, min(1.0, float(saturation)))
        self.model_saturation.labels(model_name=model_name, deployment=deployment).set(
            bounded
        )

    def set_model_resource_usage(
        self,
        model_name: str,
        deployment: str,
        *,
        cpu_percent: float | None = None,
        gpu_percent: float | None = None,
        memory_bytes: float | None = None,
        memory_percent: float | None = None,
    ) -> None:
        """Update resource utilisation gauges for the serving process."""

        if not self._enabled:
            return

        if cpu_percent is not None:
            self.model_cpu_percent.labels(
                model_name=model_name, deployment=deployment
            ).set(max(0.0, float(cpu_percent)))
        if gpu_percent is not None:
            self.model_gpu_percent.labels(
                model_name=model_name, deployment=deployment
            ).set(max(0.0, float(gpu_percent)))
        if memory_bytes is not None:
            self.model_memory_bytes.labels(
                model_name=model_name, deployment=deployment
            ).set(max(0.0, float(memory_bytes)))
        if memory_percent is not None:
            bounded = max(0.0, min(100.0, float(memory_percent)))
            self.model_memory_percent.labels(
                model_name=model_name, deployment=deployment
            ).set(bounded)

    def set_model_cache_metrics(
        self,
        model_name: str,
        deployment: str,
        cache_name: str,
        *,
        hit_ratio: float | None = None,
        entries: float | None = None,
    ) -> None:
        """Update cache-related gauges for model serving caches."""

        if not self._enabled:
            return

        if hit_ratio is not None:
            bounded = max(0.0, min(1.0, float(hit_ratio)))
            self.model_cache_hit_ratio.labels(
                model_name=model_name,
                deployment=deployment,
                cache_name=cache_name,
            ).set(bounded)
        if entries is not None:
            self.model_cache_entries.labels(
                model_name=model_name,
                deployment=deployment,
                cache_name=cache_name,
            ).set(max(0.0, float(entries)))

    def increment_model_cache_evictions(
        self, model_name: str, deployment: str, cache_name: str, count: int = 1
    ) -> None:
        """Increment eviction counters for model caches."""

        if not self._enabled:
            return
        self.model_cache_evictions.labels(
            model_name=model_name,
            deployment=deployment,
            cache_name=cache_name,
        ).inc(max(0, int(count)))

    def set_model_quality_interval(
        self,
        model_name: str,
        deployment: str,
        metric: str,
        confidence: float,
        *,
        mean: float,
        lower: float,
        upper: float,
    ) -> None:
        """Record statistics describing a quality confidence interval."""

        if not self._enabled:
            return

        label_kwargs = {
            "model_name": model_name,
            "deployment": deployment,
            "metric": metric,
            "confidence": f"{confidence:.2f}",
        }
        self.model_quality_interval_mean.labels(**label_kwargs).set(float(mean))
        self.model_quality_interval_lower.labels(**label_kwargs).set(float(lower))
        self.model_quality_interval_upper.labels(**label_kwargs).set(float(upper))
        width = max(0.0, float(upper) - float(lower))
        self.model_quality_interval_width.labels(**label_kwargs).set(width)

    def record_model_degradation(
        self,
        model_name: str,
        deployment: str,
        metric: str,
        reason: str,
    ) -> None:
        """Increment the counter tracking emitted degradation events."""

        if not self._enabled:
            return
        self.model_quality_degradation_events.labels(
            model_name=model_name,
            deployment=deployment,
            metric=metric,
            reason=reason,
        ).inc()

    def record_model_triage(
        self,
        model_name: str,
        deployment: str,
        metric: str,
        reason: str,
    ) -> None:
        """Record that an automated triage workflow was launched."""

        if not self._enabled:
            return
        self.model_triage_total.labels(
            model_name=model_name,
            deployment=deployment,
            metric=metric,
            reason=reason,
        ).inc()

    def set_model_metric_correlation(
        self,
        model_name: str,
        deployment: str,
        metric_a: str,
        metric_b: str,
        coefficient: float,
    ) -> None:
        """Publish correlation coefficients between metric pairs."""

        if not self._enabled:
            return
        self.model_metric_correlation.labels(
            model_name=model_name,
            deployment=deployment,
            metric_a=metric_a,
            metric_b=metric_b,
        ).set(float(coefficient))

    def record_response_quality_run(
        self,
        model_name: str,
        deployment: str,
        dataset: str,
        mode: str,
        status: str,
        duration_seconds: float,
    ) -> None:
        """Record metadata about a response quality verification run."""

        if not self._enabled:
            return
        final_mode = mode.strip().lower() or "full"
        final_status = status.strip().lower() or "unknown"
        bounded_duration = max(0.0, float(duration_seconds))
        self.response_quality_run_total.labels(
            model_name=model_name,
            deployment=deployment,
            dataset=dataset,
            mode=final_mode,
            status=final_status,
        ).inc()
        self.response_quality_run_duration.labels(
            model_name=model_name,
            deployment=deployment,
            dataset=dataset,
            mode=final_mode,
        ).observe(bounded_duration)

    def record_response_quality_contract_violation(
        self,
        model_name: str,
        deployment: str,
        dataset: str,
        contract: str,
    ) -> None:
        """Increment counters for response quality contract violations."""

        if not self._enabled:
            return
        self.response_quality_contract_violations.labels(
            model_name=model_name,
            deployment=deployment,
            dataset=dataset,
            contract=contract,
        ).inc()

    def record_response_quality_degradation(
        self,
        model_name: str,
        deployment: str,
        dataset: str,
        reason: str,
    ) -> None:
        """Increment counters for response quality degradations."""

        if not self._enabled:
            return
        self.response_quality_degradation_events.labels(
            model_name=model_name,
            deployment=deployment,
            dataset=dataset,
            reason=reason,
        ).inc()

    def set_response_quality_pending_reviews(
        self, model_name: str, deployment: str, count: int
    ) -> None:
        """Set the gauge tracking pending human reviews."""

        if not self._enabled:
            return
        self.response_quality_pending_reviews.labels(
            model_name=model_name,
            deployment=deployment,
        ).set(max(0, int(count)))

    def record_response_quality_complaint(
        self,
        model_name: str,
        deployment: str,
        category: str,
        route: str,
    ) -> None:
        """Record routed complaints for response quality."""

        if not self._enabled:
            return
        self.response_quality_complaints.labels(
            model_name=model_name,
            deployment=deployment,
            category=category,
            route=route,
        ).inc()

    def record_response_quality_reason(
        self, model_name: str, deployment: str, reason: str
    ) -> None:
        """Track reason map statistics for response quality operations."""

        if not self._enabled:
            return
        self.response_quality_reason_total.labels(
            model_name=model_name,
            deployment=deployment,
            reason=reason,
        ).inc()

    @contextmanager
    def measure_signal_generation(self, strategy: str) -> Iterator[Dict[str, Any]]:
        """Measure latency of strategy signal generation."""

        if not self._enabled:
            yield {}
            return

        start_time = time.time()
        ctx: Dict[str, Any] = {}
        status = "success"

        try:
            yield ctx
        except Exception:
            status = "error"
            raise
        finally:
            duration = time.time() - start_time
            final_status = self._resolve_status(ctx, status)
            samples = self._signal_latency_samples[strategy]
            samples.append(duration)
            self._update_latency_quantiles(
                self.signal_generation_latency_quantiles,
                {"strategy": strategy},
                samples,
            )
            self.signal_generation_total.labels(
                strategy=strategy, status=final_status
            ).inc()

    @contextmanager
    def measure_data_ingestion(
        self,
        source: str,
        symbol: str,
    ) -> Iterator[Dict[str, Any]]:
        """Context manager for measuring data ingestion operations.

        Args:
            source: Data source name
            symbol: Trading symbol

        Yields:
            Dictionary that can be populated with metadata (e.g. ``{"status": "error"}``).
        """
        if not self._enabled:
            yield {}
            return

        start_time = time.time()
        ctx: Dict[str, Any] = {}
        status = "success"

        try:
            yield ctx
        except Exception:
            status = "error"
            raise
        finally:
            duration = time.time() - start_time
            final_status = self._resolve_status(ctx, status)
            self.data_ingestion_duration.labels(
                source=source,
                symbol=symbol,
            ).observe(duration)
            samples = self._ingestion_latency_samples[(source, symbol)]
            samples.append(duration)
            self._update_latency_quantiles(
                self.data_ingestion_latency_quantiles,
                {"source": source, "symbol": symbol},
                samples,
            )
            self.data_ingestion_total.labels(
                source=source,
                symbol=symbol,
                status=final_status,
            ).inc()

    def set_ingestion_throughput(
        self, source: str, symbol: str, throughput: float
    ) -> None:
        """Record instantaneous ingestion throughput."""

        if not self._enabled:
            return

        self.data_ingestion_throughput.labels(source=source, symbol=symbol).set(
            max(0.0, float(throughput))
        )

    def record_tick_processed(self, source: str, symbol: str, count: int = 1) -> None:
        """Record that ticks were processed.

        Args:
            source: Data source name
            symbol: Trading symbol
            count: Number of ticks processed in the batch
        """
        if not self._enabled:
            return
        self.ticks_processed.labels(source=source, symbol=symbol).inc(count)

    def record_order_placed(
        self,
        exchange: str,
        symbol: str,
        order_type: str,
        status: str = "success",
        count: int = 1,
    ) -> None:
        """Record an order placement.

        Args:
            exchange: Exchange name
            symbol: Trading symbol
            order_type: Order type (market, limit, etc.)
            status: Order status
            count: Number of orders placed
        """
        if not self._enabled:
            return
        self.orders_placed.labels(
            exchange=exchange,
            symbol=symbol,
            order_type=order_type,
            status=status,
        ).inc(count)

    @contextmanager
    def measure_order_placement(
        self,
        exchange: str,
        symbol: str,
        order_type: str,
    ) -> Iterator[Dict[str, Any]]:
        """Context manager for measuring order placement latency and outcomes."""

        if not self._enabled:
            yield {}
            return

        start_time = time.time()
        ctx: Dict[str, Any] = {}
        status = "success"

        try:
            yield ctx
        except Exception:
            status = "error"
            raise
        finally:
            duration = time.time() - start_time
            final_status = self._resolve_status(ctx, status)
            self.order_placement_duration.labels(
                exchange=exchange,
                symbol=symbol,
            ).observe(duration)
            samples = self._order_submission_latency_samples[(exchange, symbol)]
            samples.append(duration)
            self._update_latency_quantiles(
                self.order_submission_latency_quantiles,
                {"exchange": exchange, "symbol": symbol},
                samples,
            )
            self.orders_placed.labels(
                exchange=exchange,
                symbol=symbol,
                order_type=order_type,
                status=final_status,
            ).inc()

    def set_open_positions(self, exchange: str, symbol: str, positions: float) -> None:
        """Update the gauge tracking open positions."""

        if not self._enabled:
            return
        self.open_positions.labels(exchange=exchange, symbol=symbol).set(positions)

    def set_open_incidents(self, severity: str, count: float) -> None:
        """Update the gauge tracking open incidents by severity."""

        if not self._enabled:
            return

        severity_label = self._normalise_label(severity, default="unknown")
        bounded_count = max(0.0, float(count))
        self.incidents_open.labels(severity=severity_label).set(bounded_count)

    def observe_incident_ack_latency(self, severity: str, duration: float) -> None:
        """Observe the acknowledgement latency for an incident."""

        if not self._enabled:
            return

        severity_label = self._normalise_label(severity, default="unknown")
        bounded_duration = max(0.0, float(duration))
        self.incident_ack_latency.labels(severity=severity_label).observe(
            bounded_duration
        )

    def observe_incident_resolution_latency(
        self, severity: str, duration: float
    ) -> None:
        """Observe the resolution latency for an incident."""

        if not self._enabled:
            return

        severity_label = self._normalise_label(severity, default="unknown")
        bounded_duration = max(0.0, float(duration))
        self.incident_resolution_latency.labels(severity=severity_label).observe(
            bounded_duration
        )

    def record_runbook_execution(
        self, runbook: str, outcome: str, count: float = 1.0
    ) -> None:
        """Record the execution of a production runbook."""

        if not self._enabled:
            return

        if count <= 0:
            return

        runbook_label = self._normalise_label(runbook, default="unknown")
        outcome_label = self._normalise_label(outcome, default="unknown")
        self.runbook_executions_total.labels(
            runbook=runbook_label, outcome=outcome_label
        ).inc(float(count))

    def set_lifecycle_phase_state(self, phase: str, state: str) -> None:
        """Update lifecycle phase state gauges."""

        if not self._enabled:
            return

        phase_label = self._normalise_label(phase, default="unknown")
        state_label = self._normalise_label(state, default="unknown")
        known_states = (
            "active",
            "standby",
            "maintenance",
            "degraded",
            "completed",
            "offline",
        )
        for candidate in known_states:
            value = 1.0 if candidate == state_label else 0.0
            self.lifecycle_phase_state.labels(phase=phase_label, state=candidate).set(
                value
            )
        if state_label not in known_states:
            self.lifecycle_phase_state.labels(phase=phase_label, state=state_label).set(
                1.0
            )

    def set_lifecycle_checkpoint_status(self, checkpoint: str, status: str) -> None:
        """Update lifecycle checkpoint status gauges."""

        if not self._enabled:
            return

        checkpoint_label = self._normalise_label(checkpoint, default="unknown")
        status_label = self._normalise_label(status, default="pending")
        known_statuses = ("pending", "in_progress", "passed", "blocked")
        for candidate in known_statuses:
            value = 1.0 if candidate == status_label else 0.0
            self.lifecycle_checkpoint_status.labels(
                checkpoint=checkpoint_label, status=candidate
            ).set(value)
        if status_label not in known_statuses:
            self.lifecycle_checkpoint_status.labels(
                checkpoint=checkpoint_label, status=status_label
            ).set(1.0)

    def record_lifecycle_transition(
        self, from_phase: str, to_phase: str, outcome: str = "success"
    ) -> None:
        """Record a lifecycle transition event."""

        if not self._enabled:
            return

        from_label = self._normalise_label(from_phase, default="unknown")
        to_label = self._normalise_label(to_phase, default="unknown")
        outcome_label = self._normalise_label(outcome, default="success")
        self.lifecycle_transition_total.labels(
            from_phase=from_label, to_phase=to_label, outcome=outcome_label
        ).inc()

    def record_order_fill_latency(
        self, exchange: str, symbol: str, duration: float
    ) -> None:
        """Observe latency from order submission to fill."""

        if not self._enabled:
            return
        samples = self._order_fill_latency_samples[(exchange, symbol)]
        samples.append(duration)
        self._update_latency_quantiles(
            self.order_fill_latency_quantiles,
            {"exchange": exchange, "symbol": symbol},
            samples,
        )

    def record_order_ack_latency(
        self, exchange: str, symbol: str, duration: float
    ) -> None:
        """Observe latency between order submission and venue acknowledgement."""

        if not self._enabled:
            return
        samples = self._order_ack_latency_samples[(exchange, symbol)]
        samples.append(duration)
        self._update_latency_quantiles(
            self.order_ack_latency_quantiles,
            {"exchange": exchange, "symbol": symbol},
            samples,
        )

    def record_signal_to_fill_latency(
        self,
        strategy: str,
        exchange: str,
        symbol: str,
        duration: float,
    ) -> None:
        """Observe latency from signal emission until the final fill completes."""

        if not self._enabled:
            return

        label_key = (strategy, exchange, symbol)
        samples = self._signal_to_fill_latency_samples[label_key]
        samples.append(duration)
        self._update_latency_quantiles(
            self.signal_to_fill_latency_quantiles,
            {"strategy": strategy, "exchange": exchange, "symbol": symbol},
            samples,
        )

    def set_strategy_score(self, strategy_name: str, score: float) -> None:
        """Record the latest strategy score."""

        if not self._enabled:
            return
        self.strategy_score.labels(strategy_name=strategy_name).set(score)

    def set_strategy_memory_size(self, size: int) -> None:
        """Update the number of strategies currently held in memory."""

        if not self._enabled:
            return
        self.strategy_memory_size.set(size)

    def record_regression_metrics(self, model: str, **metrics: float) -> None:
        """Record regression evaluation metrics for a given model identifier."""

        if not self._enabled:
            return
        for name, value in metrics.items():
            if value is None:
                continue
            self.regression_metrics.labels(model=model, metric=str(name)).set(
                float(value)
            )

    def record_equity_point(self, strategy: str, step: int, value: float) -> None:
        """Record a sample on the equity curve gauge."""

        if not self._enabled:
            return
        step_label = str(step)
        self.backtest_equity_curve.labels(strategy=strategy, step=step_label).set(value)
        recorded = self._equity_curve_cache[strategy]
        if step_label not in recorded:
            recorded.append(step_label)

    def record_equity_curve(
        self,
        strategy: str,
        series: Sequence[float] | NDArray[np.float64],
        *,
        max_points: int | None = None,
    ) -> None:
        """Record an equity curve using bounded cardinality sampling."""

        if not self._enabled:
            return

        limit = int(max_points or self._equity_curve_max_points)
        if limit <= 0:
            limit = 1

        values_list: list[float] | None = None
        if _NUMPY_AVAILABLE:
            values = np.asarray(series, dtype=float)
            total_points = int(values.size)
        else:
            values_list = [float(v) for v in series]
            total_points = len(values_list)

        if total_points == 0:
            self._clear_equity_curve(strategy)
            return

        stride = max(1, int(math.ceil(total_points / limit)))
        indices = list(range(0, total_points, stride))
        if indices[-1] != total_points - 1:
            indices.append(total_points - 1)

        sampled_steps = [str(index) for index in indices]
        if _NUMPY_AVAILABLE:
            sampled_values = values[indices]
        else:
            if values_list is None:  # pragma: no cover - defensive guard
                msg = "Expected list of values when NumPy is unavailable"
                raise RuntimeError(msg)
            sampled_values = [values_list[index] for index in indices]

        self._clear_equity_curve(strategy)

        for step_label, value in zip(sampled_steps, sampled_values, strict=True):
            self.backtest_equity_curve.labels(strategy=strategy, step=step_label).set(
                float(value)
            )

        self._equity_curve_cache[strategy] = sampled_steps

    def _clear_equity_curve(self, strategy: str) -> None:
        steps = self._equity_curve_cache.pop(strategy, [])
        for step_label in steps:
            try:
                self.backtest_equity_curve.remove(strategy, step_label)
            except KeyError:
                continue

    def record_environment_parity(
        self,
        *,
        strategy: str,
        status: str,
        deviations: Sequence["MetricDeviation"] | None = None,
    ) -> None:
        """Record the outcome of an environment parity evaluation."""

        if not self._enabled:
            return

        self.environment_parity_checks.labels(strategy=strategy, status=status).inc()

        if not deviations:
            return

        for deviation in deviations:
            self.environment_parity_metric_deviation.labels(
                strategy=strategy,
                metric=deviation.metric,
                baseline=deviation.baseline_environment,
                comparison=deviation.comparison_environment,
            ).set(deviation.absolute_difference)

    def render_prometheus(self) -> str:
        """Render the currently collected metrics in Prometheus text format."""

        if not self._enabled:
            return ""

        payload_bytes = (
            generate_latest(self.registry) if self.registry else generate_latest()
        )
        payload = payload_bytes.decode("utf-8")
        if "process_cpu_seconds_total" not in payload:
            cpu_seconds = time.process_time()
            payload = (
                payload
                + "\n"
                + "# HELP process_cpu_seconds_total Total user and system CPU time "
                + "spent in seconds.\n"
                + "# TYPE process_cpu_seconds_total counter\n"
                + f"process_cpu_seconds_total {cpu_seconds:.6f}\n"
            )
        return payload

    def record_risk_validation(self, symbol: str, outcome: str) -> None:
        """Record the result of a risk validation."""

        if not self._enabled:
            return
        self.risk_validation_total.labels(symbol=symbol, outcome=outcome).inc()

    def record_kill_switch_trigger(self, reason: str) -> None:
        """Record a kill switch trigger occurrence."""

        if not self._enabled:
            return
        self.kill_switch_triggers_total.labels(reason=reason).inc()

    def record_drawdown(self, drawdown_fraction: float) -> None:
        """Record the latest observed portfolio drawdown."""

        if not self._enabled:
            return

        if math.isnan(drawdown_fraction) or math.isinf(drawdown_fraction):
            return

        self.drawdown_percent.set(max(0.0, drawdown_fraction) * 100.0)

    def record_compliance_check(
        self,
        symbol: str,
        status: str,
        violations: Iterable[str] | None = None,
    ) -> None:
        """Record the outcome of a compliance check."""

        if not self._enabled:
            return

        self.compliance_checks_total.labels(symbol=symbol, status=status).inc()
        if not violations:
            return
        for violation in violations:
            self.compliance_violations_total.labels(
                symbol=symbol,
                violation_type=str(violation),
            ).inc()

    def record_watchdog_restart(self, watchdog: str, worker: str) -> None:
        """Record a watchdog-driven worker restart."""

        if not self._enabled:
            return
        self.watchdog_worker_restarts.labels(watchdog=watchdog, worker=worker).inc()

    def set_watchdog_live_probe(self, watchdog: str, healthy: bool) -> None:
        """Update the outcome of the most recent watchdog live probe."""

        if not self._enabled:
            return
        self.watchdog_live_probe_status.labels(watchdog=watchdog).set(
            1.0 if healthy else 0.0
        )

    def set_watchdog_heartbeat(
        self, watchdog: str, timestamp: float | None = None
    ) -> None:
        """Record the timestamp associated with the latest watchdog heartbeat."""

        if not self._enabled:
            return
        if timestamp is None:
            timestamp = time.time()
        self.watchdog_last_heartbeat.labels(watchdog=watchdog).set(float(timestamp))

    def observe_health_check_latency(self, check_name: str, duration: float) -> None:
        """Observe the execution time of a health check probe."""

        if not self._enabled:
            return

        self.health_check_latency.labels(check_name=check_name).observe(
            max(0.0, float(duration))
        )

    def set_health_check_status(self, check_name: str, healthy: bool) -> None:
        """Update the status gauge tracking the latest health probe outcome."""

        if not self._enabled:
            return

        self.health_check_status.labels(check_name=check_name).set(
            1.0 if healthy else 0.0
        )

    def observe_database_size(
        self,
        *,
        database: str,
        host: str,
        size_bytes: float,
    ) -> None:
        """Record the current database size and derived growth."""

        if not self._enabled:
            return

        database_label = self._normalise_label(database, default="default")
        host_label = self._normalise_label(host, default="unknown")
        size = max(0.0, float(size_bytes))
        labels = {"database": database_label, "host": host_label}

        self.database_size_bytes.labels(**labels).set(size)

        previous = self._database_size_cache.get((database_label, host_label))
        growth = 0.0 if previous is None else size - previous
        self.database_size_growth.labels(**labels).set(growth)
        self._database_size_cache[(database_label, host_label)] = size

    def observe_database_query(
        self,
        *,
        database: str,
        host: str,
        statement_type: str,
        status: str,
        duration: float,
    ) -> None:
        """Record latency and counters for a database query execution."""

        if not self._enabled:
            return

        database_label = self._normalise_label(database, default="default")
        host_label = self._normalise_label(host, default="unknown")
        statement_label = self._normalise_label(statement_type, default="other").lower()
        status_label = self._normalise_label(status, default="success").lower()
        labels = {
            "database": database_label,
            "host": host_label,
            "statement_type": statement_label,
            "status": status_label,
        }

        bounded_duration = max(0.0, float(duration))
        self.database_query_latency.labels(**labels).observe(bounded_duration)
        self.database_query_total.labels(**labels).inc()

    def observe_cache_warmup(
        self,
        cache_name: str,
        strategy: str,
        duration: float,
        *,
        rows: int | None = None,
    ) -> None:
        """Record the latency (and optional size) of a cache warm-up run."""

        if not self._enabled:
            return

        self.cache_warmup_duration.labels(
            cache_name=cache_name, strategy=strategy
        ).observe(max(0.0, float(duration)))

        if rows is not None:
            self.cache_warmup_rows.labels(cache_name=cache_name, strategy=strategy).set(
                max(0.0, float(rows))
            )

    def set_cache_readiness(self, cache_name: str, ready: bool) -> None:
        """Update readiness gauge for a managed cache."""

        if not self._enabled:
            return

        self.cache_readiness_status.labels(cache_name=cache_name).set(
            1.0 if ready else 0.0
        )

    def update_cache_hit_rate(self, cache_name: str, hit_rate: float) -> None:
        """Observe the current hit rate of a cache."""

        if not self._enabled:
            return

        bounded = max(0.0, min(1.0, float(hit_rate)))
        self.cache_hit_rate.labels(cache_name=cache_name).set(bounded)

    def observe_cache_cold_latency(self, cache_name: str, latency: float) -> None:
        """Record the latency of a cold cache request."""

        if not self._enabled:
            return

        self.cache_cold_latency.labels(cache_name=cache_name).observe(
            max(0.0, float(latency))
        )

    def increment_cache_cold_request(self, cache_name: str, outcome: str) -> None:
        """Increment counters describing cold cache request outcomes."""

        if not self._enabled:
            return

        self.cache_cold_requests.labels(cache_name=cache_name, outcome=outcome).inc()

    def record_cache_degradation(self, cache_name: str, reason: str) -> None:
        """Record an emitted cache degradation signal for observability."""

        if not self._enabled:
            return

        self.cache_degradation_events.labels(cache_name=cache_name, reason=reason).inc()

    @staticmethod
    def _normalise_label(value: object, *, default: str) -> str:
        if value is None:
            return default
        if isinstance(value, str):
            candidate = value.strip()
        else:
            candidate = str(value).strip()
        return candidate or default


# Global metrics collector instance
_collector: Optional[MetricsCollector] = None


def get_metrics_collector(registry: Optional[Any] = None) -> MetricsCollector:
    """Get the global metrics collector instance.

    Args:
        registry: Prometheus registry (uses default if None)

    Returns:
        MetricsCollector instance
    """
    global _collector
    if _collector is None:
        _collector = MetricsCollector(registry)
        return _collector

    if registry is None:
        return _collector

    try:  # pragma: no cover - optional dependency guard
        from prometheus_client import REGISTRY as _default_registry
    except Exception:  # pragma: no cover - defensive fallback
        _default_registry = None

    current_registry = _collector.registry
    if registry is current_registry:
        return _collector

    # Treat a collector built with the implicit default registry as equivalent
    # to the explicit global REGISTRY to avoid duplicate metric registration.
    if current_registry is None and registry is _default_registry:
        return _collector

    _collector = MetricsCollector(registry)
    return _collector


def start_metrics_server(port: int = 8000, addr: str = "") -> None:
    """Start the Prometheus metrics HTTP server.

    Args:
        port: Port to listen on
        addr: Address to bind to (empty string for all interfaces)
    """
    if not PROMETHEUS_AVAILABLE:
        raise RuntimeError("prometheus_client is not installed")
    start_http_server(port, addr)


def start_metrics_exporter_process(
    port: int = 8000, addr: str = ""
) -> multiprocessing.Process:
    """Spawn a Prometheus exporter in a dedicated process."""

    if not PROMETHEUS_AVAILABLE:
        raise RuntimeError("prometheus_client is not installed")

    from observability.exporters import start_prometheus_exporter_process

    return start_prometheus_exporter_process(port=port, addr=addr)


def stop_metrics_exporter_process(
    process: Optional[multiprocessing.Process], *, timeout: float = 5.0
) -> None:
    """Terminate a previously spawned Prometheus exporter process."""

    if process is None:
        return

    from observability.exporters import stop_exporter_process

    stop_exporter_process(process, timeout=timeout)


__all__ = [
    "MetricsCollector",
    "get_metrics_collector",
    "start_metrics_server",
    "start_metrics_exporter_process",
    "stop_metrics_exporter_process",
]
