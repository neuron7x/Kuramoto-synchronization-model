"""Transaction cost modelling primitives used by the backtest engine."""

from __future__ import annotations

import importlib
import inspect
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping

import yaml  # type: ignore[import-untyped]


class TransactionCostModel:
    """Base interface for per-trade cost components.

    The methods return *per-unit* adjustments expressed in price terms so that
    they can be composed by the execution layer. Implementations should always
    return non-negative values and gracefully handle zero or NaN inputs.
    """

    def get_commission(self, volume: float, price: float) -> float:
        """Return the monetary commission for executing ``volume`` at ``price``."""

        del volume, price
        return 0.0

    def get_spread(self, price: float, side: str | None = None) -> float:
        """Return the half-spread to apply on top of the mid price.

        The value represents the directional adjustment added for buys and
        subtracted for sells. ``side`` is included for extensibility and can be
        used by asymmetric models.
        """

        del price, side
        return 0.0

    def get_slippage(
        self, volume: float, price: float, side: str | None = None
    ) -> float:
        """Return the slippage adjustment in price terms for the given trade."""

        del volume, price, side
        return 0.0

    def get_financing(self, position: float, price: float) -> float:
        """Return the carry cost associated with holding ``position`` at ``price``."""

        del position, price
        return 0.0


class ZeroTransactionCost(TransactionCostModel):
    """A convenience model that yields zero costs for all components."""

    __slots__ = ()


class PerUnitCommission(TransactionCostModel):
    """Fixed fee charged per unit traded."""

    __slots__ = ("fee_per_unit",)

    def __init__(self, fee_per_unit: float) -> None:
        self.fee_per_unit = float(max(fee_per_unit, 0.0))

    def get_commission(
        self, volume: float, price: float
    ) -> float:  # noqa: D401 - see base docstring
        del price
        volume = float(abs(volume))
        if not math.isfinite(volume) or volume <= 0.0:
            return 0.0
        return volume * self.fee_per_unit


class FixedBpsCommission(TransactionCostModel):
    """Commission expressed in basis points of the notional value."""

    __slots__ = ("bps",)

    def __init__(self, bps: float) -> None:
        self.bps = float(max(bps, 0.0))

    def get_commission(self, volume: float, price: float) -> float:  # noqa: D401
        volume = float(abs(volume))
        notional = volume * float(max(price, 0.0))
        if not math.isfinite(notional) or notional <= 0.0:
            return 0.0
        return notional * self.bps * 1e-4


class PercentVolumeCommission(TransactionCostModel):
    """Commission expressed as a percentage of notional volume."""

    __slots__ = ("percent",)

    def __init__(self, percent: float) -> None:
        self.percent = float(max(percent, 0.0))

    def get_commission(self, volume: float, price: float) -> float:  # noqa: D401
        volume = float(abs(volume))
        notional = volume * float(max(price, 0.0))
        if not math.isfinite(notional) or notional <= 0.0:
            return 0.0
        return notional * self.percent * 0.01


class FixedSpread(TransactionCostModel):
    """A constant half-spread applied per trade."""

    __slots__ = ("spread",)

    def __init__(self, spread: float) -> None:
        self.spread = float(max(spread, 0.0))

    def get_spread(self, price: float, side: str | None = None) -> float:  # noqa: D401
        del price, side
        return self.spread


class BpsSpread(TransactionCostModel):
    """Spread defined in basis points relative to the reference price."""

    __slots__ = ("bps",)

    def __init__(self, bps: float) -> None:
        self.bps = float(max(bps, 0.0))

    def get_spread(self, price: float, side: str | None = None) -> float:  # noqa: D401
        price = float(max(price, 0.0))
        if not math.isfinite(price) or price <= 0.0:
            return 0.0
        return price * self.bps * 1e-4


class FixedSlippage(TransactionCostModel):
    """Fixed price adjustment applied as slippage."""

    __slots__ = ("slippage",)

    def __init__(self, slippage: float) -> None:
        self.slippage = float(max(slippage, 0.0))

    def get_slippage(
        self, volume: float, price: float, side: str | None = None
    ) -> float:  # noqa: D401
        del volume, price, side
        return self.slippage


