# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Alert Manager Module

Модуль для управління сповіщеннями та алертами в торговій системі.

Features:
- Різні рівні критичності алертів
- Багатоканальні сповіщення (email, webhook, slack)
- Правила та фільтри
- Агрегація та дедуплікація
- Історія алертів
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


class AlertSeverity(str, Enum):
    """Рівень критичності алерта"""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertCategory(str, Enum):
    """Категорія алерта"""

    SYSTEM = "system"
    TRADING = "trading"
    RISK = "risk"
    MARKET = "market"
    EXECUTION = "execution"
    DATA = "data"
    PERFORMANCE = "performance"
    SECURITY = "security"


class AlertStatus(str, Enum):
    """Статус алерта"""

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class NotificationChannel(str, Enum):
    """Канали сповіщення"""

    EMAIL = "email"
    WEBHOOK = "webhook"
    SLACK = "slack"
    TELEGRAM = "telegram"
    SMS = "sms"
    CONSOLE = "console"


@dataclass
class Alert:
    """Алерт"""

    alert_id: str
    title: str
    message: str
    severity: AlertSeverity
    category: AlertCategory
    source: str
    status: AlertStatus = AlertStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    tags: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    occurrence_count: int = 1


@dataclass
class AlertRule:
    """Правило для алертів"""

    rule_id: str
    name: str
    condition: Callable[[Dict[str, Any]], bool]
    title_template: str
    message_template: str
    severity: AlertSeverity
    category: AlertCategory
    enabled: bool = True
    cooldown_seconds: int = 300
    tags: Set[str] = field(default_factory=set)
    notification_channels: Set[NotificationChannel] = field(
        default_factory=lambda: {NotificationChannel.CONSOLE}
    )
    last_triggered: Optional[datetime] = None


@dataclass
class NotificationConfig:
    """Конфігурація каналу сповіщення"""

    channel: NotificationChannel
    enabled: bool = True
    min_severity: AlertSeverity = AlertSeverity.INFO
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AlertStats:
    """Статистика алертів"""

    total_alerts: int = 0
    active_alerts: int = 0
    acknowledged_alerts: int = 0
    resolved_alerts: int = 0
    by_severity: Dict[str, int] = field(default_factory=dict)
    by_category: Dict[str, int] = field(default_factory=dict)


