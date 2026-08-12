# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
System Health Dashboard Module

Модуль для агрегації та відображення здоров'я торгової системи.

Features:
- Моніторинг компонентів системи
- Агрегація метрик здоров'я
- Алерти та сповіщення
- Діагностика проблем
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class ComponentStatus(str, Enum):
    """Статус компонента"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    MAINTENANCE = "maintenance"


class ComponentType(str, Enum):
    """Тип компонента"""

    DATA_FEED = "data_feed"
    STRATEGY = "strategy"
    RISK_MANAGER = "risk_manager"
    EXECUTION = "execution"
    DATABASE = "database"
    MESSAGING = "messaging"
    EXTERNAL_API = "external_api"
    MONITORING = "monitoring"
    SCHEDULER = "scheduler"
    CACHE = "cache"


@dataclass
class HealthCheck:
    """Результат перевірки здоров'я"""

    check_name: str
    status: ComponentStatus
    message: str
    latency_ms: float = 0.0
    last_check: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComponentHealth:
    """Здоров'я компонента"""

    component_id: str
    component_name: str
    component_type: ComponentType
    status: ComponentStatus
    health_checks: List[HealthCheck] = field(default_factory=list)
    uptime_seconds: float = 0.0
    error_count: int = 0
    last_error: Optional[str] = None
    last_update: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemMetrics:
    """Метрики системи"""

    cpu_usage_percent: float = 0.0
    memory_usage_percent: float = 0.0
    disk_usage_percent: float = 0.0
    network_latency_ms: float = 0.0
    active_connections: int = 0
    queue_depth: int = 0
    messages_per_second: float = 0.0
    orders_per_minute: float = 0.0


@dataclass
class HealthAlert:
    """Алерт здоров'я"""

    alert_id: str
    component_id: str
    severity: str
    title: str
    description: str
    created_at: datetime = field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None
    is_resolved: bool = False


@dataclass
class SystemHealthSummary:
    """Загальний саммарі здоров'я системи"""

    overall_status: ComponentStatus
    healthy_components: int
    degraded_components: int
    unhealthy_components: int
    active_alerts: int
    uptime_percent: float
    last_update: datetime = field(default_factory=datetime.now)


