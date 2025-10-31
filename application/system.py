"""High-level orchestration primitives tying TradePulse components together."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import (
    AsyncIterator,
    Callable,
    Iterable,
    Mapping,
    MutableMapping,
    Sequence,
)

import numpy as np
import pandas as pd

from analytics.signals.pipeline import FeaturePipelineConfig, SignalFeaturePipeline
from application.trading import signal_to_dto
from core.data.async_ingestion import AsyncDataIngestor
from core.data.connectors.market import BaseMarketDataConnector
from core.data.ingestion import DataIngestor
from core.data.models import InstrumentType, PriceTick
from core.utils.metrics import get_metrics_collector
from domain import Order, OrderSide, OrderType, Signal, SignalAction
from execution.connectors import ExecutionConnector
from execution.live_loop import LiveExecutionLoop, LiveLoopConfig
from execution.risk import RiskLimits, RiskManager
from src.security import AccessController, AccessDeniedError

__all__ = [
    "ExchangeAdapterConfig",
    "LiveLoopSettings",
    "TradePulseSystemConfig",
    "TradePulseSystem",
]


@dataclass(slots=True)
class ExchangeAdapterConfig:
    """Declarative configuration describing an execution venue adapter."""

    name: str
    connector: ExecutionConnector
    credentials: Mapping[str, str] | None = None


@dataclass(slots=True)
class LiveLoopSettings:
    """Configuration used when instantiating :class:`LiveExecutionLoop`."""

    state_dir: Path = field(default_factory=lambda: Path(".tradepulse/state"))
    submission_interval: float = 0.25
    fill_poll_interval: float = 1.0
    heartbeat_interval: float = 10.0
    max_backoff: float = 60.0

    def build_config(
        self,
        *,
        credentials: Mapping[str, Mapping[str, str]] | None,
    ) -> LiveLoopConfig:
        """Return a hydrated :class:`LiveLoopConfig` instance."""

        return LiveLoopConfig(
            state_dir=self.state_dir,
            submission_interval=self.submission_interval,
            fill_poll_interval=self.fill_poll_interval,
            heartbeat_interval=self.heartbeat_interval,
            max_backoff=self.max_backoff,
            credentials=credentials,
        )


@dataclass(slots=True)
class TradePulseSystemConfig:
    """Bundle settings required to assemble a :class:`TradePulseSystem`."""

    venues: Sequence[ExchangeAdapterConfig]
    feature_pipeline: FeaturePipelineConfig = field(
        default_factory=FeaturePipelineConfig
    )
    risk_limits: RiskLimits = field(default_factory=RiskLimits)
    live_settings: LiveLoopSettings = field(default_factory=LiveLoopSettings)
    allowed_data_roots: Iterable[str | Path] | None = None
    max_csv_bytes: int | None = None
    market_data_connectors: (
        Mapping[str, BaseMarketDataConnector | Callable[[], BaseMarketDataConnector]]
        | None
    ) = None


class TradePulseSystem:
    """Facilitate end-to-end orchestration across ingestion, analytics, and execution."""

    def __init__(
        self,
        config: TradePulseSystemConfig,
        *,
        data_ingestor: DataIngestor | None = None,
        async_data_ingestor: AsyncDataIngestor | None = None,
        risk_manager: RiskManager | None = None,
        access_controller: AccessController | None = None,
    ) -> None:
        if not config.venues:
            raise ValueError("At least one execution venue must be configured")

        self._config = config
        self._data_ingestor = data_ingestor or DataIngestor(
            allowed_roots=config.allowed_data_roots,
            max_csv_bytes=config.max_csv_bytes,
        )
        self._async_ingestor = async_data_ingestor or AsyncDataIngestor(
            allowed_roots=config.allowed_data_roots,
            max_csv_bytes=config.max_csv_bytes,
            market_connectors=config.market_data_connectors,
        )
        self._pipeline = SignalFeaturePipeline(config.feature_pipeline)
        self._risk_manager = risk_manager or RiskManager(config.risk_limits)
        self._metrics = get_metrics_collector()
        self._access_controller = access_controller
        self._clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

        connectors: MutableMapping[str, ExecutionConnector] = {}
        credentials: MutableMapping[str, Mapping[str, str]] = {}
        for venue in config.venues:
            key = venue.name.lower()
            if key in connectors:
                raise ValueError(f"Duplicate venue name configured: {venue.name}")
            connectors[key] = venue.connector
            if venue.credentials:
                credentials[key] = dict(venue.credentials)

        self._connectors: Mapping[str, ExecutionConnector] = dict(connectors)
        self._credentials: Mapping[str, Mapping[str, str]] = dict(credentials)
        self._live_loop: LiveExecutionLoop | None = None

        self._last_symbol: str | None = None
        self._last_venue: str | None = None
        self._last_ingestion_started_at: datetime | None = None
        self._last_ingestion_completed_at: datetime | None = None
        self._last_ingestion_duration_seconds: float | None = None
        self._last_ingestion_error: str | None = None
        self._last_ingestion_symbol: str | None = None
        self._last_signal_generated_at: datetime | None = None
        self._last_signal_latency_seconds: float | None = None
        self._last_signal_error: str | None = None
        self._last_execution_submission_at: datetime | None = None
        self._last_execution_error: str | None = None

    # ------------------------------------------------------------------
    # Accessors
    @property
    def data_ingestor(self) -> DataIngestor:
        """Return the synchronous ingestion service."""

        return self._data_ingestor

    @property
    def async_data_ingestor(self) -> AsyncDataIngestor:
        """Return the asynchronous ingestion service."""

        return self._async_ingestor

    @property
    def feature_pipeline(self) -> SignalFeaturePipeline:
        """Return the configured feature pipeline."""

        return self._pipeline

    @property
    def risk_manager(self) -> RiskManager:
        """Return the shared risk manager instance."""

        return self._risk_manager

    @property
    def connector_names(self) -> tuple[str, ...]:
        """Return the canonical names of configured connectors."""

        return tuple(sorted(self._connectors.keys()))

    def get_connector(self, venue: str) -> ExecutionConnector:
        """Return the connector registered for ``venue``."""

        key = venue.lower()
        try:
            return self._connectors[key]
        except KeyError as exc:
            raise LookupError(f"Unknown execution venue: {venue}") from exc

    def connector_credentials(
        self,
        venue: str,
        *,
        actor: str | None = None,
        roles: Iterable[str] | None = None,
    ) -> Mapping[str, str] | None:
        """Return credentials associated with ``venue`` if configured."""

        creds = self._credentials.get(venue.lower())
        if creds is None:
            return None
        controller = self._access_controller
        if controller is not None:
            try:
                controller.require(
                    "read_exchange_keys",
                    actor=actor,
                    roles=roles or (),
                    resource=venue.lower(),
                )
            except AccessDeniedError as exc:
                raise AccessDeniedError(
                    f"Actor '{actor or 'system'}' lacks permission to read credentials for {venue}"
                ) from exc
        return creds

    @property
    def last_ingestion_started_at(self) -> datetime | None:
        return self._last_ingestion_started_at

    @property
    def last_ingestion_completed_at(self) -> datetime | None:
        return self._last_ingestion_completed_at

    @property
    def last_ingestion_duration_seconds(self) -> float | None:
        return self._last_ingestion_duration_seconds

    @property
    def last_ingestion_error(self) -> str | None:
        return self._last_ingestion_error

    @property
    def last_ingestion_symbol(self) -> str | None:
        return self._last_ingestion_symbol

    @property
    def last_signal_generated_at(self) -> datetime | None:
        return self._last_signal_generated_at

    @property
    def last_signal_latency_seconds(self) -> float | None:
        return self._last_signal_latency_seconds

    @property
    def last_signal_error(self) -> str | None:
        return self._last_signal_error

    @property
    def last_execution_submission_at(self) -> datetime | None:
        return self._last_execution_submission_at

    @property
    def last_execution_error(self) -> str | None:
        return self._last_execution_error

    # ------------------------------------------------------------------
    # Data ingestion & feature engineering
    def ingest_csv(
        self,
        path: str | Path,
        *,
        symbol: str,
        venue: str,
        instrument_type: InstrumentType = InstrumentType.SPOT,
        market: str | None = None,
        required_fields: Iterable[str] | None = None,
        timestamp_field: str = "ts",
        price_field: str = "price",
        volume_field: str = "volume",
    ) -> pd.DataFrame:
        """Load historical ticks from *path* and return a normalised OHLCV frame."""

        self._last_ingestion_started_at = self._clock()
        self._last_ingestion_symbol = symbol
        start = perf_counter()
        records: list[PriceTick] = []
        with self._metrics.measure_data_ingestion("csv", symbol) as ctx:
            try:
                self._data_ingestor.historical_csv(
                    str(path),
                    records.append,
                    required_fields=required_fields,
                    timestamp_field=timestamp_field,
                    price_field=price_field,
                    volume_field=volume_field,
                    symbol=symbol,
                    venue=venue,
                    instrument_type=instrument_type,
                    market=market,
                )
            except Exception as exc:
                ctx["status"] = "error"
                self._last_ingestion_error = str(exc)
                self._last_ingestion_completed_at = self._clock()
                self._last_ingestion_duration_seconds = perf_counter() - start
                raise
            else:
                ctx["status"] = "success"
                self._last_ingestion_error = None

        if not records:
            raise ValueError(f"No ticks ingested from {path}")

        frame = self._ticks_to_frame(records)
        duration = perf_counter() - start
        self._last_ingestion_completed_at = self._clock()
        self._last_ingestion_duration_seconds = duration
        self._metrics.record_tick_processed("csv", symbol, len(records))
        if duration > 0:
            self._metrics.set_ingestion_throughput(
                "csv", symbol, len(records) / duration
            )
        self._last_symbol = symbol
        self._last_venue = venue
        return frame

    def stream_market_data(
        self,
        source: str,
        symbol: str,
        *,
        instrument_type: InstrumentType = InstrumentType.SPOT,
        interval_ms: int = 1000,
        max_ticks: int | None = None,
    ) -> AsyncIterator[PriceTick]:
        """Return an async iterator streaming live market data from *source*."""

        return self._async_ingestor.stream_ticks(
            source,
            symbol,
            instrument_type=instrument_type,
            interval_ms=interval_ms,
            max_ticks=max_ticks,
        )

    async def fetch_market_snapshot(
        self,
        source: str,
        *,
        symbol: str,
        instrument_type: InstrumentType = InstrumentType.SPOT,
        **kwargs,
    ) -> list[PriceTick]:
        """Fetch a snapshot of market data from a configured connector."""

        return await self._async_ingestor.fetch_market_snapshot(
            source,
            symbol=symbol,
            instrument_type=instrument_type,
            **kwargs,
        )

    def build_feature_frame(self, market_frame: pd.DataFrame) -> pd.DataFrame:
        """Return a feature-enriched frame aligned with ``market_frame``."""

        features = self._pipeline.transform(market_frame)
        combined = market_frame.join(features, how="inner")
        combined.sort_index(inplace=True)
        return combined

    # ------------------------------------------------------------------
    # Signal generation helpers
    def generate_signals(
        self,
        feature_frame: pd.DataFrame,
        *,
        strategy: Callable[[np.ndarray], np.ndarray],
        symbol: str | None = None,
    ) -> list[Signal]:
        """Run *strategy* over ``feature_frame`` and return domain signals."""

        strategy_name = getattr(strategy, "__name__", strategy.__class__.__name__)
        resolved_symbol = symbol or self._last_symbol
        if resolved_symbol is None:
            raise ValueError(
                "symbol must be provided when no ingestion has been performed"
            )

        price_col = self._pipeline.config.price_col
        if price_col not in feature_frame.columns:
            raise KeyError(f"Feature frame is missing '{price_col}' column")

        aligned = feature_frame.dropna()
        if aligned.empty:
            raise ValueError("Feature frame does not contain any fully populated rows")

        prices = aligned[price_col].to_numpy(dtype=float)
        start = perf_counter()
        with self._metrics.measure_signal_generation(strategy_name) as ctx:
            try:
                raw_scores = np.asarray(strategy(prices), dtype=float)
                if raw_scores.shape[0] != aligned.shape[0]:
                    raise ValueError(
                        "Strategy output length must match feature frame rows"
                    )

                valid_mask = np.isfinite(raw_scores)
                if not valid_mask.all():
                    dropped = int((~valid_mask).sum())
                    ctx["dropped_invalid_scores"] = dropped
                    raw_scores = raw_scores[valid_mask]
                    aligned = aligned.iloc[valid_mask]
                if raw_scores.size == 0:
                    raise ValueError("Strategy produced no valid signal scores")

                signals: list[Signal] = []
                for timestamp, score in zip(aligned.index, raw_scores):
                    if score > 0:
                        action = SignalAction.BUY
                    elif score < 0:
                        action = SignalAction.SELL
                    else:
                        action = SignalAction.HOLD

                    confidence = float(np.clip(abs(score), 0.0, 1.0))
                    metadata = {"score": float(score)}
                    signals.append(
                        Signal(
                            symbol=resolved_symbol,
                            action=action,
                            confidence=confidence,
                            timestamp=pd.Timestamp(timestamp).to_pydatetime(),
                            metadata=metadata,
                        )
                    )
            except Exception as exc:
                ctx["status"] = "error"
                self._last_signal_error = str(exc)
                self._last_signal_generated_at = self._clock()
                self._last_signal_latency_seconds = perf_counter() - start
                raise
            else:
                ctx["status"] = "success"
                self._last_signal_error = None

        duration = perf_counter() - start
        self._last_signal_generated_at = self._clock()
        self._last_signal_latency_seconds = duration
        return signals

    @staticmethod
    def signals_to_dtos(signals: Iterable[Signal]) -> list[dict[str, object]]:
        """Serialise ``signals`` into transport-friendly payloads."""

        return [signal_to_dto(signal) for signal in signals]

    # ------------------------------------------------------------------
    # Live execution orchestration
    def ensure_live_loop(self) -> LiveExecutionLoop:
        """Return a lazily initialised :class:`LiveExecutionLoop`."""

        if self._live_loop is None:
            credentials = self._credentials or None
            config = self._config.live_settings.build_config(credentials=credentials)
            self._live_loop = LiveExecutionLoop(
                self._connectors, self._risk_manager, config=config
            )
        return self._live_loop

    @property
    def live_loop(self) -> LiveExecutionLoop | None:
        """Expose the instantiated live execution loop if available."""

        return self._live_loop

    def submit_signal(
        self,
        signal: Signal,
        *,
        venue: str,
        quantity: float,
        price: float | None = None,
        order_type: OrderType | str | None = None,
        correlation_id: str | None = None,
    ) -> Order:
        """Convert *signal* into an order and enqueue it via the live loop."""

        venue_key = venue.lower()
        if venue_key not in self._connectors:
            raise LookupError(f"Unknown execution venue: {venue}")
        if signal.action in {SignalAction.HOLD}:
            raise ValueError("Cannot submit HOLD signals as execution orders")

        if quantity <= 0:
            raise ValueError("quantity must be positive")

        if order_type is None:
            order_type = OrderType.MARKET if price is None else OrderType.LIMIT
        order_type = OrderType(order_type)

        if signal.action == SignalAction.EXIT:
            side = OrderSide.SELL
        else:
            side = OrderSide(signal.action.value)

        order = Order(
            symbol=signal.symbol,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
        )

        loop = self.ensure_live_loop()
        derived_correlation = (
            correlation_id
            or f"{signal.symbol}-{int(signal.timestamp.timestamp() * 1e9)}"
        )
        try:
            submitted = loop.submit_order(
                venue_key, order, correlation_id=derived_correlation
            )
        except Exception as exc:
            self._last_execution_error = str(exc)
            raise
        else:
            self._last_execution_error = None
            self._last_execution_submission_at = self._clock()
            return submitted

    # ------------------------------------------------------------------
    # Internal helpers
    @staticmethod
    def _ticks_to_frame(ticks: Sequence[PriceTick]) -> pd.DataFrame:
        records: list[dict[str, object]] = []
        for tick in ticks:
            records.append(
                {
                    "timestamp": tick.timestamp,
                    "open": float(tick.price),
                    "high": float(tick.price),
                    "low": float(tick.price),
                    "close": float(tick.price),
                    "volume": float(tick.volume),
                }
            )

        frame = pd.DataFrame.from_records(records).set_index("timestamp").sort_index()
        index = pd.DatetimeIndex(pd.to_datetime(frame.index))
        if index.tz is None:
            index = index.tz_localize("UTC")
        else:
            index = index.tz_convert("UTC")
        frame.index = index
        return frame
