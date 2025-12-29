"""Практичні приклади оптимізацій для TradePulse.

Цей модуль демонструє конкретні оптимізації, описані в SYSTEM_OPTIMIZATION_ANALYSIS_UA.md.
"""

import hashlib
import logging
import time
from collections import deque
from dataclasses import dataclass
from functools import wraps
from queue import Empty, Queue
from threading import RLock, Thread
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import numpy as np

from core.utils.determinism import DEFAULT_SEED, seed_numpy

SEED = DEFAULT_SEED

logger = logging.getLogger(__name__)


# ============================================================================
# 1. Event Sourcing Optimizations
# ============================================================================


class StreamingEventReplayer:
    """Оптимізований event replayer з батчингом та streaming."""

    def __init__(self, batch_size: int = 1000):
        self.batch_size = batch_size
        self._stats = {
            "total_events": 0,
            "batches_processed": 0,
            "cache_hits": 0,
        }

    def replay_events_streaming(
        self,
        aggregate_id: str,
        aggregate_type: str,
        since_version: int = 0,
    ) -> Iterator[List[Dict]]:
        """
        Повертає події батчами замість завантаження всіх в пам'ять.

        Переваги:
        - Константне використання пам'яті
        - Можливість обробки мільйонів подій
        - Раннє виявлення помилок

        Yields:
            Батчі подій розміром до batch_size
        """
        last_version = since_version

        while True:
            # Симуляція запиту до БД (замініть на реальний код)
            events = self._fetch_batch(aggregate_id, aggregate_type, last_version)

            if not events:
                break

            self._stats["batches_processed"] += 1
            self._stats["total_events"] += len(events)

            last_version = events[-1]["version"]
            yield events

    def _fetch_batch(
        self, aggregate_id: str, aggregate_type: str, since_version: int
    ) -> List[Dict]:
        """Fetch batch from database with limit.

        This method is designed to work with SQLAlchemy sessions.
        For production use, inject a session and event table into the constructor.

        Example usage with real database:
            from sqlalchemy import select
            from sqlalchemy.orm import Session

            # In constructor:
            self._session = session
            self._events_table = events_table

            # In this method:
            stmt = (
                select(self._events_table)
                .where(
                    self._events_table.c.aggregate_id == aggregate_id,
                    self._events_table.c.aggregate_type == aggregate_type,
                    self._events_table.c.version > since_version
                )
                .order_by(self._events_table.c.version)
                .limit(self.batch_size)
            )
            return [dict(row) for row in self._session.execute(stmt).fetchall()]
        """
        # Default implementation returns empty list for demonstration
        # Override this method or inject database session for production use
        return []

    def get_stats(self) -> Dict[str, int]:
        """Статистика для моніторингу."""
        return self._stats.copy()


# ============================================================================
# 2. Adaptive Polling для Live Execution Loop
# ============================================================================


@dataclass
class AdaptivePollingConfig:
    """Конфігурація для adaptive polling."""

    min_interval: float = 0.1  # 100ms при активності
    max_interval: float = 2.0  # 2s при idle
    ramp_up_threshold: int = 5  # Скільки idle циклів до збільшення
    ramp_down_threshold: int = 1  # Скільки активних циклів до зменшення