class VolumeProportionalSlippage(TransactionCostModel):
    """Slippage proportional to traded volume."""

    __slots__ = ("coefficient",)

    def __init__(self, coefficient: float) -> None:
        self.coefficient = float(max(coefficient, 0.0))

    def get_slippage(
        self, volume: float, price: float, side: str | None = None
    ) -> float:  # noqa: D401
        del price, side
        volume = float(abs(volume))
        if not math.isfinite(volume) or volume <= 0.0:
            return 0.0
        return volume * self.coefficient


class SquareRootSlippage(TransactionCostModel):
    """Square-root market impact model."""

    __slots__ = ("a", "b")

    def __init__(self, a: float = 0.0, b: float = 0.0) -> None:
        self.a = float(max(a, 0.0))
        self.b = float(max(b, 0.0))

    def get_slippage(
        self, volume: float, price: float, side: str | None = None
    ) -> float:  # noqa: D401
        volume = float(abs(volume))
        price = float(max(price, 0.0))
        if not math.isfinite(volume) or volume <= 0.0 or not math.isfinite(price):
            return 0.0
        return price * (self.a + self.b * math.sqrt(volume))


class BorrowFinancing(TransactionCostModel):
    """Borrow/funding cost model with optional non-linear scaling."""

    __slots__ = ("long_rate", "short_rate", "periods_per_year", "exponent")

    def __init__(
        self,
        long_rate_bps: float = 0.0,
        short_rate_bps: float = 0.0,
        *,
        periods_per_year: int = 252,
        exponent: float = 1.0,
    ) -> None:
        self.long_rate = float(long_rate_bps) * 1e-4
        self.short_rate = float(short_rate_bps) * 1e-4
        self.periods_per_year = max(int(periods_per_year), 1)
        self.exponent = float(exponent) if exponent > 0 else 1.0

    def get_financing(self, position: float, price: float) -> float:  # noqa: D401
        position = float(position)
        price = float(max(price, 0.0))
        volume = abs(position)
        if not math.isfinite(price) or not math.isfinite(volume) or volume <= 0.0:
            return 0.0
        notional = volume * price
        scale = volume ** (self.exponent - 1.0) if self.exponent != 1.0 else 1.0
        rate = self.long_rate if position >= 0 else self.short_rate
        annual_cost = rate * notional * scale
        return annual_cost / self.periods_per_year


@dataclass(slots=True)
class CompositeTransactionCostModel(TransactionCostModel):
    """Aggregate model composed of optional commission, spread and slippage."""

    commission_model: TransactionCostModel | None = None
    spread_model: TransactionCostModel | None = None
    slippage_model: TransactionCostModel | None = None
    financing_model: TransactionCostModel | None = None

    def get_commission(self, volume: float, price: float) -> float:  # noqa: D401
        model = self.commission_model
        return model.get_commission(volume, price) if model else 0.0

    def get_spread(self, price: float, side: str | None = None) -> float:  # noqa: D401
        model = self.spread_model
        return model.get_spread(price, side) if model else 0.0

    def get_slippage(
        self, volume: float, price: float, side: str | None = None
    ) -> float:  # noqa: D401
        model = self.slippage_model
        return model.get_slippage(volume, price, side) if model else 0.0

    def get_financing(self, position: float, price: float) -> float:  # noqa: D401
        model = self.financing_model
        return model.get_financing(position, price) if model else 0.0


def _import_from_string(path: str) -> Callable[..., Any]:
    module_name, _, attr = path.rpartition(".")
    if not module_name:
        raise ValueError(f"Invalid import path '{path}'")
    module = importlib.import_module(module_name)
    try:
        return getattr(module, attr)
    except AttributeError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"'{attr}' is not defined in module '{module_name}'") from exc