class SystemHealthDashboard:
    """
    Dashboard здоров'я системи

    Централізований моніторинг стану всіх компонентів системи.
    """

    def __init__(
        self,
        check_interval_seconds: float = 30.0,
        unhealthy_threshold_errors: int = 3,
        degraded_threshold_latency_ms: float = 500.0,
    ):
        """
        Ініціалізація dashboard

        Args:
            check_interval_seconds: Інтервал перевірки
            unhealthy_threshold_errors: Поріг помилок для unhealthy
            degraded_threshold_latency_ms: Поріг latency для degraded
        """
        self.check_interval_seconds = check_interval_seconds
        self.unhealthy_threshold_errors = unhealthy_threshold_errors
        self.degraded_threshold_latency_ms = degraded_threshold_latency_ms

        # Компоненти
        self._components: Dict[str, ComponentHealth] = {}

        # Health check функції
        self._health_checks: Dict[str, Callable[[], HealthCheck]] = {}

        # Алерти
        self._alerts: List[HealthAlert] = []
        self._alert_counter = 0

        # Метрики системи
        self._system_metrics = SystemMetrics()

        # Час запуску
        self._start_time = datetime.now()

        # Історія статусів
        self._status_history: List[Dict[str, Any]] = []

        # Підписники на зміни
        self._subscribers: List[Callable[[ComponentHealth], None]] = []

    def register_component(
        self,
        component_id: str,
        component_name: str,
        component_type: ComponentType,
        health_check: Optional[Callable[[], HealthCheck]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Реєстрація компонента

        Args:
            component_id: ID компонента
            component_name: Назва компонента
            component_type: Тип компонента
            health_check: Функція перевірки здоров'я
            metadata: Метадані

        Returns:
            True якщо успішно
        """
        if component_id in self._components:
            return False

        component = ComponentHealth(
            component_id=component_id,
            component_name=component_name,
            component_type=component_type,
            status=ComponentStatus.UNKNOWN,
            metadata=metadata or {},
        )

        self._components[component_id] = component

        if health_check:
            self._health_checks[component_id] = health_check

        return True

    def unregister_component(self, component_id: str) -> bool:
        """
        Видалення компонента

        Args:
            component_id: ID компонента

        Returns:
            True якщо успішно
        """
        if component_id not in self._components:
            return False

        del self._components[component_id]

        if component_id in self._health_checks:
            del self._health_checks[component_id]

        return True

    def update_component_status(
        self,
        component_id: str,
        status: ComponentStatus,
        message: Optional[str] = None,
        error: Optional[str] = None,
    ) -> bool:
        """
        Оновлення статусу компонента

        Args:
            component_id: ID компонента
            status: Новий статус
            message: Повідомлення
            error: Помилка

        Returns:
            True якщо успішно
        """
        if component_id not in self._components:
            return False

        component = self._components[component_id]
        old_status = component.status
        component.status = status
        component.last_update = datetime.now()

        if error:
            component.error_count += 1
            component.last_error = error

        # Оновлення uptime
        component.uptime_seconds = (datetime.now() - self._start_time).total_seconds()

        # Генерація алерту при зміні статусу
        if old_status != status:
            self._handle_status_change(component, old_status, status)
            self._notify_subscribers(component)

        return True

    def run_health_checks(self) -> Dict[str, HealthCheck]:
        """
        Виконання всіх health checks

        Returns:
            Словник результатів
        """
        results = {}

        for component_id, check_func in self._health_checks.items():
            try:
                start_time = datetime.now()
                result = check_func()
                result.latency_ms = (datetime.now() - start_time).total_seconds() * 1000
                result.last_check = datetime.now()
                results[component_id] = result

                # Оновлення статусу компонента
                self._update_from_health_check(component_id, result)

            except Exception as e:
                # Помилка під час перевірки
                result = HealthCheck(
                    check_name=f"{component_id}_check",
                    status=ComponentStatus.UNHEALTHY,
                    message=f"Health check failed: {str(e)}",
                )
                results[component_id] = result
                self.update_component_status(
                    component_id,
                    ComponentStatus.UNHEALTHY,
                    error=str(e),
                )

        return results

    def get_component_health(self, component_id: str) -> Optional[ComponentHealth]:
        """
        Отримання здоров'я компонента

        Args:
            component_id: ID компонента

        Returns:
            Здоров'я компонента або None
        """
        return self._components.get(component_id)

    def get_all_components(
        self,
        component_type: Optional[ComponentType] = None,
        status: Optional[ComponentStatus] = None,
    ) -> List[ComponentHealth]:
        """
        Отримання всіх компонентів

        Args:
            component_type: Фільтр за типом
            status: Фільтр за статусом

        Returns:
            Список компонентів
        """
        components = list(self._components.values())

        if component_type:
            components = [c for c in components if c.component_type == component_type]
        if status:
            components = [c for c in components if c.status == status]

        return sorted(components, key=lambda c: c.component_name)

    def get_system_summary(self) -> SystemHealthSummary:
        """
        Отримання саммарі системи

        Returns:
            Саммарі здоров'я
        """
        healthy = 0
        degraded = 0
        unhealthy = 0

        for component in self._components.values():
            if component.status == ComponentStatus.HEALTHY:
                healthy += 1
            elif component.status == ComponentStatus.DEGRADED:
                degraded += 1
            elif component.status == ComponentStatus.UNHEALTHY:
                unhealthy += 1

        total = healthy + degraded + unhealthy
        uptime_percent = (healthy + degraded) / total * 100 if total > 0 else 100.0

        # Визначення загального статусу
        if unhealthy > 0:
            overall_status = ComponentStatus.UNHEALTHY
        elif degraded > 0:
            overall_status = ComponentStatus.DEGRADED
        elif healthy > 0:
            overall_status = ComponentStatus.HEALTHY
        else:
            overall_status = ComponentStatus.UNKNOWN

        active_alerts = len([a for a in self._alerts if not a.is_resolved])

        return SystemHealthSummary(
            overall_status=overall_status,
            healthy_components=healthy,
            degraded_components=degraded,
            unhealthy_components=unhealthy,
            active_alerts=active_alerts,
            uptime_percent=uptime_percent,
        )

    def update_system_metrics(self, metrics: SystemMetrics) -> None:
        """
        Оновлення метрик системи

        Args:
            metrics: Нові метрики
        """
        self._system_metrics = metrics

        # Запис в історію
        self._status_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "cpu": metrics.cpu_usage_percent,
                "memory": metrics.memory_usage_percent,
                "disk": metrics.disk_usage_percent,
            }
        )

        # Обмеження розміру історії
        max_history = 1000
        if len(self._status_history) > max_history:
            self._status_history = self._status_history[-max_history:]

    def get_system_metrics(self) -> SystemMetrics:
        """
        Отримання метрик системи

        Returns:
            Метрики системи
        """
        return self._system_metrics

    def create_alert(
        self,
        component_id: str,
        severity: str,
        title: str,
        description: str,
    ) -> HealthAlert:
        """
        Створення алерту

        Args:
            component_id: ID компонента
            severity: Критичність
            title: Заголовок
            description: Опис

        Returns:
            Алерт
        """
        self._alert_counter += 1
        alert = HealthAlert(
            alert_id=f"alert_{self._alert_counter}",
            component_id=component_id,
            severity=severity,
            title=title,
            description=description,
        )

        self._alerts.append(alert)
        return alert

    def resolve_alert(self, alert_id: str) -> bool:
        """
        Вирішення алерту

        Args:
            alert_id: ID алерту

        Returns:
            True якщо успішно
        """
        for alert in self._alerts:
            if alert.alert_id == alert_id and not alert.is_resolved:
                alert.is_resolved = True
                alert.resolved_at = datetime.now()
                return True

        return False

    def get_active_alerts(
        self,
        component_id: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> List[HealthAlert]:
        """
        Отримання активних алертів

        Args:
            component_id: Фільтр за компонентом
            severity: Фільтр за критичністю

        Returns:
            Список алертів
        """
        alerts = [a for a in self._alerts if not a.is_resolved]

        if component_id:
            alerts = [a for a in alerts if a.component_id == component_id]
        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        return sorted(alerts, key=lambda a: a.created_at, reverse=True)

    def get_diagnostics(self, component_id: str) -> Dict[str, Any]:
        """
        Отримання діагностики компонента

        Args:
            component_id: ID компонента

        Returns:
            Діагностична інформація
        """
        component = self._components.get(component_id)
        if not component:
            return {"error": "Component not found"}

        # Збір діагностичної інформації
        recent_alerts = [
            a
            for a in self._alerts
            if a.component_id == component_id
            and (datetime.now() - a.created_at).total_seconds() < 86400
        ]

        # Історія health checks
        health_history = component.health_checks[-10:]  # Останні 10

        return {
            "component_id": component_id,
            "component_name": component.component_name,
            "component_type": component.component_type.value,
            "current_status": component.status.value,
            "uptime_seconds": component.uptime_seconds,
            "uptime_formatted": str(timedelta(seconds=int(component.uptime_seconds))),
            "error_count": component.error_count,
            "last_error": component.last_error,
            "last_update": component.last_update.isoformat(),
            "recent_alerts": len(recent_alerts),
            "health_checks_count": len(health_history),
            "metadata": component.metadata,
            "recommendations": self._generate_recommendations(component),
        }

    def subscribe(self, callback: Callable[[ComponentHealth], None]) -> None:
        """
        Підписка на зміни

        Args:
            callback: Функція зворотного виклику
        """
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[ComponentHealth], None]) -> None:
        """
        Відписка від змін

        Args:
            callback: Функція зворотного виклику
        """
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def _update_from_health_check(self, component_id: str, check: HealthCheck) -> None:
        """Оновлення компонента з результату health check"""
        if component_id not in self._components:
            return

        component = self._components[component_id]

        # Збереження результату
        component.health_checks.append(check)

        # Обмеження розміру історії
        max_checks = 100
        if len(component.health_checks) > max_checks:
            component.health_checks = component.health_checks[-max_checks:]

        # Визначення статусу на основі check
        new_status = check.status

        # Врахування latency
        if (
            check.latency_ms > self.degraded_threshold_latency_ms
            and check.status == ComponentStatus.HEALTHY
        ):
            new_status = ComponentStatus.DEGRADED

        # Врахування кількості помилок
        if component.error_count >= self.unhealthy_threshold_errors:
            new_status = ComponentStatus.UNHEALTHY

        self.update_component_status(component_id, new_status)

    def _handle_status_change(
        self,
        component: ComponentHealth,
        old_status: ComponentStatus,
        new_status: ComponentStatus,
    ) -> None:
        """Обробка зміни статусу"""
        # Створення алерту для degraded/unhealthy
        if new_status in [ComponentStatus.DEGRADED, ComponentStatus.UNHEALTHY]:
            severity = "warning" if new_status == ComponentStatus.DEGRADED else "critical"
            self.create_alert(
                component_id=component.component_id,
                severity=severity,
                title=f"{component.component_name} is {new_status.value}",
                description=f"Component status changed from {old_status.value} to {new_status.value}",
            )

        # Автоматичне вирішення алертів при відновленні
        if new_status == ComponentStatus.HEALTHY and old_status in [
            ComponentStatus.DEGRADED,
            ComponentStatus.UNHEALTHY,
        ]:
            for alert in self._alerts:
                if alert.component_id == component.component_id and not alert.is_resolved:
                    self.resolve_alert(alert.alert_id)

    def _notify_subscribers(self, component: ComponentHealth) -> None:
        """Сповіщення підписників"""
        for subscriber in self._subscribers:
            try:
                subscriber(component)
            except Exception as e:
                print(f"Error notifying subscriber: {e}")

    def _generate_recommendations(self, component: ComponentHealth) -> List[str]:
        """Генерація рекомендацій"""
        recommendations = []

        if component.status == ComponentStatus.UNHEALTHY:
            recommendations.append(
                "Component is unhealthy. Check logs for errors and restart if necessary."
            )

            if component.error_count > 0:
                recommendations.append(
                    f"Component has {component.error_count} errors. Investigate the root cause."
                )

        if component.status == ComponentStatus.DEGRADED:
            recommendations.append("Component is degraded. Monitor closely for further issues.")

            # Перевірка latency
            if component.health_checks:
                avg_latency = sum(h.latency_ms for h in component.health_checks) / len(
                    component.health_checks
                )
                if avg_latency > self.degraded_threshold_latency_ms:
                    recommendations.append(
                        f"Average latency is {avg_latency:.0f}ms. Check for performance issues."
                    )

        if component.last_error:
            recommendations.append(f"Last error: {component.last_error}")

        if not recommendations:
            recommendations.append("Component is healthy. No actions required.")

        return recommendations

    def get_dashboard_data(self) -> Dict[str, Any]:
        """
        Отримання даних для dashboard

        Returns:
            Дані для відображення
        """
        summary = self.get_system_summary()

        # Групування по типах
        by_type: Dict[str, List[Dict[str, Any]]] = {}
        for component in self._components.values():
            type_name = component.component_type.value
            if type_name not in by_type:
                by_type[type_name] = []

            by_type[type_name].append(
                {
                    "id": component.component_id,
                    "name": component.component_name,
                    "status": component.status.value,
                    "error_count": component.error_count,
                    "last_update": component.last_update.isoformat(),
                }
            )

        return {
            "summary": {
                "overall_status": summary.overall_status.value,
                "healthy": summary.healthy_components,
                "degraded": summary.degraded_components,
                "unhealthy": summary.unhealthy_components,
                "active_alerts": summary.active_alerts,
                "uptime_percent": f"{summary.uptime_percent:.1f}%",
            },
            "metrics": {
                "cpu": f"{self._system_metrics.cpu_usage_percent:.1f}%",
                "memory": f"{self._system_metrics.memory_usage_percent:.1f}%",
                "disk": f"{self._system_metrics.disk_usage_percent:.1f}%",
                "network_latency": f"{self._system_metrics.network_latency_ms:.0f}ms",
                "orders_per_minute": f"{self._system_metrics.orders_per_minute:.1f}",
            },
            "components_by_type": by_type,
            "active_alerts": [
                {
                    "id": a.alert_id,
                    "component": a.component_id,
                    "severity": a.severity,
                    "title": a.title,
                    "created_at": a.created_at.isoformat(),
                }
                for a in self.get_active_alerts()[:5]
            ],
            "last_update": datetime.now().isoformat(),
        }

    def get_summary(self) -> Dict:
        """
        Отримання саммарі

        Returns:
            Словник зі статистикою
        """
        summary = self.get_system_summary()

        return {
            "overall_status": summary.overall_status.value,
            "total_components": len(self._components),
            "healthy_components": summary.healthy_components,
            "degraded_components": summary.degraded_components,
            "unhealthy_components": summary.unhealthy_components,
            "active_alerts": summary.active_alerts,
            "total_alerts": len(self._alerts),
            "uptime_percent": f"{summary.uptime_percent:.1f}%",
            "system_uptime": str(
                timedelta(seconds=int((datetime.now() - self._start_time).total_seconds()))
            ),
            "health_checks_registered": len(self._health_checks),
            "subscribers": len(self._subscribers),
        }