class AdaptivePoller:
    """
    Adaptive polling механізм з динамічним інтервалом.

    Автоматично зменшує частоту polling коли немає активності,
    економлячи CPU та мережевий bandwidth.
    """

    def __init__(self, config: AdaptivePollingConfig):
        self.config = config
        self._current_interval = config.min_interval
        self._idle_cycles = 0
        self._active_cycles = 0

        self._stats = {
            "total_polls": 0,
            "active_polls": 0,
            "idle_polls": 0,
            "avg_interval": config.min_interval,
        }

    def poll(self, check_activity_fn: Callable[[], bool]) -> bool:
        """
        Виконує polling з adaptive інтервалом.

        Args:
            check_activity_fn: Функція яка перевіряє чи є активність

        Returns:
            True якщо була активність, False інакше
        """
        self._stats["total_polls"] += 1

        # Перевірка активності
        has_activity = check_activity_fn()

        if has_activity:
            self._on_activity()
            self._stats["active_polls"] += 1
        else:
            self._on_idle()
            self._stats["idle_polls"] += 1

        # Оновлення середнього інтервалу
        self._update_avg_interval()

        # Sleep до наступного poll
        time.sleep(self._current_interval)

        return has_activity

    def _on_activity(self):
        """Обробка активного циклу."""
        self._active_cycles += 1
        self._idle_cycles = 0

        # Швидко зменшуємо інтервал при активності
        if self._active_cycles >= self.config.ramp_down_threshold:
            self._current_interval = self.config.min_interval
            self._active_cycles = 0

    def _on_idle(self):
        """Обробка idle циклу."""
        self._idle_cycles += 1
        self._active_cycles = 0

        # Поступово збільшуємо інтервал при idle
        if self._idle_cycles >= self.config.ramp_up_threshold:
            self._current_interval = min(
                self._current_interval * 1.5, self.config.max_interval
            )

    def _update_avg_interval(self):
        """Оновлює середній інтервал для метрик."""
        alpha = 0.1  # Exponential moving average
        self._stats["avg_interval"] = (
            alpha * self._current_interval + (1 - alpha) * self._stats["avg_interval"]
        )

    def get_stats(self) -> Dict[str, Any]:
        """Статистика для моніторингу."""
        stats = self._stats.copy()
        stats["current_interval"] = self._current_interval
        stats["idle_ratio"] = self._stats["idle_polls"] / max(
            self._stats["total_polls"], 1
        )
        return stats


# ============================================================================
# 3. Indicator Cache з TTL
# ============================================================================


class IndicatorCache:
    """
    Інтелектуальний кеш для індикаторів з TTL та LRU eviction.

    Кешує результати дорогих обчислень індикаторів щоб уникнути
    повторних обчислень на тих самих даних.
    """

    def __init__(
        self, max_size: int = 1000, ttl_seconds: float = 60.0, enable_stats: bool = True
    ):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._access_order: deque = deque()  # For LRU
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = RLock()

        self._stats = (
            {
                "hits": 0,
                "misses": 0,
                "evictions": 0,
                "expirations": 0,
            }
            if enable_stats
            else None
        )

    def get_or_compute(
        self,
        key: str,
        data: np.ndarray,
        compute_fn: Callable[[], Any],
        params: Optional[Dict] = None,
    ) -> Any:
        """
        Отримати з кешу або обчислити.

        Args:
            key: Базовий ключ (наприклад, "ricci")
            data: Numpy array даних
            compute_fn: Функція обчислення якщо немає в кеші
            params: Додаткові параметри для ключа

        Returns:
            Результат обчислення (з кешу або новий)
        """
        # Генерація повного ключа
        cache_key = self._make_cache_key(key, data, params)

        with self._lock:
            now = time.time()

            # Перевірка кешу
            if cache_key in self._cache:
                value, timestamp = self._cache[cache_key]

                # Перевірка TTL
                if now - timestamp < self._ttl:
                    # Cache hit
                    self._record_hit()
                    self._update_lru(cache_key)
                    return value
                else:
                    # Expired
                    self._record_expiration()
                    del self._cache[cache_key]

            # Cache miss - обчислити
            self._record_miss()
            value = compute_fn()

            # Зберегти в кеші
            self._cache[cache_key] = (value, now)
            self._access_order.append(cache_key)

            # LRU eviction якщо потрібно
            if len(self._cache) > self._max_size:
                self._evict_lru()

            return value

    def _make_cache_key(
        self, key: str, data: np.ndarray, params: Optional[Dict]
    ) -> str:
        """Створює ключ кешу з даних та параметрів."""
        # Hash даних (швидкий для numpy)
        data_hash = hashlib.blake2b(data.tobytes(), digest_size=16).hexdigest()

        # Hash параметрів
        if params:
            params_str = str(sorted(params.items()))
            params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
        else:
            params_hash = "none"

        return f"{key}:{data_hash}:{params_hash}"

    def _update_lru(self, key: str):
        """Оновлює LRU для ключа."""
        # Переміщуємо в кінець deque (most recently used)
        try:
            self._access_order.remove(key)
        except ValueError:
            pass
        self._access_order.append(key)

    def _evict_lru(self):
        """Видаляє найстарший елемент (LRU)."""
        if self._access_order:
            oldest_key = self._access_order.popleft()
            if oldest_key in self._cache:
                del self._cache[oldest_key]
                self._record_eviction()

    def _record_hit(self):
        if self._stats is not None:
            self._stats["hits"] += 1

    def _record_miss(self):
        if self._stats is not None:
            self._stats["misses"] += 1

    def _record_eviction(self):
        if self._stats is not None:
            self._stats["evictions"] += 1

    def _record_expiration(self):
        if self._stats is not None:
            self._stats["expirations"] += 1

    def get_stats(self) -> Optional[Dict[str, Any]]:
        """Статистика кешу."""
        if self._stats is None:
            return None

        with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = (
                self._stats["hits"] / total_requests if total_requests > 0 else 0.0
            )

            return {
                **self._stats,
                "hit_rate": hit_rate,
                "size": len(self._cache),
                "capacity": self._max_size,
            }

    def clear(self):
        """Очищення кешу."""
        with self._lock:
            self._cache.clear()
            self._access_order.clear()