def _instantiate(
    spec: Any, params: Mapping[str, Any] | None = None
) -> TransactionCostModel:
    if isinstance(spec, TransactionCostModel):
        return spec

    if inspect.isclass(spec) and issubclass(spec, TransactionCostModel):
        return spec(**(params or {}))

    if callable(spec):
        return spec(**(params or {}))

    if isinstance(spec, str):
        target = _import_from_string(spec)
        if inspect.isclass(target) and issubclass(target, TransactionCostModel):
            return target(**(params or {}))
        if callable(target):
            return target(**(params or {}))
        raise TypeError(f"Resolved object '{spec}' is not callable")

    raise TypeError(f"Unsupported model specification: {spec!r}")


def _build_commission(entry: Mapping[str, Any]) -> TransactionCostModel | None:
    if "commission_model" in entry:
        model_spec = entry["commission_model"]
        params = entry.get("commission_params", {})
        if isinstance(model_spec, str):
            alias = model_spec.lower()
            if alias in {"fixed_bps", "bps"}:
                value = params.get("bps", params.get("value"))
                if value is None:
                    raise ValueError(
                        "'commission_params.bps' is required for fixed_bps model"
                    )
                return FixedBpsCommission(value)
            if alias in {"percent", "percentage", "percent_volume"}:
                value = params.get("percent", params.get("value"))
                if value is None:
                    raise ValueError(
                        "'commission_params.percent' is required for percent model"
                    )
                return PercentVolumeCommission(value)
            if alias in {"per_unit", "fixed", "per_contract"}:
                value = params.get("per_unit", params.get("value"))
                if value is None:
                    raise ValueError(
                        "'commission_params.per_unit' is required for per_unit model"
                    )
                return PerUnitCommission(value)
        return _instantiate(model_spec, params)

    if "commission_bps" in entry:
        return FixedBpsCommission(entry["commission_bps"])

    if "commission_percent" in entry:
        return PercentVolumeCommission(entry["commission_percent"])

    if "commission_per_unit" in entry:
        return PerUnitCommission(entry["commission_per_unit"])

    if "commission_per_contract" in entry:
        return PerUnitCommission(entry["commission_per_contract"])

    return None


def _build_spread(entry: Mapping[str, Any]) -> TransactionCostModel | None:
    if "spread_model" in entry:
        model_spec = entry["spread_model"]
        params = entry.get("spread_params", {})
        if isinstance(model_spec, str):
            alias = model_spec.lower()
            if alias in {"fixed", "absolute"}:
                value = params.get("value")
                if value is None:
                    raise ValueError(
                        "'spread_params.value' is required for fixed spread model"
                    )
                return FixedSpread(value)
            if alias in {"bps", "percent"}:
                value = params.get("bps", params.get("value"))
                if value is None:
                    raise ValueError(
                        "'spread_params.bps' is required for bps spread model"
                    )
                return BpsSpread(value)
        return _instantiate(model_spec, params)

    if "spread" in entry:
        return FixedSpread(entry["spread"])

    if "spread_bps" in entry:
        return BpsSpread(entry["spread_bps"])

    return None


def _build_slippage(entry: Mapping[str, Any]) -> TransactionCostModel | None:
    if "slippage_model" in entry:
        model_spec = entry["slippage_model"]
        params = entry.get("slippage_params", {})
        if isinstance(model_spec, str):
            alias = model_spec.lower()
            if alias == "fixed":
                value = params.get("value")
                if value is None:
                    raise ValueError(
                        "'slippage_params.value' is required for fixed model"
                    )
                return FixedSlippage(value)
            if alias in {"square_root", "sqrt"}:
                return SquareRootSlippage(**params)
            if alias in {"volume", "proportional"}:
                coefficient = params.get("coefficient", params.get("value"))
                if coefficient is None:
                    raise ValueError("'coefficient' is required for volume slippage")
                return VolumeProportionalSlippage(coefficient)
        return _instantiate(model_spec, params)

    if "slippage_value" in entry:
        return FixedSlippage(entry["slippage_value"])

    if "slippage_coefficient" in entry:
        return VolumeProportionalSlippage(entry["slippage_coefficient"])

    if "slippage_square_root" in entry:
        params = entry["slippage_square_root"]
        if not isinstance(params, Mapping):
            raise TypeError("'slippage_square_root' must be a mapping")
        return SquareRootSlippage(**params)

    return None


