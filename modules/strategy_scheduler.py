# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Strategy Scheduler Module

Модуль для планування та управління виконанням торгових стратегій.

Features:
- Планування запуску стратегій
- Управління життєвим циклом
- Залежності між стратегіями
- Моніторинг виконання
"""

import heapq
import threading
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


class ScheduleType(str, Enum):
    """Тип розкладу"""

    ONCE = "once"
    INTERVAL = "interval"
    DAILY = "daily"
    WEEKLY = "weekly"
    CRON = "cron"
    ON_EVENT = "on_event"


class TaskStatus(str, Enum):
    """Статус задачі"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class TaskPriority(int, Enum):
    """Пріоритет задачі"""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class ScheduleConfig:
    """Конфігурація розкладу"""

    schedule_type: ScheduleType
    interval_seconds: Optional[float] = None
    run_at_time: Optional[time] = None
    days_of_week: Set[int] = field(default_factory=lambda: {0, 1, 2, 3, 4})  # Mon-Fri
    cron_expression: Optional[str] = None
    event_trigger: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


@dataclass
class ScheduledTask:
    """Запланована задача"""

    task_id: str
    name: str
    strategy_name: str
    handler: Callable[..., Any]
    schedule: ScheduleConfig
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    dependencies: Set[str] = field(default_factory=set)
    next_run: Optional[datetime] = None
    last_run: Optional[datetime] = None
    run_count: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    timeout_seconds: float = 300.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other: "ScheduledTask") -> bool:
        """Порівняння для heapq"""
        if self.next_run is None:
            return False
        if other.next_run is None:
            return True
        if self.next_run == other.next_run:
            return self.priority.value > other.priority.value
        return self.next_run < other.next_run


@dataclass
class TaskExecution:
    """Виконання задачі"""

    execution_id: str
    task_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: TaskStatus = TaskStatus.RUNNING
    result: Optional[Any] = None
    error: Optional[str] = None
    duration_seconds: float = 0.0


@dataclass
class SchedulerStats:
    """Статистика планувальника"""

    total_tasks: int = 0
    running_tasks: int = 0
    pending_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0