# ============================================================================
# 4. Async Metrics Writer
# ============================================================================


class AsyncMetricsWriter:
    """
    Асинхронний writer для метрик з батчингом.

    Записує метрики в background thread батчами замість синхронного
    запису кожної метрики, що значно зменшує latency.
    """

    def __init__(
        self,
        batch_size: int = 100,
        flush_interval: float = 1.0,
        max_queue_size: int = 10000,
    ):
        self._queue: Queue = Queue(maxsize=max_queue_size)
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._worker_thread: Optional[Thread] = None
        self._running = False
        self._prometheus_gauges: Dict[str, Any] = (
            {}
        )  # Initialize Prometheus gauges dict

        self._stats = {
            "total_recorded": 0,
            "total_flushed": 0,
            "total_dropped": 0,
            "flush_count": 0,
        }

    def start(self):
        """Запуск background worker."""
        if self._running:
            return

        self._running = True
        self._worker_thread = Thread(target=self._worker, daemon=True)
        self._worker_thread.start()
        logger.info("AsyncMetricsWriter started")

    def stop(self):
        """Зупинка worker та flush залишку."""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)
        logger.info("AsyncMetricsWriter stopped")

    def record(
        self, metric_name: str, value: float, labels: Optional[Dict[str, str]] = None
    ):
        """
        Додає метрику в чергу для асинхронного запису.

        Args:
            metric_name: Ім'я метрики
            value: Значення
            labels: Додаткові labels
        """
        try:
            self._queue.put_nowait((metric_name, value, labels or {}, time.time()))
            self._stats["total_recorded"] += 1
        except Exception:  # noqa: BLE001 - intentionally catch all for queue operations
            # Queue full - краще drop ніж blocking
            self._stats["total_dropped"] += 1
            logger.warning(
                "Metrics queue full, dropping metric", extra={"metric": metric_name}
            )

    def _worker(self):
        """Worker thread для батчевого запису."""
        batch = []
        last_flush = time.time()

        while self._running:
            try:
                # Отримати метрику з timeout
                item = self._queue.get(timeout=0.1)
                batch.append(item)

                # Flush якщо:
                # 1. Batch заповнений, або
                # 2. Минув час flush_interval
                now = time.time()
                should_flush = len(batch) >= self._batch_size or (
                    now - last_flush >= self._flush_interval and batch
                )

                if should_flush:
                    self._flush_batch(batch)
                    batch = []
                    last_flush = now

            except Empty:
                # Timeout - flush якщо є що флашити
                if batch:
                    self._flush_batch(batch)
                    batch = []
                    last_flush = time.time()

        # Final flush при зупинці
        if batch:
            self._flush_batch(batch)

    def _flush_batch(self, batch: List[Tuple]):
        """
        Записує батч метрик.

        Integrates with Prometheus client for production use.
        Requires prometheus_client package to be installed.

        Example production setup:
            from prometheus_client import Gauge, Counter, Histogram

            # Create metrics registry in constructor:
            self._gauges = {}
            self._counters = {}

            # Use in this method:
            for metric_name, value, labels, timestamp in batch:
                if metric_name not in self._gauges:
                    self._gauges[metric_name] = Gauge(metric_name, '', list(labels.keys()))
                self._gauges[metric_name].labels(**labels).set(value)
        """
        try:
            # Attempt Prometheus integration if available
            try:
                from prometheus_client import Gauge

                for metric_name, value, labels, timestamp in batch:
                    gauge_key = f"{metric_name}:{sorted(labels.keys())}"
                    if gauge_key not in self._prometheus_gauges:
                        # Create gauge with label names
                        label_names = list(labels.keys()) if labels else []
                        # Sanitize metric name for Prometheus (only letters, digits, underscores)
                        safe_name = "".join(
                            c if c.isalnum() or c == "_" else "_" for c in metric_name
                        )
                        self._prometheus_gauges[gauge_key] = Gauge(
                            safe_name, f"Metric {metric_name}", label_names
                        )

                    if labels:
                        self._prometheus_gauges[gauge_key].labels(**labels).set(value)
                    else:
                        self._prometheus_gauges[gauge_key].set(value)
            except ImportError:
                # Prometheus client not installed - log metrics locally
                pass

            self._stats["total_flushed"] += len(batch)
            self._stats["flush_count"] += 1

            logger.debug(
                f"Flushed {len(batch)} metrics", extra={"batch_size": len(batch)}
            )
        except Exception as e:
            logger.error(f"Failed to flush metrics batch: {e}", exc_info=True)

    def get_stats(self) -> Dict[str, Any]:
        """Статистика writer."""
        stats = self._stats.copy()
        stats["queue_size"] = self._queue.qsize()
        stats["drop_rate"] = self._stats["total_dropped"] / max(
            self._stats["total_recorded"], 1
        )
        return stats