class AlertManager:
    """
    Менеджер алертів

    Централізована система управління алертами,
    сповіщеннями та їх обробкою.
    """

    def __init__(
        self,
        deduplication_window_seconds: int = 300,
        max_history_size: int = 10000,
        enable_aggregation: bool = True,
    ):
        """
        Ініціалізація менеджера алертів

        Args:
            deduplication_window_seconds: Вікно дедуплікації в секундах
            max_history_size: Максимальний розмір історії
            enable_aggregation: Увімкнути агрегацію схожих алертів
        """
        self.deduplication_window_seconds = deduplication_window_seconds
        self.max_history_size = max_history_size
        self.enable_aggregation = enable_aggregation

        # Активні алерти
        self._active_alerts: Dict[str, Alert] = {}

        # Історія алертів
        self._alert_history: List[Alert] = []

        # Правила
        self._rules: Dict[str, AlertRule] = {}

        # Канали сповіщень
        self._notification_configs: Dict[NotificationChannel, NotificationConfig] = {}
        self._notification_handlers: Dict[NotificationChannel, Callable[[Alert], bool]] = {}

        # Підписники
        self._subscribers: List[Callable[[Alert], None]] = []

        # Лічильник алертів
        self._alert_counter = 0

        # Дедуплікація
        self._dedup_cache: Dict[str, datetime] = {}

        # Налаштування каналу console за замовчуванням
        self._setup_default_console_handler()

    def _setup_default_console_handler(self) -> None:
        """Налаштування обробника console за замовчуванням"""
        self._notification_configs[NotificationChannel.CONSOLE] = NotificationConfig(
            channel=NotificationChannel.CONSOLE, enabled=True
        )

        def console_handler(alert: Alert) -> bool:
            severity_emoji = {
                AlertSeverity.DEBUG: "🔍",
                AlertSeverity.INFO: "ℹ️",
                AlertSeverity.WARNING: "⚠️",
                AlertSeverity.ERROR: "❌",
                AlertSeverity.CRITICAL: "🚨",
            }
            emoji = severity_emoji.get(alert.severity, "📢")
            print(
                f"[{alert.created_at.isoformat()}] {emoji} "
                f"[{alert.severity.value.upper()}] [{alert.category.value}] "
                f"{alert.title}: {alert.message}"
            )
            return True

        self._notification_handlers[NotificationChannel.CONSOLE] = console_handler

    def create_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        category: AlertCategory,
        source: str,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Alert:
        """
        Створення нового алерта

        Args:
            title: Заголовок
            message: Повідомлення
            severity: Рівень критичності
            category: Категорія
            source: Джерело
            tags: Теги
            metadata: Метадані

        Returns:
            Створений алерт
        """
        # Генерація ID
        self._alert_counter += 1
        alert_id = f"alert_{self._alert_counter}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Дедуплікація
        dedup_key = self._generate_dedup_key(title, category, source)
        if self._is_duplicate(dedup_key):
            existing_alert = self._get_alert_by_dedup_key(dedup_key)
            if existing_alert:
                existing_alert.occurrence_count += 1
                existing_alert.updated_at = datetime.now()
                if metadata:
                    existing_alert.metadata.update(metadata)
                return existing_alert

        # Створення нового алерта
        alert = Alert(
            alert_id=alert_id,
            title=title,
            message=message,
            severity=severity,
            category=category,
            source=source,
            tags=tags or set(),
            metadata=metadata or {},
        )

        # Збереження
        self._active_alerts[alert_id] = alert
        self._add_to_history(alert)
        self._mark_dedup_key(dedup_key)

        # Сповіщення
        self._notify_subscribers(alert)
        self._send_notifications(alert)

        return alert

    def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> bool:
        """
        Підтвердження алерта

        Args:
            alert_id: ID алерта
            acknowledged_by: Хто підтвердив

        Returns:
            True якщо успішно
        """
        if alert_id not in self._active_alerts:
            return False

        alert = self._active_alerts[alert_id]
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.now()
        alert.acknowledged_by = acknowledged_by
        alert.updated_at = datetime.now()

        return True

    def resolve_alert(self, alert_id: str, resolution_note: Optional[str] = None) -> bool:
        """
        Вирішення алерта

        Args:
            alert_id: ID алерта
            resolution_note: Примітка щодо вирішення

        Returns:
            True якщо успішно
        """
        if alert_id not in self._active_alerts:
            return False

        alert = self._active_alerts[alert_id]
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now()
        alert.updated_at = datetime.now()

        if resolution_note:
            alert.metadata["resolution_note"] = resolution_note

        # Переміщення з активних
        del self._active_alerts[alert_id]

        return True

    def suppress_alert(self, alert_id: str, duration_seconds: int = 3600) -> bool:
        """
        Придушення алерта

        Args:
            alert_id: ID алерта
            duration_seconds: Тривалість придушення

        Returns:
            True якщо успішно
        """
        if alert_id not in self._active_alerts:
            return False

        alert = self._active_alerts[alert_id]
        alert.status = AlertStatus.SUPPRESSED
        alert.updated_at = datetime.now()
        alert.metadata["suppressed_until"] = (
            datetime.now() + timedelta(seconds=duration_seconds)
        ).isoformat()

        return True

    def add_rule(self, rule: AlertRule) -> bool:
        """
        Додавання правила алертів

        Args:
            rule: Правило

        Returns:
            True якщо успішно
        """
        if rule.rule_id in self._rules:
            return False

        self._rules[rule.rule_id] = rule
        return True

    def remove_rule(self, rule_id: str) -> bool:
        """
        Видалення правила

        Args:
            rule_id: ID правила

        Returns:
            True якщо успішно
        """
        if rule_id not in self._rules:
            return False

        del self._rules[rule_id]
        return True

    def evaluate_rules(self, context: Dict[str, Any]) -> List[Alert]:
        """
        Оцінка правил та генерація алертів

        Args:
            context: Контекст для оцінки правил

        Returns:
            Список створених алертів
        """
        created_alerts = []

        for rule in self._rules.values():
            if not rule.enabled:
                continue

            # Перевірка cooldown
            if rule.last_triggered:
                cooldown_end = rule.last_triggered + timedelta(seconds=rule.cooldown_seconds)
                if datetime.now() < cooldown_end:
                    continue

            try:
                # Оцінка умови
                if rule.condition(context):
                    # Генерація повідомлення з шаблону
                    title = rule.title_template.format(**context)
                    message = rule.message_template.format(**context)

                    alert = self.create_alert(
                        title=title,
                        message=message,
                        severity=rule.severity,
                        category=rule.category,
                        source=f"rule:{rule.rule_id}",
                        tags=rule.tags,
                        metadata={"rule_id": rule.rule_id, "context": context},
                    )

                    rule.last_triggered = datetime.now()
                    created_alerts.append(alert)

            except Exception as e:
                # Логування помилки без переривання
                print(f"Error evaluating rule {rule.rule_id}: {e}")

        return created_alerts

    def configure_notification_channel(self, config: NotificationConfig) -> None:
        """
        Налаштування каналу сповіщення

        Args:
            config: Конфігурація каналу
        """
        self._notification_configs[config.channel] = config

    def register_notification_handler(
        self,
        channel: NotificationChannel,
        handler: Callable[[Alert], bool],
    ) -> None:
        """
        Реєстрація обробника сповіщень

        Args:
            channel: Канал
            handler: Функція-обробник
        """
        self._notification_handlers[channel] = handler

    def subscribe(self, callback: Callable[[Alert], None]) -> None:
        """
        Підписка на алерти

        Args:
            callback: Функція зворотного виклику
        """
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[Alert], None]) -> None:
        """
        Відписка від алертів

        Args:
            callback: Функція зворотного виклику
        """
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def get_active_alerts(
        self,
        severity: Optional[AlertSeverity] = None,
        category: Optional[AlertCategory] = None,
    ) -> List[Alert]:
        """
        Отримання активних алертів

        Args:
            severity: Фільтр за рівнем критичності
            category: Фільтр за категорією

        Returns:
            Список алертів
        """
        alerts = list(self._active_alerts.values())

        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        if category:
            alerts = [a for a in alerts if a.category == category]

        return sorted(alerts, key=lambda a: a.created_at, reverse=True)

    def get_alert_history(
        self,
        limit: int = 100,
        severity: Optional[AlertSeverity] = None,
        category: Optional[AlertCategory] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Alert]:
        """
        Отримання історії алертів

        Args:
            limit: Максимальна кількість
            severity: Фільтр за рівнем критичності
            category: Фільтр за категорією
            start_time: Початок періоду
            end_time: Кінець періоду

        Returns:
            Список алертів
        """
        alerts = self._alert_history.copy()

        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        if category:
            alerts = [a for a in alerts if a.category == category]
        if start_time:
            alerts = [a for a in alerts if a.created_at >= start_time]
        if end_time:
            alerts = [a for a in alerts if a.created_at <= end_time]

        alerts = sorted(alerts, key=lambda a: a.created_at, reverse=True)
        return alerts[:limit]

    def get_stats(self) -> AlertStats:
        """
        Отримання статистики

        Returns:
            Об'єкт статистики
        """
        stats = AlertStats()
        stats.total_alerts = len(self._alert_history)
        stats.active_alerts = len(self._active_alerts)

        stats.acknowledged_alerts = len(
            [a for a in self._active_alerts.values() if a.status == AlertStatus.ACKNOWLEDGED]
        )
        stats.resolved_alerts = len(
            [a for a in self._alert_history if a.status == AlertStatus.RESOLVED]
        )

        for alert in self._alert_history:
            severity = alert.severity.value
            category = alert.category.value

            stats.by_severity[severity] = stats.by_severity.get(severity, 0) + 1
            stats.by_category[category] = stats.by_category.get(category, 0) + 1

        return stats

    def _generate_dedup_key(self, title: str, category: AlertCategory, source: str) -> str:
        """Генерація ключа дедуплікації"""
        key_string = f"{title}:{category.value}:{source}"
        return hashlib.md5(key_string.encode()).hexdigest()

    def _is_duplicate(self, dedup_key: str) -> bool:
        """Перевірка на дублікат"""
        if not self.enable_aggregation:
            return False

        if dedup_key not in self._dedup_cache:
            return False

        last_seen = self._dedup_cache[dedup_key]
        window = timedelta(seconds=self.deduplication_window_seconds)

        return datetime.now() - last_seen < window

    def _mark_dedup_key(self, dedup_key: str) -> None:
        """Позначення ключа дедуплікації"""
        self._dedup_cache[dedup_key] = datetime.now()

        # Очищення старих записів
        cutoff = datetime.now() - timedelta(seconds=self.deduplication_window_seconds * 2)
        self._dedup_cache = {k: v for k, v in self._dedup_cache.items() if v > cutoff}

    def _get_alert_by_dedup_key(self, dedup_key: str) -> Optional[Alert]:
        """Отримання алерта за ключем дедуплікації"""
        for alert in self._active_alerts.values():
            key = self._generate_dedup_key(alert.title, alert.category, alert.source)
            if key == dedup_key:
                return alert
        return None

    def _add_to_history(self, alert: Alert) -> None:
        """Додавання до історії"""
        self._alert_history.append(alert)

        # Обмеження розміру історії
        if len(self._alert_history) > self.max_history_size:
            self._alert_history = self._alert_history[-self.max_history_size :]

    def _notify_subscribers(self, alert: Alert) -> None:
        """Сповіщення підписників"""
        for subscriber in self._subscribers:
            try:
                subscriber(alert)
            except Exception as e:
                print(f"Error notifying subscriber: {e}")

    def _send_notifications(self, alert: Alert) -> None:
        """Відправка сповіщень через канали"""
        for channel, config in self._notification_configs.items():
            if not config.enabled:
                continue

            # Перевірка мінімального рівня критичності
            severity_order = [
                AlertSeverity.DEBUG,
                AlertSeverity.INFO,
                AlertSeverity.WARNING,
                AlertSeverity.ERROR,
                AlertSeverity.CRITICAL,
            ]
            if severity_order.index(alert.severity) < severity_order.index(config.min_severity):
                continue

            # Виклик обробника
            handler = self._notification_handlers.get(channel)
            if handler:
                try:
                    handler(alert)
                except Exception as e:
                    print(f"Error sending notification via {channel.value}: {e}")

    def get_summary(self) -> Dict:
        """
        Отримання загальної статистики

        Returns:
            Словник зі статистикою
        """
        stats = self.get_stats()

        return {
            "active_alerts": stats.active_alerts,
            "total_alerts": stats.total_alerts,
            "acknowledged": stats.acknowledged_alerts,
            "resolved": stats.resolved_alerts,
            "by_severity": stats.by_severity,
            "by_category": stats.by_category,
            "rules_count": len(self._rules),
            "channels_configured": len(self._notification_configs),
            "subscribers_count": len(self._subscribers),
        }