class StrategyScheduler:
    """
    Планувальник стратегій

    Управляє розкладом виконання та життєвим циклом стратегій.
    """

    def __init__(
        self,
        max_concurrent_tasks: int = 5,
        default_timeout: float = 300.0,
        enable_dependency_check: bool = True,
    ):
        """
        Ініціалізація планувальника

        Args:
            max_concurrent_tasks: Максимальна кількість одночасних задач
            default_timeout: Таймаут за замовчуванням
            enable_dependency_check: Увімкнути перевірку залежностей
        """
        self.max_concurrent_tasks = max_concurrent_tasks
        self.default_timeout = default_timeout
        self.enable_dependency_check = enable_dependency_check

        # Зареєстровані задачі
        self._tasks: Dict[str, ScheduledTask] = {}

        # Черга виконання
        self._queue: List[ScheduledTask] = []

        # Активні виконання
        self._running: Dict[str, TaskExecution] = {}

        # Історія виконань
        self._execution_history: List[TaskExecution] = []

        # Обробники подій
        self._event_handlers: Dict[str, List[str]] = {}

        # Стан
        self._is_running = False
        self._lock = threading.Lock()
        self._task_counter = 0
        self._execution_counter = 0

    def schedule(
        self,
        name: str,
        strategy_name: str,
        handler: Callable[..., Any],
        schedule: ScheduleConfig,
        priority: TaskPriority = TaskPriority.NORMAL,
        dependencies: Optional[Set[str]] = None,
        timeout_seconds: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Планування задачі

        Args:
            name: Назва задачі
            strategy_name: Назва стратегії
            handler: Обробник задачі
            schedule: Конфігурація розкладу
            priority: Пріоритет
            dependencies: Залежності (ID інших задач)
            timeout_seconds: Таймаут
            metadata: Метадані

        Returns:
            ID задачі
        """
        with self._lock:
            self._task_counter += 1
            task_id = f"task_{self._task_counter}_{strategy_name}"

            task = ScheduledTask(
                task_id=task_id,
                name=name,
                strategy_name=strategy_name,
                handler=handler,
                schedule=schedule,
                priority=priority,
                dependencies=dependencies or set(),
                timeout_seconds=timeout_seconds or self.default_timeout,
                metadata=metadata or {},
            )

            # Розрахунок наступного запуску
            task.next_run = self._calculate_next_run(schedule)

            self._tasks[task_id] = task

            # Додавання до черги
            if task.next_run:
                heapq.heappush(self._queue, task)

            # Реєстрація обробника подій
            if schedule.schedule_type == ScheduleType.ON_EVENT and schedule.event_trigger:
                if schedule.event_trigger not in self._event_handlers:
                    self._event_handlers[schedule.event_trigger] = []
                self._event_handlers[schedule.event_trigger].append(task_id)

            return task_id

    def unschedule(self, task_id: str) -> bool:
        """
        Видалення задачі з розкладу

        Args:
            task_id: ID задачі

        Returns:
            True якщо успішно
        """
        with self._lock:
            if task_id not in self._tasks:
                return False

            task = self._tasks[task_id]
            task.status = TaskStatus.CANCELLED

            # Видалення з обробників подій
            if task.schedule.schedule_type == ScheduleType.ON_EVENT and task.schedule.event_trigger:
                handlers = self._event_handlers.get(task.schedule.event_trigger, [])
                if task_id in handlers:
                    handlers.remove(task_id)

            del self._tasks[task_id]
            return True

    def pause(self, task_id: str) -> bool:
        """
        Призупинення задачі

        Args:
            task_id: ID задачі

        Returns:
            True якщо успішно
        """
        if task_id not in self._tasks:
            return False

        self._tasks[task_id].status = TaskStatus.PAUSED
        return True

    def resume(self, task_id: str) -> bool:
        """
        Відновлення задачі

        Args:
            task_id: ID задачі

        Returns:
            True якщо успішно
        """
        if task_id not in self._tasks:
            return False

        task = self._tasks[task_id]
        if task.status != TaskStatus.PAUSED:
            return False

        task.status = TaskStatus.PENDING
        task.next_run = self._calculate_next_run(task.schedule)

        if task.next_run:
            with self._lock:
                heapq.heappush(self._queue, task)

        return True

    def trigger_event(self, event_name: str, payload: Optional[Dict[str, Any]] = None) -> int:
        """
        Тригер події

        Args:
            event_name: Назва події
            payload: Дані події

        Returns:
            Кількість запущених задач
        """
        triggered_count = 0
        task_ids = self._event_handlers.get(event_name, [])

        for task_id in task_ids:
            if task_id in self._tasks:
                task = self._tasks[task_id]
                if task.status == TaskStatus.PENDING:
                    if payload:
                        task.metadata["event_payload"] = payload
                    self._execute_task(task)
                    triggered_count += 1

        return triggered_count

    def run_now(self, task_id: str) -> Optional[TaskExecution]:
        """
        Негайний запуск задачі

        Args:
            task_id: ID задачі

        Returns:
            Виконання або None
        """
        if task_id not in self._tasks:
            return None

        task = self._tasks[task_id]
        return self._execute_task(task)

    def tick(self) -> List[TaskExecution]:
        """
        Обробка черги (виклик з основного циклу)

        Returns:
            Список виконань
        """
        executions = []
        now = datetime.now()

        with self._lock:
            # Перевірка задач для запуску
            while self._queue and len(self._running) < self.max_concurrent_tasks:
                # Peek at the next task
                if not self._queue:
                    break

                task = self._queue[0]

                # Перевірка часу
                if task.next_run is None or task.next_run > now:
                    break

                # Видалення з черги
                heapq.heappop(self._queue)

                # Перевірка статусу
                if task.status != TaskStatus.PENDING:
                    continue

                # Перевірка залежностей
                if self.enable_dependency_check and not self._check_dependencies(task):
                    # Повернення в чергу з затримкою
                    task.next_run = now + timedelta(seconds=5)
                    heapq.heappush(self._queue, task)
                    continue

                # Виконання
                execution = self._execute_task(task)
                if execution:
                    executions.append(execution)

        return executions

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """
        Отримання задачі

        Args:
            task_id: ID задачі

        Returns:
            Задача або None
        """
        return self._tasks.get(task_id)

    def get_tasks(
        self,
        strategy_name: Optional[str] = None,
        status: Optional[TaskStatus] = None,
    ) -> List[ScheduledTask]:
        """
        Отримання списку задач

        Args:
            strategy_name: Фільтр за стратегією
            status: Фільтр за статусом

        Returns:
            Список задач
        """
        tasks = list(self._tasks.values())

        if strategy_name:
            tasks = [t for t in tasks if t.strategy_name == strategy_name]
        if status:
            tasks = [t for t in tasks if t.status == status]

        return sorted(tasks, key=lambda t: t.next_run or datetime.max)

    def get_execution_history(
        self,
        task_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[TaskExecution]:
        """
        Отримання історії виконань

        Args:
            task_id: Фільтр за ID задачі
            limit: Максимальна кількість

        Returns:
            Список виконань
        """
        history = self._execution_history.copy()

        if task_id:
            history = [e for e in history if e.task_id == task_id]

        history = sorted(history, key=lambda e: e.started_at, reverse=True)
        return history[:limit]

    def get_stats(self) -> SchedulerStats:
        """
        Отримання статистики

        Returns:
            Статистика планувальника
        """
        stats = SchedulerStats()

        stats.total_tasks = len(self._tasks)
        stats.running_tasks = len(self._running)

        for task in self._tasks.values():
            if task.status == TaskStatus.PENDING:
                stats.pending_tasks += 1
            elif task.status == TaskStatus.COMPLETED:
                stats.completed_tasks += 1
            elif task.status == TaskStatus.FAILED:
                stats.failed_tasks += 1

        stats.total_executions = len(self._execution_history)
        stats.successful_executions = len(
            [e for e in self._execution_history if e.status == TaskStatus.COMPLETED]
        )
        stats.failed_executions = len(
            [e for e in self._execution_history if e.status == TaskStatus.FAILED]
        )

        return stats

    def _execute_task(self, task: ScheduledTask) -> Optional[TaskExecution]:
        """Виконання задачі"""
        self._execution_counter += 1
        execution_id = f"exec_{self._execution_counter}"

        execution = TaskExecution(
            execution_id=execution_id,
            task_id=task.task_id,
            started_at=datetime.now(),
        )

        self._running[task.task_id] = execution
        task.status = TaskStatus.RUNNING
        task.last_run = datetime.now()
        task.run_count += 1

        try:
            # Виконання обробника
            result = task.handler()
            execution.result = result
            execution.status = TaskStatus.COMPLETED
            task.status = TaskStatus.PENDING

        except Exception as e:
            execution.error = str(e)
            execution.status = TaskStatus.FAILED
            task.status = TaskStatus.FAILED
            task.error_count += 1
            task.last_error = str(e)

        finally:
            execution.completed_at = datetime.now()
            execution.duration_seconds = (
                execution.completed_at - execution.started_at
            ).total_seconds()

            # Видалення з running
            if task.task_id in self._running:
                del self._running[task.task_id]

            # Додавання до історії
            self._execution_history.append(execution)

            # Обмеження розміру історії
            max_history = 1000
            if len(self._execution_history) > max_history:
                self._execution_history = self._execution_history[-max_history:]

            # Планування наступного запуску
            if (
                task.schedule.schedule_type != ScheduleType.ONCE
                and task.status != TaskStatus.FAILED
            ):
                task.next_run = self._calculate_next_run(task.schedule)
                if task.next_run:
                    with self._lock:
                        heapq.heappush(self._queue, task)

        return execution

    def _calculate_next_run(self, schedule: ScheduleConfig) -> Optional[datetime]:
        """Розрахунок наступного часу запуску"""
        now = datetime.now()

        # Перевірка часових обмежень
        if schedule.start_time and now < schedule.start_time:
            return schedule.start_time

        if schedule.end_time and now > schedule.end_time:
            return None

        if schedule.schedule_type == ScheduleType.ONCE:
            if schedule.start_time and schedule.start_time > now:
                return schedule.start_time
            return now

        elif schedule.schedule_type == ScheduleType.INTERVAL:
            if schedule.interval_seconds:
                return now + timedelta(seconds=schedule.interval_seconds)
            return None

        elif schedule.schedule_type == ScheduleType.DAILY:
            if schedule.run_at_time:
                next_run = datetime.combine(now.date(), schedule.run_at_time)
                if next_run <= now:
                    next_run += timedelta(days=1)
                return next_run
            return None

        elif schedule.schedule_type == ScheduleType.WEEKLY:
            if schedule.run_at_time and schedule.days_of_week:
                # Знаходимо наступний день тижня
                for days_ahead in range(7):
                    next_day = now.date() + timedelta(days=days_ahead)
                    if next_day.weekday() in schedule.days_of_week:
                        next_run = datetime.combine(next_day, schedule.run_at_time)
                        if next_run > now:
                            return next_run
                # Якщо не знайшли - наступний тиждень
                return now + timedelta(days=7)
            return None

        elif schedule.schedule_type == ScheduleType.ON_EVENT:
            # Для event-based задач немає фіксованого часу
            return None

        return None

    def _check_dependencies(self, task: ScheduledTask) -> bool:
        """Перевірка залежностей задачі"""
        for dep_id in task.dependencies:
            if dep_id not in self._tasks:
                continue

            dep_task = self._tasks[dep_id]

            # Залежність повинна бути виконана успішно
            if dep_task.status == TaskStatus.RUNNING:
                return False

            if dep_task.status == TaskStatus.FAILED:
                return False

            # Перевірка чи залежність виконувалась хоча б раз
            if dep_task.run_count == 0:
                return False

        return True

    def get_summary(self) -> Dict:
        """
        Отримання саммарі

        Returns:
            Словник зі статистикою
        """
        stats = self.get_stats()

        next_runs = []
        for task in self._tasks.values():
            if task.next_run and task.status == TaskStatus.PENDING:
                next_runs.append(
                    {
                        "task_id": task.task_id,
                        "name": task.name,
                        "strategy": task.strategy_name,
                        "next_run": task.next_run.isoformat(),
                    }
                )

        next_runs = sorted(next_runs, key=lambda x: x["next_run"])[:5]

        return {
            "total_tasks": stats.total_tasks,
            "running_tasks": stats.running_tasks,
            "pending_tasks": stats.pending_tasks,
            "completed_tasks": stats.completed_tasks,
            "failed_tasks": stats.failed_tasks,
            "total_executions": stats.total_executions,
            "success_rate": (
                f"{stats.successful_executions / stats.total_executions:.1%}"
                if stats.total_executions > 0
                else "N/A"
            ),
            "upcoming_tasks": next_runs,
            "event_handlers": {
                event: len(handlers) for event, handlers in self._event_handlers.items()
            },
        }