# ============================================================================
# 5. Performance Monitoring Decorator
# ============================================================================


def monitor_performance(metric_name: str, enable_profiling: bool = False):
    """
    Decorator для моніторингу продуктивності функцій.

    Автоматично записує:
    - Час виконання
    - Успішність / помилки
    - Опціонально - детальний профіль

    Usage:
        @monitor_performance("compute_indicator")
        def my_indicator(data):
            ...
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()

            # Опціональний профайлер
            if enable_profiling:
                import cProfile

                profiler = cProfile.Profile()
                profiler.enable()

            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                # Запис метрики успіху
                _record_metric(
                    f"{metric_name}_duration_seconds", duration, {"status": "success"}
                )

                return result

            except Exception as e:
                duration = time.time() - start_time

                # Запис метрики помилки
                _record_metric(
                    f"{metric_name}_duration_seconds",
                    duration,
                    {"status": "error", "error_type": type(e).__name__},
                )

                raise

            finally:
                if enable_profiling:
                    profiler.disable()
                    # Зберегти профіль
                    import pstats

                    stats = pstats.Stats(profiler)
                    stats.dump_stats(
                        f"/tmp/profile_{metric_name}_{int(time.time())}.prof"
                    )

        return wrapper

    return decorator


# Global async metrics writer instance for the performance decorator
_async_metrics_writer: Optional[AsyncMetricsWriter] = None


def get_metrics_writer() -> Optional[AsyncMetricsWriter]:
    """Get the global async metrics writer instance."""
    return _async_metrics_writer


def set_metrics_writer(writer: AsyncMetricsWriter) -> None:
    """Set the global async metrics writer for performance monitoring."""
    global _async_metrics_writer
    _async_metrics_writer = writer


def _record_metric(name: str, value: float, labels: Dict[str, str]):
    """Helper для запису метрики.

    Records metrics through the global AsyncMetricsWriter if configured,
    otherwise logs the metric for debugging purposes.
    """
    writer = get_metrics_writer()
    if writer is not None:
        writer.record(name, value, labels)
    else:
        # Fallback to logging when no writer is configured
        logger.debug(
            f"Metric recorded: {name}={value}",
            extra={"metric_name": name, "value": value, "labels": labels},
        )


# ============================================================================
# 6. Usage Examples
# ============================================================================


def example_streaming_replay():
    """Приклад використання streaming event replay."""
    replayer = StreamingEventReplayer(batch_size=1000)

    # Обробка подій батчами
    for batch in replayer.replay_events_streaming(
        aggregate_id="order-123", aggregate_type="Order"
    ):
        # Обробити батч
        for event in batch:
            process_event(event)

    # Статистика
    stats = replayer.get_stats()
    print(
        f"Processed {stats['total_events']} events in {stats['batches_processed']} batches"
    )


def example_adaptive_polling():
    """Приклад використання adaptive polling."""
    config = AdaptivePollingConfig(min_interval=0.1, max_interval=2.0)
    poller = AdaptivePoller(config)

    def check_for_orders():
        # Перевірити чи є нові ордери
        return has_pending_orders()

    # Main loop
    while True:
        has_activity = poller.poll(check_for_orders)
        if has_activity:
            process_orders()

        # Періодично виводити статистику
        if poller._stats["total_polls"] % 100 == 0:
            stats = poller.get_stats()
            print(f"Polling stats: {stats}")


def example_indicator_cache():
    """Приклад використання indicator cache."""
    cache = IndicatorCache(max_size=1000, ttl_seconds=60.0)

    def compute_expensive_indicator(data: np.ndarray) -> float:
        # Дорогі обчислення
        time.sleep(0.1)  # Симуляція
        return np.mean(data)

    # Використання кешу
    data = np.random.randn(10000)

    # Перший виклик - miss
    cache.get_or_compute(
        key="mean_indicator",
        data=data,
        compute_fn=lambda: compute_expensive_indicator(data),
    )

    # Другий виклик на тих самих даних - hit
    cache.get_or_compute(
        key="mean_indicator",
        data=data,
        compute_fn=lambda: compute_expensive_indicator(data),
    )

    # Статистика
    stats = cache.get_stats()
    print(f"Cache hit rate: {stats['hit_rate']:.2%}")


def example_async_metrics():
    """Приклад використання async metrics writer."""
    writer = AsyncMetricsWriter(batch_size=100, flush_interval=1.0)
    writer.start()

    try:
        # Запис метрик
        for i in range(1000):
            writer.record(
                "order_latency_ms", np.random.exponential(10.0), {"exchange": "binance"}
            )

        # Дочекатися flush
        time.sleep(2.0)

        # Статистика
        stats = writer.get_stats()
        print(f"Metrics: {stats}")

    finally:
        writer.stop()


# Dummy functions для прикладів
def process_event(event):
    pass


def has_pending_orders():
    return np.random.random() > 0.8


def process_orders():
    pass


if __name__ == "__main__":
    seed_numpy(SEED)
    print("=== TradePulse Optimization Examples ===\n")

    print("1. Streaming Event Replay")
    example_streaming_replay()
    print()

    print("2. Indicator Cache")
    example_indicator_cache()
    print()

    print("3. Async Metrics Writer")
    example_async_metrics()
    print()

    print("All examples completed!")