# Фабрика глобального менеджера
_global_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """
    Отримання глобального менеджера алертів

    Returns:
        Глобальний екземпляр
    """
    global _global_alert_manager
    if _global_alert_manager is None:
        _global_alert_manager = AlertManager()

        # Додавання базових правил
        _global_alert_manager.add_rule(
            AlertRule(
                rule_id="high_drawdown",
                name="High Drawdown Alert",
                condition=lambda ctx: ctx.get("drawdown", 0) > 0.1,
                title_template="High Portfolio Drawdown",
                message_template="Portfolio drawdown reached {drawdown:.2%}",
                severity=AlertSeverity.WARNING,
                category=AlertCategory.RISK,
                tags={"risk", "drawdown"},
            )
        )

        _global_alert_manager.add_rule(
            AlertRule(
                rule_id="critical_drawdown",
                name="Critical Drawdown Alert",
                condition=lambda ctx: ctx.get("drawdown", 0) > 0.2,
                title_template="Critical Portfolio Drawdown",
                message_template="Portfolio drawdown reached critical level: {drawdown:.2%}",
                severity=AlertSeverity.CRITICAL,
                category=AlertCategory.RISK,
                tags={"risk", "drawdown", "critical"},
            )
        )

        _global_alert_manager.add_rule(
            AlertRule(
                rule_id="high_volatility",
                name="High Volatility Alert",
                condition=lambda ctx: ctx.get("volatility", 0) > 0.4,
                title_template="High Market Volatility",
                message_template="Market volatility at {volatility:.2%}",
                severity=AlertSeverity.WARNING,
                category=AlertCategory.MARKET,
                tags={"market", "volatility"},
            )
        )

    return _global_alert_manager