def _build_financing(entry: Mapping[str, Any]) -> TransactionCostModel | None:
    if "financing_model" in entry:
        model_spec = entry["financing_model"]
        params = entry.get("financing_params", {})
        if isinstance(model_spec, str):
            alias = model_spec.lower()
            if alias in {"borrow", "borrowing", "funding"}:
                long_rate = params.get(
                    "long_rate_bps", params.get("long_bps", params.get("bps", 0.0))
                )
                short_rate = params.get(
                    "short_rate_bps",
                    params.get("short_bps", params.get("borrow_bps", long_rate)),
                )
                exponent = params.get("exponent")
                periods = params.get("periods_per_year")
                kwargs: dict[str, Any] = {
                    "long_rate_bps": long_rate or 0.0,
                    "short_rate_bps": (
                        short_rate if short_rate is not None else long_rate or 0.0
                    ),
                }
                if exponent is not None:
                    kwargs["exponent"] = exponent
                if periods is not None:
                    kwargs["periods_per_year"] = periods
                return BorrowFinancing(**kwargs)
        return _instantiate(model_spec, params)

    if "borrow_bps" in entry:
        value = entry["borrow_bps"]
        short_value = entry.get("borrow_bps_short", value)
        return BorrowFinancing(long_rate_bps=value, short_rate_bps=short_value)

    if "funding_long_bps" in entry or "funding_short_bps" in entry:
        long_rate = entry.get("funding_long_bps", 0.0)
        short_rate = entry.get("funding_short_bps", long_rate)
        exponent = entry.get("funding_exponent")
        kwargs: dict[str, Any] = {
            "long_rate_bps": long_rate,
            "short_rate_bps": short_rate,
        }
        if exponent is not None:
            kwargs["exponent"] = exponent
        periods = entry.get("funding_periods_per_year")
        if periods is not None:
            kwargs["periods_per_year"] = periods
        return BorrowFinancing(**kwargs)

    return None


def load_market_costs(
    source: str | Path | Mapping[str, Any],
    market: str,
) -> CompositeTransactionCostModel:
    """Load a :class:`CompositeTransactionCostModel` for ``market``.

    Parameters
    ----------
    source:
        Either a mapping already in memory or a path to a YAML/JSON file.
    market:
        The market identifier to load.
    """

    if isinstance(source, (str, Path)):
        data: MutableMapping[str, Any]
        with Path(source).expanduser().open("r", encoding="utf8") as handle:
            data = yaml.safe_load(handle) or {}
    elif isinstance(source, Mapping):
        data = dict(source)
    else:  # pragma: no cover - defensive guard
        raise TypeError("source must be a mapping or a path-like object")

    try:
        entry = data[market]
    except KeyError as exc:
        raise KeyError(f"Market '{market}' is not defined in configuration") from exc

    if not isinstance(entry, Mapping):
        raise TypeError(f"Configuration for market '{market}' must be a mapping")

    commission = _build_commission(entry)
    spread = _build_spread(entry)
    slippage = _build_slippage(entry)
    financing = _build_financing(entry)

    return CompositeTransactionCostModel(
        commission_model=commission,
        spread_model=spread,
        slippage_model=slippage,
        financing_model=financing,
    )


__all__ = [
    "TransactionCostModel",
    "ZeroTransactionCost",
    "PerUnitCommission",
    "FixedBpsCommission",
    "PercentVolumeCommission",
    "FixedSpread",
    "BpsSpread",
    "FixedSlippage",
    "VolumeProportionalSlippage",
    "SquareRootSlippage",
    "BorrowFinancing",
    "CompositeTransactionCostModel",
    "load_market_costs",
]
