"""Transaction Cost Analysis (TCA) module.

This module aggregates execution data to produce a comprehensive transaction
cost analysis covering latency, slippage, liquidity conditions, benchmark
comparisons, cost attribution, venue comparisons, and periodic reporting.  It
is intentionally dependency free so it can be embedded in latency sensitive
trade execution stacks while remaining fully testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import floor
from statistics import mean
from typing import Mapping, MutableMapping, Sequence

from .execution_quality import (
    FillSample,
    implementation_shortfall,
    vwap,
    vwap_slippage,
)

__all__ = [
    "FillDetail",
    "OrderLifecycle",
    "MarketVolumeSample",
    "LiquiditySample",
    "BenchmarkPriceSample",
    "LatencyDistribution",
    "LatencyReport",
    "SlippageReport",
    "LiquidityReport",
    "BenchmarkReport",
    "CostBreakdown",
    "BrokerVenueBreakdown",
    "PeriodicTCARecord",
    "TCAReport",
    "TransactionCostAnalyzer",
]


SideLiteral = str


def _normalise_side(side: SideLiteral) -> SideLiteral:
    side_lower = side.lower()
    if side_lower not in {"buy", "sell"}:
        raise ValueError("side must be 'buy' or 'sell'")
    return side_lower


@dataclass(frozen=True, slots=True)
class FillDetail:
    """Augmented fill sample with routing metadata."""

    quantity: float
    price: float
    timestamp: float
    broker: str
    venue: str
    fees: float = 0.0

    def __post_init__(self) -> None:
        if self.quantity <= 0.0:
            raise ValueError("quantity must be positive")
        if self.price <= 0.0:
            raise ValueError("price must be positive")
        if not self.broker:
            raise ValueError("broker must be a non-empty string")
        if not self.venue:
            raise ValueError("venue must be a non-empty string")

    def as_fill_sample(self) -> FillSample:
        return FillSample(quantity=self.quantity, price=self.price, fees=self.fees)


@dataclass(frozen=True, slots=True)
class OrderLifecycle:
    """Lifecycle timestamps for an order routed to market."""

    order_id: str
    submitted_ts: float
    acknowledged_ts: float | None
    completed_ts: float | None

    def __post_init__(self) -> None:
        if not self.order_id:
            raise ValueError("order_id must be a non-empty string")

    def submit_to_ack(self) -> float | None:
        if self.acknowledged_ts is None:
            return None
        return max(0.0, float(self.acknowledged_ts) - float(self.submitted_ts))

    def ack_to_complete(self) -> float | None:
        if self.acknowledged_ts is None or self.completed_ts is None:
            return None
        return max(0.0, float(self.completed_ts) - float(self.acknowledged_ts))

    def submit_to_complete(self) -> float | None:
        if self.completed_ts is None:
            return None
        return max(0.0, float(self.completed_ts) - float(self.submitted_ts))


@dataclass(frozen=True, slots=True)
class MarketVolumeSample:
    """Market-wide traded volume for a period."""

    timestamp: float
    volume: float

    def __post_init__(self) -> None:
        if self.volume < 0.0:
            raise ValueError("volume must be non-negative")


@dataclass(frozen=True, slots=True)
class LiquiditySample:
    """Displayed liquidity snapshot for a venue."""

    timestamp: float
    displayed_volume: float
    spread_bps: float | None = None

    def __post_init__(self) -> None:
        if self.displayed_volume < 0.0:
            raise ValueError("displayed_volume must be non-negative")
        if self.spread_bps is not None and self.spread_bps < 0.0:
            raise ValueError("spread_bps must be non-negative when provided")


@dataclass(frozen=True, slots=True)
class BenchmarkPriceSample:
    """Benchmark price used for VWAP/POV comparisons."""

    timestamp: float
    price: float
    vwap_window_volume: float | None = None

    def __post_init__(self) -> None:
        if self.price <= 0.0:
            raise ValueError("price must be positive")
        if self.vwap_window_volume is not None and self.vwap_window_volume < 0.0:
            raise ValueError("vwap_window_volume must be non-negative when provided")


@dataclass(frozen=True, slots=True)
class LatencyDistribution:
    """Descriptive statistics for a latency dimension."""

    count: float
    mean: float
    p50: float
    p95: float
    max: float


@dataclass(frozen=True, slots=True)
class LatencyReport:
    """Latency statistics across the order life cycle."""

    submit_to_ack: LatencyDistribution
    ack_to_fill: LatencyDistribution
    submit_to_complete: LatencyDistribution


@dataclass(frozen=True, slots=True)
class SlippageReport:
    """Slippage diagnostics relative to key benchmarks."""

    arrival_slippage: float
    vwap_slippage: float
    implementation_shortfall: float
    per_share_shortfall: float


@dataclass(frozen=True, slots=True)
class LiquidityReport:
    """Liquidity conditions experienced during execution."""

    average_displayed_volume: float
    coverage_ratio: float
    book_pressure: float
    median_spread_bps: float


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """Benchmark analytics for TCA."""

    trade_vwap: float
    market_vwap: float
    participation_rate: float
    implementation_shortfall: float


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    """Cost attribution results."""

    explicit_fees: float
    slippage_cost: float
    opportunity_cost: float
    total_cost: float


@dataclass(frozen=True, slots=True)
class BrokerVenueBreakdown:
    """Performance metrics per broker and venue."""

    broker: str
    venue: str
    quantity: float
    average_price: float
    fees: float
    fill_count: int
    cost_per_share: float


@dataclass(frozen=True, slots=True)
class PeriodicTCARecord:
    """Periodic execution summary for reporting."""

    start_timestamp: float
    end_timestamp: float
    executed_quantity: float
    vwap: float
    participation_rate: float
    slippage: float


@dataclass(frozen=True, slots=True)
class TCAReport:
    """Immutable TCA output payload."""

    executed_quantity: float
    latency: LatencyReport
    slippage: SlippageReport
    liquidity: LiquidityReport
    benchmarks: BenchmarkReport
    cost_breakdown: CostBreakdown
    recommendations: tuple[str, ...]
    broker_comparison: tuple[BrokerVenueBreakdown, ...]
    periodic: tuple[PeriodicTCARecord, ...]


FillInput = Mapping[str, object] | FillDetail
OrderLifecycleInput = Mapping[str, object] | OrderLifecycle
MarketVolumeInput = Mapping[str, object] | MarketVolumeSample
LiquidityInput = Mapping[str, object] | LiquiditySample
BenchmarkPriceInput = Mapping[str, object] | BenchmarkPriceSample


def _coerce_fill(fill: FillInput) -> FillDetail:
    if isinstance(fill, FillDetail):
        return fill
    broker = str(fill["broker"])
    venue = str(fill["venue"])
    timestamp = float(fill["timestamp"])
    quantity = float(fill.get("quantity") or fill.get("qty"))
    price = float(fill["price"])
    fees = float(fill.get("fees", 0.0))
    return FillDetail(quantity=quantity, price=price, fees=fees, timestamp=timestamp, broker=broker, venue=venue)


def _coerce_order(order: OrderLifecycleInput) -> OrderLifecycle:
    if isinstance(order, OrderLifecycle):
        return order
    return OrderLifecycle(
        order_id=str(order["order_id"]),
        submitted_ts=float(order["submitted_ts"]),
        acknowledged_ts=(None if order.get("acknowledged_ts") is None else float(order["acknowledged_ts"])),
        completed_ts=(None if order.get("completed_ts") is None else float(order["completed_ts"])),
    )


def _coerce_market_volume(sample: MarketVolumeInput) -> MarketVolumeSample:
    if isinstance(sample, MarketVolumeSample):
        return sample
    return MarketVolumeSample(timestamp=float(sample["timestamp"]), volume=float(sample.get("volume", 0.0)))


def _coerce_liquidity(sample: LiquidityInput) -> LiquiditySample:
    if isinstance(sample, LiquiditySample):
        return sample
    spread_key = "spread_bps" if "spread_bps" in sample else "spread"
    spread = sample.get(spread_key)
    return LiquiditySample(
        timestamp=float(sample["timestamp"]),
        displayed_volume=float(sample.get("displayed_volume", 0.0)),
        spread_bps=(None if spread is None else float(spread)),
    )


def _coerce_benchmark(sample: BenchmarkPriceInput) -> BenchmarkPriceSample:
    if isinstance(sample, BenchmarkPriceSample):
        return sample
    return BenchmarkPriceSample(
        timestamp=float(sample["timestamp"]),
        price=float(sample["price"]),
        vwap_window_volume=(
            None if sample.get("vwap_window_volume") is None else float(sample["vwap_window_volume"])
        ),
    )


def _percentile(samples: Sequence[float], p: float) -> float:
    if not samples:
        return 0.0
    if not 0.0 <= p <= 1.0:
        raise ValueError("percentile must be between 0 and 1")
    ordered = sorted(samples)
    if len(ordered) == 1:
        return ordered[0]
    rank = p * (len(ordered) - 1)
    low_idx = floor(rank)
    high_idx = min(len(ordered) - 1, low_idx + 1)
    if low_idx == high_idx:
        return ordered[low_idx]
    weight = rank - low_idx
    return ordered[low_idx] + (ordered[high_idx] - ordered[low_idx]) * weight


def _compute_distribution(samples: Sequence[float]) -> LatencyDistribution:
    if not samples:
        return LatencyDistribution(count=0.0, mean=0.0, p50=0.0, p95=0.0, max=0.0)
    ordered = sorted(samples)
    return LatencyDistribution(
        count=float(len(ordered)),
        mean=mean(ordered),
        p50=_percentile(ordered, 0.5),
        p95=_percentile(ordered, 0.95),
        max=ordered[-1],
    )


def _bucket_key(timestamp: float, bucket_seconds: float) -> float:
    if bucket_seconds <= 0:
        raise ValueError("bucket_seconds must be positive")
    return float(floor(timestamp / bucket_seconds) * bucket_seconds)


class TransactionCostAnalyzer:
    """High level orchestrator for transaction cost analysis."""

    def __init__(self, bucket_seconds: float = 900.0) -> None:
        if bucket_seconds <= 0.0:
            raise ValueError("bucket_seconds must be positive")
        self._bucket_seconds = float(bucket_seconds)

    @property
    def bucket_seconds(self) -> float:
        return self._bucket_seconds

    def generate_report(
        self,
        *,
        side: SideLiteral,
        arrival_price: float,
        target_quantity: float,
        fills: Sequence[FillInput],
        orders: Sequence[OrderLifecycleInput] | None = None,
        market_volumes: Sequence[MarketVolumeInput] | None = None,
        liquidity_samples: Sequence[LiquidityInput] | None = None,
        benchmark_prices: Sequence[BenchmarkPriceInput] | None = None,
    ) -> TCAReport:
        side_norm = _normalise_side(side)
        if arrival_price <= 0.0:
            raise ValueError("arrival_price must be positive")
        if target_quantity < 0.0:
            raise ValueError("target_quantity must be non-negative")

        coerced_fills = tuple(_coerce_fill(fill) for fill in fills)
        fill_samples = tuple(fill.as_fill_sample() for fill in coerced_fills)
        coerced_orders = tuple(_coerce_order(order) for order in (orders or ()))
        coerced_market_volumes = tuple(_coerce_market_volume(sample) for sample in (market_volumes or ()))
        coerced_liquidity = tuple(_coerce_liquidity(sample) for sample in (liquidity_samples or ()))
        coerced_benchmarks = tuple(_coerce_benchmark(sample) for sample in (benchmark_prices or ()))

        executed_quantity = sum(fill.quantity for fill in coerced_fills if fill.quantity > 0.0)
        total_fees = sum(fill.fees for fill in coerced_fills)
        trade_vwap = vwap(fill_samples) if fill_samples else 0.0

        market_vwap = self._compute_market_vwap(coerced_benchmarks) if coerced_benchmarks else arrival_price
        impl_shortfall = implementation_shortfall(
            side_norm,
            arrival_price,
            fill_samples,
            explicit_fees=0.0,
        )
        per_share_shortfall = impl_shortfall / executed_quantity if executed_quantity > 0.0 else 0.0
        arrival_slip = vwap_slippage(side_norm, arrival_price, fill_samples) if fill_samples else 0.0
        vwap_slip = vwap_slippage(side_norm, market_vwap, fill_samples) if fill_samples else 0.0

        participation_rate = self._compute_participation_rate(coerced_market_volumes, executed_quantity)

        latency_report = self._build_latency_report(coerced_orders)
        liquidity_report = self._build_liquidity_report(
            coerced_liquidity,
            coerced_fills,
            executed_quantity,
        )

        slippage_report = SlippageReport(
            arrival_slippage=arrival_slip,
            vwap_slippage=vwap_slip,
            implementation_shortfall=impl_shortfall,
            per_share_shortfall=per_share_shortfall,
        )

        benchmark_report = BenchmarkReport(
            trade_vwap=trade_vwap,
            market_vwap=market_vwap,
            participation_rate=participation_rate,
            implementation_shortfall=impl_shortfall,
        )

        slippage_cost = vwap_slip * executed_quantity
        opportunity_cost = self._compute_opportunity_cost(
            side_norm,
            arrival_price,
            target_quantity,
            executed_quantity,
            coerced_benchmarks,
            coerced_fills,
        )
        total_cost = total_fees + slippage_cost + opportunity_cost
        cost_breakdown = CostBreakdown(
            explicit_fees=total_fees,
            slippage_cost=slippage_cost,
            opportunity_cost=opportunity_cost,
            total_cost=total_cost,
        )

        broker_comparison = self._build_broker_comparison(
            coerced_fills,
            side_norm,
            market_vwap,
        )

        periodic = self._build_periodic_records(
            coerced_fills,
            coerced_market_volumes,
            coerced_benchmarks,
            side_norm,
        )

        recommendations = self._generate_recommendations(
            latency_report,
            slippage_report,
            liquidity_report,
            benchmark_report,
            broker_comparison,
        )

        return TCAReport(
            executed_quantity=executed_quantity,
            latency=latency_report,
            slippage=slippage_report,
            liquidity=liquidity_report,
            benchmarks=benchmark_report,
            cost_breakdown=cost_breakdown,
            recommendations=tuple(recommendations),
            broker_comparison=broker_comparison,
            periodic=periodic,
        )

    @staticmethod
    def _compute_market_vwap(benchmarks: Sequence[BenchmarkPriceSample]) -> float:
        total_value = 0.0
        total_volume = 0.0
        for sample in benchmarks:
            volume = sample.vwap_window_volume
            if volume is None:
                weight = 1.0
            elif volume > 0.0:
                weight = volume
            else:
                # Explicit zero-volume benchmarks should not influence the VWAP.
                continue
            total_value += sample.price * weight
            total_volume += weight
        if total_volume == 0.0:
            return 0.0
        return total_value / total_volume

    @staticmethod
    def _compute_participation_rate(
        market_volumes: Sequence[MarketVolumeSample], executed_quantity: float
    ) -> float:
        total_market_volume = sum(sample.volume for sample in market_volumes)
        if total_market_volume <= 0.0 or executed_quantity <= 0.0:
            return 0.0
        return min(1.0, executed_quantity / total_market_volume)

    def _build_latency_report(self, orders: Sequence[OrderLifecycle]) -> LatencyReport:
        submit_to_ack = [value for order in orders if (value := order.submit_to_ack()) is not None]
        ack_to_fill = [value for order in orders if (value := order.ack_to_complete()) is not None]
        submit_to_complete = [value for order in orders if (value := order.submit_to_complete()) is not None]
        return LatencyReport(
            submit_to_ack=_compute_distribution(submit_to_ack),
            ack_to_fill=_compute_distribution(ack_to_fill),
            submit_to_complete=_compute_distribution(submit_to_complete),
        )

    def _build_liquidity_report(
        self,
        liquidity_samples: Sequence[LiquiditySample],
        fills: Sequence[FillDetail],
        executed_quantity: float,
    ) -> LiquidityReport:
        if not liquidity_samples:
            return LiquidityReport(
                average_displayed_volume=0.0,
                coverage_ratio=0.0,
                book_pressure=0.0,
                median_spread_bps=0.0,
            )

        volumes: list[float] = [sample.displayed_volume for sample in liquidity_samples]
        spreads: list[float] = [sample.spread_bps for sample in liquidity_samples if sample.spread_bps is not None]

        liquidity_by_bucket: MutableMapping[float, list[float]] = {}
        for sample in liquidity_samples:
            bucket = _bucket_key(sample.timestamp, self._bucket_seconds)
            liquidity_by_bucket.setdefault(bucket, []).append(sample.displayed_volume)

        fills_by_bucket: MutableMapping[float, list[FillDetail]] = {}
        for fill in fills:
            bucket = _bucket_key(fill.timestamp, self._bucket_seconds)
            fills_by_bucket.setdefault(bucket, []).append(fill)

        pressures: list[float] = []
        for bucket, bucket_fills in fills_by_bucket.items():
            bucket_liquidity = liquidity_by_bucket.get(bucket)
            if not bucket_liquidity:
                continue
            available = mean(bucket_liquidity)
            if available <= 0.0:
                continue
            bucket_executed = sum(fill.quantity for fill in bucket_fills)
            pressures.append(bucket_executed / available)

        total_displayed = sum(volumes)
        coverage_ratio = executed_quantity / total_displayed if total_displayed > 0.0 else 0.0
        book_pressure = max(pressures) if pressures else 0.0
        median_spread = _percentile(spreads, 0.5) if spreads else 0.0

        return LiquidityReport(
            average_displayed_volume=mean(volumes),
            coverage_ratio=coverage_ratio,
            book_pressure=book_pressure,
            median_spread_bps=median_spread,
        )

    @staticmethod
    def _compute_opportunity_cost(
        side: SideLiteral,
        arrival_price: float,
        target_quantity: float,
        executed_quantity: float,
        benchmarks: Sequence[BenchmarkPriceSample],
        fills: Sequence[FillDetail],
    ) -> float:
        residual = max(0.0, target_quantity - executed_quantity)
        if residual <= 0.0:
            return 0.0
        side_factor = 1.0 if side == "buy" else -1.0
        reference_price: float | None = None
        if benchmarks:
            reference_price = benchmarks[-1].price
        if reference_price is None and fills:
            reference_price = fills[-1].price
        if reference_price is None:
            reference_price = arrival_price
        return max(0.0, side_factor * (reference_price - arrival_price) * residual)

    @staticmethod
    def _build_broker_comparison(
        fills: Sequence[FillDetail],
        side: SideLiteral,
        market_vwap: float,
    ) -> tuple[BrokerVenueBreakdown, ...]:
        if not fills:
            return tuple()
        grouped: MutableMapping[tuple[str, str], dict[str, float]] = {}
        for fill in fills:
            key = (fill.broker, fill.venue)
            bucket = grouped.setdefault(key, {"quantity": 0.0, "notional": 0.0, "fees": 0.0, "count": 0.0})
            bucket["quantity"] += fill.quantity
            bucket["notional"] += fill.quantity * fill.price
            bucket["fees"] += fill.fees
            bucket["count"] += 1.0

        side_factor = 1.0 if side == "buy" else -1.0
        breakdowns: list[BrokerVenueBreakdown] = []
        for (broker, venue), stats in grouped.items():
            quantity = stats["quantity"]
            average_price = stats["notional"] / quantity if quantity > 0.0 else 0.0
            per_share_cost = side_factor * (average_price - market_vwap)
            breakdowns.append(
                BrokerVenueBreakdown(
                    broker=broker,
                    venue=venue,
                    quantity=quantity,
                    average_price=average_price,
                    fees=stats["fees"],
                    fill_count=int(stats["count"]),
                    cost_per_share=per_share_cost,
                )
            )

        breakdowns.sort(key=lambda entry: (entry.cost_per_share, -entry.quantity))
        return tuple(breakdowns)

    def _build_periodic_records(
        self,
        fills: Sequence[FillDetail],
        market_volumes: Sequence[MarketVolumeSample],
        benchmarks: Sequence[BenchmarkPriceSample],
        side: SideLiteral,
    ) -> tuple[PeriodicTCARecord, ...]:
        if not fills:
            return tuple()

        fills_by_bucket: MutableMapping[float, list[FillDetail]] = {}
        for fill in fills:
            bucket = _bucket_key(fill.timestamp, self._bucket_seconds)
            fills_by_bucket.setdefault(bucket, []).append(fill)

        volume_by_bucket: MutableMapping[float, float] = {}
        for sample in market_volumes:
            bucket = _bucket_key(sample.timestamp, self._bucket_seconds)
            volume_by_bucket[bucket] = volume_by_bucket.get(bucket, 0.0) + sample.volume

        benchmark_by_bucket: MutableMapping[float, list[BenchmarkPriceSample]] = {}
        for sample in benchmarks:
            bucket = _bucket_key(sample.timestamp, self._bucket_seconds)
            benchmark_by_bucket.setdefault(bucket, []).append(sample)

        side_factor = 1.0 if side == "buy" else -1.0
        periodic_records: list[PeriodicTCARecord] = []
        for bucket_start in sorted(fills_by_bucket):
            bucket_fills = fills_by_bucket[bucket_start]
            executed_quantity = sum(fill.quantity for fill in bucket_fills)
            notional = sum(fill.quantity * fill.price for fill in bucket_fills)
            vwap_price = notional / executed_quantity if executed_quantity > 0.0 else 0.0
            market_volume = volume_by_bucket.get(bucket_start, 0.0)
            participation = executed_quantity / market_volume if market_volume > 0.0 else 0.0

            benchmark_samples = benchmark_by_bucket.get(bucket_start)
            if benchmark_samples:
                benchmark_vwap = self._compute_market_vwap(tuple(benchmark_samples))
            else:
                benchmark_vwap = vwap_price
            slippage = side_factor * (vwap_price - benchmark_vwap)

            periodic_records.append(
                PeriodicTCARecord(
                    start_timestamp=bucket_start,
                    end_timestamp=bucket_start + self._bucket_seconds,
                    executed_quantity=executed_quantity,
                    vwap=vwap_price,
                    participation_rate=min(1.0, participation),
                    slippage=slippage,
                )
            )

        return tuple(periodic_records)

    @staticmethod
    def _generate_recommendations(
        latency: LatencyReport,
        slippage: SlippageReport,
        liquidity: LiquidityReport,
        benchmarks: BenchmarkReport,
        broker_comparison: Sequence[BrokerVenueBreakdown],
    ) -> list[str]:
        recommendations: list[str] = []

        if latency.submit_to_ack.p95 > 1.0:
            recommendations.append(
                "Investigate routing latency; consider diversifying smart order routing paths or brokers."
            )

        if liquidity.book_pressure > 1.2:
            recommendations.append(
                "Execution slices are exhausting displayed liquidity; reduce participation or widen slicing intervals."
            )

        if slippage.per_share_shortfall > 0.5:
            recommendations.append(
                "Implementation shortfall is elevated; tighten limit offsets or review algo aggressiveness."
            )

        if benchmarks.participation_rate > 0.25:
            recommendations.append(
                "Participation rate is high; evaluate POV limits to reduce signalling risk."
            )

        if broker_comparison:
            worst = max(broker_comparison, key=lambda entry: entry.cost_per_share)
            best = min(broker_comparison, key=lambda entry: entry.cost_per_share)
            if worst.cost_per_share - best.cost_per_share > 0.1:
                recommendations.append(
                    f"Broker {worst.broker} on {worst.venue} underperformed peers; shift flow toward {best.broker}/{best.venue}."
                )

        seen = set()
        unique_recommendations: list[str] = []
        for rec in recommendations:
            if rec not in seen:
                unique_recommendations.append(rec)
                seen.add(rec)
        return unique_recommendations

