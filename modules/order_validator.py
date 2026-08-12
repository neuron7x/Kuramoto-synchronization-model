# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Order Validator Module

Модуль для валідації торгових ордерів перед виконанням.

Features:
- Перевірка ризиків
- Валідація лімітів
- Перевірка ринкових умов
- Комплаєнс правила
"""

from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


class OrderType(str, Enum):
    """Тип ордера"""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderSide(str, Enum):
    """Сторона ордера"""

    BUY = "buy"
    SELL = "sell"


class OrderTimeInForce(str, Enum):
    """Час дії ордера"""

    GTC = "good_till_cancelled"
    DAY = "day"
    IOC = "immediate_or_cancel"
    FOK = "fill_or_kill"


class ValidationResult(str, Enum):
    """Результат валідації"""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"


@dataclass
class Order:
    """Торговий ордер"""

    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: OrderTimeInForce = OrderTimeInForce.DAY
    client_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ValidationError:
    """Помилка валідації"""

    code: str
    message: str
    field: Optional[str] = None
    severity: str = "error"


@dataclass
class ValidationWarning:
    """Попередження валідації"""

    code: str
    message: str
    suggestion: Optional[str] = None


@dataclass
class OrderValidationResult:
    """Результат валідації ордера"""

    is_valid: bool
    order: Order
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationWarning] = field(default_factory=list)
    risk_score: float = 0.0
    validated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskLimits:
    """Ліміти ризиків"""

    max_position_size: float = 100000.0
    max_order_value: float = 50000.0
    max_daily_trades: int = 100
    max_daily_volume: float = 500000.0
    max_concentration: float = 0.2  # 20% портфеля в одному активі
    min_order_size: float = 10.0
    max_leverage: float = 2.0


@dataclass
class TradingHours:
    """Торгові години"""

    start: time = field(default_factory=lambda: time(9, 30))
    end: time = field(default_factory=lambda: time(16, 0))
    timezone: str = "America/New_York"
    trading_days: Set[int] = field(default_factory=lambda: {0, 1, 2, 3, 4})  # Mon-Fri


@dataclass
class PositionInfo:
    """Інформація про позицію"""

    symbol: str
    quantity: float
    average_price: float
    market_value: float
    unrealized_pnl: float


class OrderValidator:
    """
    Валідатор торгових ордерів

    Перевіряє ордери на відповідність правилам ризику,
    лімітам та ринковим умовам.
    """

    def __init__(
        self,
        risk_limits: Optional[RiskLimits] = None,
        trading_hours: Optional[TradingHours] = None,
        portfolio_value: float = 100000.0,
    ):
        """
        Ініціалізація валідатора

        Args:
            risk_limits: Ліміти ризиків
            trading_hours: Торгові години
            portfolio_value: Вартість портфеля
        """
        self.risk_limits = risk_limits or RiskLimits()
        self.trading_hours = trading_hours or TradingHours()
        self.portfolio_value = portfolio_value

        # Позиції
        self._positions: Dict[str, PositionInfo] = {}

        # Денна статистика
        self._daily_trades: int = 0
        self._daily_volume: float = 0.0
        self._last_reset_date: datetime = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # Кастомні валідатори
        self._custom_validators: List[Callable[[Order], List[ValidationError]]] = []

        # Заборонені символи
        self._blocked_symbols: Set[str] = set()

        # Дозволені символи (якщо пусто - всі дозволені)
        self._allowed_symbols: Set[str] = set()

    def validate(
        self,
        order: Order,
        current_price: Optional[float] = None,
    ) -> OrderValidationResult:
        """
        Валідація ордера

        Args:
            order: Ордер для валідації
            current_price: Поточна ціна (опціонально)

        Returns:
            Результат валідації
        """
        errors: List[ValidationError] = []
        warnings: List[ValidationWarning] = []
        risk_score = 0.0

        # Скидання денної статистики якщо потрібно
        self._check_daily_reset()

        # Базова валідація
        errors.extend(self._validate_basic(order))

        # Валідація символу
        errors.extend(self._validate_symbol(order))

        # Валідація кількості
        quantity_errors, quantity_warnings = self._validate_quantity(order, current_price)
        errors.extend(quantity_errors)
        warnings.extend(quantity_warnings)

        # Валідація ціни
        if order.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT]:
            errors.extend(self._validate_price(order, current_price))

        # Валідація ризиків
        risk_errors, risk_warnings, risk_score = self._validate_risk(order, current_price)
        errors.extend(risk_errors)
        warnings.extend(risk_warnings)

        # Валідація торгових годин
        trading_errors = self._validate_trading_hours(order)
        errors.extend(trading_errors)

        # Валідація позиції
        position_errors, position_warnings = self._validate_position(order, current_price)
        errors.extend(position_errors)
        warnings.extend(position_warnings)

        # Кастомні валідатори
        for validator in self._custom_validators:
            try:
                custom_errors = validator(order)
                errors.extend(custom_errors)
            except Exception as e:
                warnings.append(
                    ValidationWarning(
                        code="CUSTOM_VALIDATOR_ERROR",
                        message=f"Custom validator failed: {str(e)}",
                    )
                )

        is_valid = len(errors) == 0

        return OrderValidationResult(
            is_valid=is_valid,
            order=order,
            errors=errors,
            warnings=warnings,
            risk_score=risk_score,
            metadata={
                "current_price": current_price,
                "portfolio_value": self.portfolio_value,
                "daily_trades": self._daily_trades,
                "daily_volume": self._daily_volume,
            },
        )

    def _validate_basic(self, order: Order) -> List[ValidationError]:
        """Базова валідація"""
        errors = []

        # Перевірка обов'язкових полів
        if not order.symbol:
            errors.append(
                ValidationError(
                    code="MISSING_SYMBOL",
                    message="Order symbol is required",
                    field="symbol",
                )
            )

        if not order.order_id:
            errors.append(
                ValidationError(
                    code="MISSING_ORDER_ID",
                    message="Order ID is required",
                    field="order_id",
                )
            )

        if order.quantity <= 0:
            errors.append(
                ValidationError(
                    code="INVALID_QUANTITY",
                    message="Quantity must be positive",
                    field="quantity",
                )
            )

        # Перевірка ціни для лімітних ордерів
        if order.order_type == OrderType.LIMIT and (order.price is None or order.price <= 0):
            errors.append(
                ValidationError(
                    code="MISSING_LIMIT_PRICE",
                    message="Limit price is required for limit orders",
                    field="price",
                )
            )

        # Перевірка stop price для стоп-ордерів
        if order.order_type in [OrderType.STOP, OrderType.STOP_LIMIT] and (
            order.stop_price is None or order.stop_price <= 0
        ):
            errors.append(
                ValidationError(
                    code="MISSING_STOP_PRICE",
                    message="Stop price is required for stop orders",
                    field="stop_price",
                )
            )

        return errors

    def _validate_symbol(self, order: Order) -> List[ValidationError]:
        """Валідація символу"""
        errors = []
        symbol = order.symbol.upper()

        # Перевірка заблокованих символів
        if symbol in self._blocked_symbols:
            errors.append(
                ValidationError(
                    code="BLOCKED_SYMBOL",
                    message=f"Trading in {symbol} is currently blocked",
                    field="symbol",
                )
            )

        # Перевірка дозволених символів
        if self._allowed_symbols and symbol not in self._allowed_symbols:
            errors.append(
                ValidationError(
                    code="SYMBOL_NOT_ALLOWED",
                    message=f"Symbol {symbol} is not in the allowed list",
                    field="symbol",
                )
            )

        return errors

    def _validate_quantity(
        self, order: Order, current_price: Optional[float]
    ) -> Tuple[List[ValidationError], List[ValidationWarning]]:
        """Валідація кількості"""
        errors = []
        warnings = []
        limits = self.risk_limits

        # Мінімальний розмір ордера
        if order.quantity < limits.min_order_size:
            errors.append(
                ValidationError(
                    code="ORDER_TOO_SMALL",
                    message=f"Order size {order.quantity} is below minimum {limits.min_order_size}",
                    field="quantity",
                )
            )

        # Максимальна вартість ордера
        if current_price:
            order_value = order.quantity * current_price

            if order_value > limits.max_order_value:
                errors.append(
                    ValidationError(
                        code="ORDER_VALUE_EXCEEDED",
                        message=f"Order value ${order_value:,.2f} exceeds maximum ${limits.max_order_value:,.2f}",
                        field="quantity",
                    )
                )

            # Попередження для великих ордерів
            if order_value > limits.max_order_value * 0.8:
                warnings.append(
                    ValidationWarning(
                        code="LARGE_ORDER",
                        message=f"Order value ${order_value:,.2f} is close to the limit",
                        suggestion="Consider splitting the order",
                    )
                )

        return errors, warnings

    def _validate_price(
        self, order: Order, current_price: Optional[float]
    ) -> List[ValidationError]:
        """Валідація ціни"""
        errors = []

        if current_price and order.price:
            # Перевірка розумності ціни
            price_deviation = abs(order.price - current_price) / current_price

            if price_deviation > 0.1:  # 10% відхилення
                errors.append(
                    ValidationError(
                        code="PRICE_DEVIATION_HIGH",
                        message=f"Limit price deviates {price_deviation:.1%} from current price",
                        field="price",
                        severity="warning",
                    )
                )

            # Перевірка логіки ціни
            if order.side == OrderSide.BUY and order.price > current_price * 1.5:
                errors.append(
                    ValidationError(
                        code="BUY_PRICE_TOO_HIGH",
                        message="Buy limit price is significantly above current price",
                        field="price",
                    )
                )

            if order.side == OrderSide.SELL and order.price < current_price * 0.5:
                errors.append(
                    ValidationError(
                        code="SELL_PRICE_TOO_LOW",
                        message="Sell limit price is significantly below current price",
                        field="price",
                    )
                )

        return errors

    def _validate_risk(
        self, order: Order, current_price: Optional[float]
    ) -> Tuple[List[ValidationError], List[ValidationWarning], float]:
        """Валідація ризиків"""
        errors = []
        warnings = []
        risk_score = 0.0
        limits = self.risk_limits

        # Денні ліміти
        if self._daily_trades >= limits.max_daily_trades:
            errors.append(
                ValidationError(
                    code="DAILY_TRADE_LIMIT",
                    message=f"Daily trade limit ({limits.max_daily_trades}) reached",
                )
            )

        if current_price:
            order_value = order.quantity * current_price
            projected_volume = self._daily_volume + order_value

            if projected_volume > limits.max_daily_volume:
                errors.append(
                    ValidationError(
                        code="DAILY_VOLUME_LIMIT",
                        message=f"Daily volume limit (${limits.max_daily_volume:,.0f}) would be exceeded",
                    )
                )

            # Концентрація портфеля
            concentration = order_value / self.portfolio_value
            if concentration > limits.max_concentration:
                errors.append(
                    ValidationError(
                        code="CONCENTRATION_LIMIT",
                        message=(
                            f"Order would result in {concentration:.1%} concentration "
                            f"(max: {limits.max_concentration:.1%})"
                        ),
                    )
                )

            # Розрахунок risk score
            volume_ratio = order_value / limits.max_order_value
            concentration_ratio = concentration / limits.max_concentration
            trade_ratio = self._daily_trades / limits.max_daily_trades

            risk_score = (volume_ratio + concentration_ratio + trade_ratio) / 3
            risk_score = min(1.0, max(0.0, risk_score))

            if risk_score > 0.7:
                warnings.append(
                    ValidationWarning(
                        code="HIGH_RISK_SCORE",
                        message=f"Order has elevated risk score: {risk_score:.2f}",
                        suggestion="Review order parameters",
                    )
                )

        return errors, warnings, risk_score

    def _validate_trading_hours(self, order: Order) -> List[ValidationError]:
        """Валідація торгових годин"""
        errors = []
        now = datetime.now()
        current_time = now.time()
        current_day = now.weekday()

        hours = self.trading_hours

        # Перевірка дня тижня
        if current_day not in hours.trading_days:
            # Для market ордерів - помилка, для інших - попередження
            if order.order_type == OrderType.MARKET:
                errors.append(
                    ValidationError(
                        code="MARKET_CLOSED_DAY",
                        message="Market is closed today",
                    )
                )

        # Перевірка часу
        if current_time < hours.start or current_time > hours.end:
            if order.order_type == OrderType.MARKET:
                errors.append(
                    ValidationError(
                        code="MARKET_CLOSED_TIME",
                        message=f"Market hours: {hours.start} - {hours.end}",
                    )
                )

        return errors

    def _validate_position(
        self, order: Order, current_price: Optional[float]
    ) -> Tuple[List[ValidationError], List[ValidationWarning]]:
        """Валідація позиції"""
        errors = []
        warnings = []
        limits = self.risk_limits

        symbol = order.symbol.upper()
        position = self._positions.get(symbol)

        if position and current_price:
            # Перевірка максимальної позиції
            if order.side == OrderSide.BUY:
                projected_quantity = position.quantity + order.quantity
            else:
                projected_quantity = position.quantity - order.quantity

            projected_value = abs(projected_quantity) * current_price

            if projected_value > limits.max_position_size:
                errors.append(
                    ValidationError(
                        code="POSITION_SIZE_LIMIT",
                        message=(
                            f"Projected position ${projected_value:,.2f} exceeds "
                            f"limit ${limits.max_position_size:,.2f}"
                        ),
                    )
                )

            # Попередження про закриття позиції
            if order.side == OrderSide.SELL and order.quantity >= position.quantity:
                warnings.append(
                    ValidationWarning(
                        code="CLOSING_POSITION",
                        message=f"This order will close the entire position in {symbol}",
                    )
                )

        return errors, warnings

    def _check_daily_reset(self) -> None:
        """Перевірка та скидання денної статистики"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        if today > self._last_reset_date:
            self._daily_trades = 0
            self._daily_volume = 0.0
            self._last_reset_date = today

    def update_position(self, position: PositionInfo) -> None:
        """
        Оновлення позиції

        Args:
            position: Інформація про позицію
        """
        self._positions[position.symbol.upper()] = position

    def record_execution(self, order: Order, execution_price: float) -> None:
        """
        Запис виконання ордера

        Args:
            order: Виконаний ордер
            execution_price: Ціна виконання
        """
        self._daily_trades += 1
        self._daily_volume += order.quantity * execution_price

    def add_custom_validator(self, validator: Callable[[Order], List[ValidationError]]) -> None:
        """
        Додавання кастомного валідатора

        Args:
            validator: Функція валідації
        """
        self._custom_validators.append(validator)

    def block_symbol(self, symbol: str) -> None:
        """Блокування символу"""
        self._blocked_symbols.add(symbol.upper())

    def unblock_symbol(self, symbol: str) -> None:
        """Розблокування символу"""
        self._blocked_symbols.discard(symbol.upper())

    def set_allowed_symbols(self, symbols: Set[str]) -> None:
        """Встановлення дозволених символів"""
        self._allowed_symbols = {s.upper() for s in symbols}

    def update_portfolio_value(self, value: float) -> None:
        """Оновлення вартості портфеля"""
        self.portfolio_value = max(0.0, value)

    def update_risk_limits(self, limits: RiskLimits) -> None:
        """Оновлення лімітів ризику"""
        self.risk_limits = limits

    def get_summary(self) -> Dict:
        """
        Отримання саммарі

        Returns:
            Словник зі статистикою
        """
        return {
            "portfolio_value": f"${self.portfolio_value:,.2f}",
            "daily_trades": self._daily_trades,
            "daily_trades_limit": self.risk_limits.max_daily_trades,
            "daily_volume": f"${self._daily_volume:,.2f}",
            "daily_volume_limit": f"${self.risk_limits.max_daily_volume:,.2f}",
            "blocked_symbols": len(self._blocked_symbols),
            "allowed_symbols": len(self._allowed_symbols) if self._allowed_symbols else "all",
            "positions_tracked": len(self._positions),
            "custom_validators": len(self._custom_validators),
        }
