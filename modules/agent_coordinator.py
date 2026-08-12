# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Agent Coordinator Module
========================

Модуль для координації між різними агентами в системі GeoSync,
включаючи TACL, ризик-менеджер, та торгові агенти.

Canonical contracts shipped in this revision
--------------------------------------------

1. UTC timestamp contract.
   ``utc_now()`` is the single source of timezone-aware ``datetime``
   values in this module. Every default factory and every live
   ``datetime`` assignment routes through it. Naive ``datetime.now()``
   calls are forbidden.

2. Entropy contract (Variant A — derived).
   ``SubjectiveState.entropy`` is derived from the ``coherence_score``
   as ``entropy = 1.0 - coherence_score`` inside
   ``_evaluate_subjective_state``. The equality check
   ``abs(entropy - (1.0 - coherence_score)) <= 1e-9`` in
   ``hidden_contradiction`` is therefore a **sanity guard** against
   externally constructed invalid states (tests, subclasses,
   deserialisation paths), not a diagnostic of production drift.
   In production the equality holds by construction.

3. Fail-closed halt contract.
   When ``_detect_hidden_contradiction`` returns ``True`` the
   coordinator enters a halted state. While halted, every mutating /
   executing operation raises ``ContradictionHaltError``.
   The only allowed operations are read-only introspection:

   * ``get_agent_info``
   * ``get_system_health``
   * ``get_coordination_summary``

   …and the explicit recovery call ``reset_halt`` which requires a
   human-supplied reason and an authorising identity. Both halt and
   reset events are appended to the ``_halt_history`` audit trail
   with a reproducible ``state_hash`` of the
   ``SubjectiveState`` payload.

4. State classification contract.
   ``SubjectiveState.state_class`` partitions every observable
   coordinator state into one of three disjoint classes:

   * ``healthy``          — fully coherent (coherence≈1, entropy≈0).
   * ``degraded_valid``   — coherent but below healthy perfection.
   * ``impossible``       — contradictory or out-of-range invariants.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


def utc_now() -> datetime:
    """Return a timezone-aware UTC ``datetime`` — the module's only clock.

    All timestamps produced inside this module (agent metadata, task
    lifecycle, decisions, synthesis cycle reports, halt/reset audit
    events) route through this function. The function is deliberately
    tiny and free of side effects so that callers can monkey-patch it
    in deterministic replay tests.
    """
    return datetime.now(timezone.utc)


class AgentType(str, Enum):
    """Типи агентів"""

    TRADING = "trading"
    RISK_MANAGER = "risk_manager"
    MARKET_ANALYZER = "market_analyzer"
    POSITION_SIZER = "position_sizer"
    THERMO_CONTROLLER = "thermo_controller"
    STRATEGY = "strategy"
    EXECUTION = "execution"
    MONITORING = "monitoring"


class AgentStatus(str, Enum):
    """Статус агента"""

    IDLE = "idle"
    ACTIVE = "active"
    BUSY = "busy"
    ERROR = "error"
    PAUSED = "paused"
    STOPPED = "stopped"


class Priority(int, Enum):
    """Пріоритет задачі"""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4
    EMERGENCY = 5


@dataclass
class AgentMetadata:
    """Метадані агента"""

    agent_id: str
    agent_type: AgentType
    name: str
    description: str
    status: AgentStatus = AgentStatus.IDLE
    priority: Priority = Priority.NORMAL
    capabilities: Set[str] = field(default_factory=set)
    dependencies: Set[str] = field(default_factory=set)
    registered_at: datetime = field(default_factory=utc_now)
    last_active: datetime = field(default_factory=utc_now)
    task_count: int = 0
    error_count: int = 0


@dataclass
class AgentTask:
    """Задача для агента"""

    task_id: str
    agent_id: str
    task_type: str
    priority: Priority
    payload: Dict[str, Any]
    callback: Optional[Callable[..., Any]] = None
    created_at: datetime = field(default_factory=utc_now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class CoordinationDecision:
    """Рішення координатора"""

    decision_type: str
    affected_agents: List[str]
    action: str
    reason: str
    priority: Priority
    timestamp: datetime = field(default_factory=utc_now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConflictDescriptor:
    """Опис ізольованого протиріччя в системі."""

    conflict_id: str
    agent_id: str
    conflict_type: str
    severity: Priority
    function_expression: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CoherenceAxes:
    """П'ять осей цілісності для суб'єктивного стану.

    Every axis is a score in ``[0.0, 1.0]`` where ``1.0`` is ideal.
    ``all_above(threshold)`` is used by ``SubjectiveState.truth``.
    """

    structural_integrity: float
    temporal_stability: float
    verification_honesty: float
    dependency_coherence: float
    recovery_readiness: float

    def all_above(self, threshold: float) -> bool:
        return (
            self.structural_integrity >= threshold
            and self.temporal_stability >= threshold
            and self.verification_honesty >= threshold
            and self.dependency_coherence >= threshold
            and self.recovery_readiness >= threshold
        )


@dataclass(frozen=True)
class SubjectiveState:
    """Структурований стан когерентності (замість неструктурованого Dict).

    Invariants (documented contract, enforced via
    :meth:`hidden_contradiction`):

    * ``0.0 <= coherence_score <= 1.0``
    * ``0.0 <= entropy <= 1.0``
    * ``abs(entropy - (1.0 - coherence_score)) <= 1e-9``
    * every axis in ``[0.0, 1.0]``

    Production invariant: ``_evaluate_subjective_state`` always sets
    ``entropy = 1.0 - coherence_score`` explicitly, so
    ``hidden_contradiction`` can only fire for externally constructed
    states (tests, subclasses, deserialisation). Such states are
    classified as ``state_class == "impossible"`` and trigger the
    fail-closed halt contract inside the coordinator.
    """

    axes: CoherenceAxes
    coherence_score: float
    entropy: float

    @property
    def truth(self) -> bool:
        """Canonical truth predicate.

        An artefact is *true* iff every axis is ≥ 0.8, the aggregate
        coherence is ≥ 0.8, entropy is ≤ 0.2, **and** the entropy
        equation is consistent with the coherence score.
        """
        return (
            self.axes.all_above(0.8)
            and self.coherence_score >= 0.8
            and self.entropy <= 0.2
            and abs(self.entropy - (1.0 - self.coherence_score)) <= 1e-9
        )

    @property
    def hidden_contradiction(self) -> bool:
        """Sanity guard against externally-constructed invalid states.

        Returns ``True`` iff the state violates at least one of the
        documented ``SubjectiveState`` invariants:

        * ``coherence_score`` outside ``[0.0, 1.0]``
        * ``entropy`` outside ``[0.0, 1.0]``
        * entropy is not the derived complement of coherence
          (``|entropy - (1 - coherence_score)| > 1e-9``)
        * any axis outside ``[0.0, 1.0]``

        In production this is a dead branch — the only way to reach it
        is to construct a ``SubjectiveState`` directly with inconsistent
        values. The sanity guard exists so that tests, subclasses,
        and deserialisation paths cannot smuggle impossible states
        past the halt gate.
        """
        if not (0.0 <= self.coherence_score <= 1.0):
            return True
        if not (0.0 <= self.entropy <= 1.0):
            return True
        if abs(self.entropy - (1.0 - self.coherence_score)) > 1e-9:
            return True

        return any(
            not (0.0 <= axis_value <= 1.0)
            for axis_value in (
                self.axes.structural_integrity,
                self.axes.temporal_stability,
                self.axes.verification_honesty,
                self.axes.dependency_coherence,
                self.axes.recovery_readiness,
            )
        )

    @property
    def state_class(self) -> str:
        """Canonical state classification — one of three disjoint classes.

        * ``impossible``     — violates a structural invariant
          (see :meth:`hidden_contradiction`).
        * ``healthy``        — fully coherent
          (coherence ≥ 1 − ε, entropy ≤ ε, and ``truth`` holds).
        * ``degraded_valid`` — coherent but below healthy perfection.
        """
        if self.hidden_contradiction:
            return "impossible"
        if self.coherence_score >= (1.0 - 1e-9) and self.entropy <= 1e-9 and self.truth:
            return "healthy"
        return "degraded_valid"


@dataclass
class SynthesisCycleReport:
    """Звіт детермінованого циклу синтезу."""

    cycle_id: str
    started_at: datetime
    completed_at: datetime
    decomposed_conflicts: List[ConflictDescriptor]
    synchronized_agents: List[str]
    verification_results: Dict[str, bool]
    recovered_agents: List[str]
    coherence_score: float
    subjective_state: SubjectiveState
    hidden_contradiction_detected: bool
    halted: bool


class ContradictionHaltError(RuntimeError):
    """Raised when a mutating operation is attempted while the
    coordinator is halted because of a hidden contradiction.

    See the module docstring (section *Fail-closed halt contract*)
    for the set of allowed read-only operations and the explicit
    recovery path via :meth:`AgentCoordinator.reset_halt`.
    """


# Mutating / executing operations blocked while halted.
# The set is part of the module contract and is also used by the test
# suite to prove that every mutating path is gated.
_HALT_GATED_OPS: frozenset[str] = frozenset(
    {
        "register_agent",
        "unregister_agent",
        "submit_task",
        "register_protocol",
        "register_validator",
        "process_tasks",
        "make_decision",
        "update_agent_status",
        "run_deterministic_synthesis_cycle",
    }
)

# Read-only operations that remain callable while halted.
_HALT_ALLOWED_OPS: frozenset[str] = frozenset(
    {
        "get_agent_info",
        "get_system_health",
        "get_coordination_summary",
        "reset_halt",
    }
)


class AgentCoordinator:
    """
    Координатор агентів

    Управляє взаємодією між різними агентами в системі,
    забезпечує узгоджену роботу та розв'язує конфлікти.
    """

    def __init__(
        self, max_concurrent_tasks: int = 10, enable_conflict_resolution: bool = True
    ) -> None:
        """
        Ініціалізація координатора

        Args:
            max_concurrent_tasks: Максимальна кількість одночасних задач
            enable_conflict_resolution: Увімкнути розв'язання конфліктів
        """
        self.max_concurrent_tasks = max_concurrent_tasks
        self.enable_conflict_resolution = enable_conflict_resolution

        # Реєстр агентів
        self._agents: Dict[str, AgentMetadata] = {}
        self._agent_handlers: Dict[str, Any] = {}

        # Черга задач
        self._task_queue: List[AgentTask] = []
        self._active_tasks: Dict[str, AgentTask] = {}
        self._completed_tasks: List[AgentTask] = []

        # Історія рішень
        self._decisions: List[CoordinationDecision] = []

        # Стан системи
        self._system_state: Dict[str, Any] = {}
        self._resource_allocation: Dict[str, float] = {}

        # Лічильники
        self._task_id_counter = 0
        self._synthesis_cycle_counter = 0

        # IoC рівень: протоколи та валідація
        self._protocol_handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self._validators: Dict[str, Callable[["AgentCoordinator"], bool]] = {}

        # Fail-closed halt state
        self._halted_due_to_contradiction: bool = False
        self._last_subjective_state: Optional[SubjectiveState] = None
        self._halted_state_snapshot: Optional[SubjectiveState] = None
        self._halt_history: List[Dict[str, Any]] = []

    def _assert_not_halted(self, operation: str) -> None:
        """System-wide fail-closed contract for mutating/execution operations."""
        if self._halted_due_to_contradiction:
            raise ContradictionHaltError(
                f"Operation '{operation}' is blocked: coordinator is halted "
                "due to hidden contradiction. Allowed operations: "
                + ", ".join(sorted(_HALT_ALLOWED_OPS))
                + "."
            )

    def register_agent(
        self,
        agent_id: str,
        agent_type: AgentType,
        name: str,
        description: str,
        handler: Any,
        capabilities: Optional[Set[str]] = None,
        dependencies: Optional[Set[str]] = None,
        priority: Priority = Priority.NORMAL,
    ) -> AgentMetadata:
        """
        Реєстрація агента в системі

        Args:
            agent_id: Унікальний ідентифікатор агента
            agent_type: Тип агента
            name: Ім'я агента
            description: Опис агента
            handler: Об'єкт-обробник агента
            capabilities: Можливості агента
            dependencies: Залежності від інших агентів
            priority: Пріоритет агента

        Returns:
            AgentMetadata
        """
        self._assert_not_halted("register_agent")
        if agent_id in self._agents:
            raise ValueError(f"Agent {agent_id} already registered")

        metadata = AgentMetadata(
            agent_id=agent_id,
            agent_type=agent_type,
            name=name,
            description=description,
            priority=priority,
            capabilities=capabilities or set(),
            dependencies=dependencies or set(),
        )

        self._agents[agent_id] = metadata
        self._agent_handlers[agent_id] = handler

        # Ініціалізація ресурсів
        self._resource_allocation[agent_id] = 0.0

        return metadata

    def unregister_agent(self, agent_id: str) -> None:
        """
        Видалення агента з реєстру

        Args:
            agent_id: Ідентифікатор агента
        """
        self._assert_not_halted("unregister_agent")
        if agent_id in self._agents:
            # Скасувати всі активні задачі агента
            tasks_to_remove = [
                task_id for task_id, task in self._active_tasks.items() if task.agent_id == agent_id
            ]
            for task_id in tasks_to_remove:
                del self._active_tasks[task_id]

            # Видалити з реєстру
            del self._agents[agent_id]
            del self._agent_handlers[agent_id]
            if agent_id in self._resource_allocation:
                del self._resource_allocation[agent_id]

    def submit_task(
        self,
        agent_id: str,
        task_type: str,
        payload: Dict[str, Any],
        priority: Priority = Priority.NORMAL,
        callback: Optional[Callable[..., Any]] = None,
    ) -> str:
        """
        Додавання задачі до черги

        Args:
            agent_id: Ідентифікатор агента
            task_type: Тип задачі
            payload: Дані задачі
            priority: Пріоритет
            callback: Callback функція

        Returns:
            Ідентифікатор задачі
        """
        self._assert_not_halted("submit_task")
        if agent_id not in self._agents:
            raise ValueError(f"Agent {agent_id} not registered")

        # Генерація task ID
        self._task_id_counter += 1
        task_id = f"task_{self._task_id_counter}_{agent_id}"

        task = AgentTask(
            task_id=task_id,
            agent_id=agent_id,
            task_type=task_type,
            priority=priority,
            payload=payload,
            callback=callback,
        )

        self._task_queue.append(task)

        # Сортуємо чергу по пріоритету
        self._task_queue.sort(key=lambda t: t.priority.value, reverse=True)

        return task_id

    def register_protocol(
        self, protocol_name: str, handler: Callable[[Dict[str, Any]], Any]
    ) -> None:
        """
        Реєструє універсальний протокол взаємодії (IoC).
        """
        self._assert_not_halted("register_protocol")
        self._protocol_handlers[protocol_name] = handler

    def register_validator(
        self, validator_name: str, validator: Callable[["AgentCoordinator"], bool]
    ) -> None:
        """
        Реєструє валідатор для рекурсивної верифікації системи.
        """
        self._assert_not_halted("register_validator")
        self._validators[validator_name] = validator

    def process_tasks(self) -> List[str]:
        """
        Обробка задач з черги

        Returns:
            Список ID оброблених задач
        """
        self._assert_not_halted("process_tasks")
        processed: List[str] = []

        # Обмежуємо кількість одночасних задач
        available_slots = self.max_concurrent_tasks - len(self._active_tasks)

        if available_slots <= 0:
            return processed

        # Беремо задачі з найвищим пріоритетом
        tasks_to_process = self._task_queue[:available_slots]
        self._task_queue = self._task_queue[available_slots:]

        for task in tasks_to_process:
            try:
                # Перевірка залежностей
                agent = self._agents[task.agent_id]
                if not self._check_dependencies(agent):
                    # Повертаємо в чергу
                    self._task_queue.append(task)
                    continue

                # Оновлюємо статус
                self._agents[task.agent_id].status = AgentStatus.BUSY
                self._agents[task.agent_id].last_active = utc_now()
                self._agents[task.agent_id].task_count += 1

                task.started_at = utc_now()
                self._active_tasks[task.task_id] = task

                # Виконуємо задачу (в реальності це буде async)
                handler = self._agent_handlers[task.agent_id]
                result = self._execute_task(handler, task)

                task.completed_at = utc_now()
                task.result = result

                # Викликаємо callback якщо є
                if task.callback:
                    task.callback(result)

                # Переміщуємо до completed
                del self._active_tasks[task.task_id]
                self._completed_tasks.append(task)

                # Оновлюємо статус агента
                self._agents[task.agent_id].status = AgentStatus.IDLE

                processed.append(task.task_id)

            except Exception as e:
                task.error = str(e)
                self._agents[task.agent_id].status = AgentStatus.ERROR
                self._agents[task.agent_id].error_count += 1

                # Переміщуємо до completed з помилкою
                if task.task_id in self._active_tasks:
                    del self._active_tasks[task.task_id]
                self._completed_tasks.append(task)

        return processed

    def _check_dependencies(self, agent: AgentMetadata) -> bool:
        """
        Перевірка залежностей агента

        Args:
            agent: Метадані агента

        Returns:
            True якщо всі залежності задоволені
        """
        for dep_id in agent.dependencies:
            if dep_id not in self._agents:
                return False
            dep_agent = self._agents[dep_id]
            if dep_agent.status == AgentStatus.ERROR:
                return False
        return True

    def _execute_task(self, handler: Any, task: AgentTask) -> Any:
        """
        Виконання задачі (заглушка для демонстрації)

        Args:
            handler: Обробник агента
            task: Задача

        Returns:
            Результат виконання
        """
        protocol = task.payload.get("protocol")
        if protocol and protocol in self._protocol_handlers:
            return self._protocol_handlers[protocol](task.payload)

        if hasattr(handler, "process") and callable(handler.process):
            return handler.process(task)

        # Базовий fallback для простих/тестових handler-об'єктів
        return {
            "status": "completed",
            "task_id": task.task_id,
            "task_type": task.task_type,
        }

    def make_decision(self, decision_type: str, context: Dict[str, Any]) -> CoordinationDecision:
        """
        Прийняття координаційного рішення

        Args:
            decision_type: Тип рішення
            context: Контекст для прийняття рішення

        Returns:
            CoordinationDecision
        """
        self._assert_not_halted("make_decision")
        affected_agents: List[str] = []
        action = "no_action"
        reason = "default"
        priority = Priority.NORMAL

        # Різні типи рішень
        if decision_type == "resource_allocation":
            # Розподіл ресурсів
            affected_agents = list(self._agents.keys())
            action = "rebalance_resources"
            reason = "resource optimization"
            self._rebalance_resources()

        elif decision_type == "conflict_resolution":
            # Розв'язання конфліктів
            conflicts = context.get("conflicts", [])
            affected_agents = [c["agent_id"] for c in conflicts]
            action = "resolve_conflicts"
            reason = f"detected {len(conflicts)} conflicts"
            priority = Priority.HIGH

        elif decision_type == "emergency_stop":
            # Аварійна зупинка
            affected_agents = list(self._agents.keys())
            action = "stop_all"
            reason = context.get("reason", "emergency")
            priority = Priority.EMERGENCY
            self._emergency_stop()

        elif decision_type == "agent_coordination":
            # Координація агентів
            agents = context.get("agents", [])
            affected_agents = agents
            action = "synchronize"
            reason = "coordination required"

        decision = CoordinationDecision(
            decision_type=decision_type,
            affected_agents=affected_agents,
            action=action,
            reason=reason,
            priority=priority,
            metadata=context,
        )

        self._decisions.append(decision)
        return decision

    def _rebalance_resources(self) -> None:
        """Перерозподіл ресурсів між агентами"""
        total_priority = sum(agent.priority.value for agent in self._agents.values())

        if total_priority == 0:
            return

        # Розподіляємо ресурси пропорційно пріоритету
        for agent_id, agent in self._agents.items():
            allocation = agent.priority.value / total_priority
            self._resource_allocation[agent_id] = allocation

    def _emergency_stop(self) -> None:
        """Аварійна зупинка всіх агентів"""
        for agent_id in self._agents:
            self._agents[agent_id].status = AgentStatus.STOPPED

        # Очищаємо черги
        self._task_queue.clear()
        self._active_tasks.clear()

    def update_agent_status(self, agent_id: str, status: AgentStatus) -> None:
        """
        Оновлення статусу агента

        Args:
            agent_id: Ідентифікатор агента
            status: Новий статус
        """
        self._assert_not_halted("update_agent_status")
        if agent_id in self._agents:
            self._agents[agent_id].status = status
            self._agents[agent_id].last_active = utc_now()

    def get_agent_info(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Отримання інформації про агента (read-only — дозволено під час halt).

        Args:
            agent_id: Ідентифікатор агента

        Returns:
            Словник з інформацією
        """
        if agent_id not in self._agents:
            return None

        agent = self._agents[agent_id]
        return {
            "agent_id": agent.agent_id,
            "type": agent.agent_type.value,
            "name": agent.name,
            "status": agent.status.value,
            "priority": agent.priority.value,
            "capabilities": list(agent.capabilities),
            "dependencies": list(agent.dependencies),
            "task_count": agent.task_count,
            "error_count": agent.error_count,
            "resource_allocation": f"{self._resource_allocation.get(agent_id, 0.0):.2%}",
            "last_active": agent.last_active.isoformat(),
        }

    def get_system_health(self) -> Dict[str, Any]:
        """
        Отримання стану системи (read-only — дозволено під час halt).

        Returns:
            Словник зі станом здоров'я системи
        """
        total_agents = len(self._agents)
        active_agents = sum(
            1
            for a in self._agents.values()
            if a.status == AgentStatus.ACTIVE or a.status == AgentStatus.BUSY
        )
        error_agents = sum(1 for a in self._agents.values() if a.status == AgentStatus.ERROR)

        # Обчислюємо health score
        health_score = 100.0
        if total_agents > 0:
            health_score -= (error_agents / total_agents) * 50
            health_score -= (len(self._task_queue) / max(self.max_concurrent_tasks, 1)) * 25

        health_score = max(0.0, min(100.0, health_score))

        return {
            "health_score": f"{health_score:.1f}",
            "total_agents": total_agents,
            "active_agents": active_agents,
            "idle_agents": sum(1 for a in self._agents.values() if a.status == AgentStatus.IDLE),
            "error_agents": error_agents,
            "queued_tasks": len(self._task_queue),
            "active_tasks": len(self._active_tasks),
            "completed_tasks": len(self._completed_tasks),
            "recent_decisions": len(self._decisions[-10:]),
        }

    def get_coordination_summary(self) -> Dict[str, Any]:
        """
        Отримання загального звіту координації (read-only — дозволено під час halt).

        Returns:
            Словник зі звітом
        """
        return {
            "registered_agents": len(self._agents),
            "agent_types": list(set(a.agent_type.value for a in self._agents.values())),
            "total_tasks_processed": sum(a.task_count for a in self._agents.values()),
            "total_errors": sum(a.error_count for a in self._agents.values()),
            "queue_size": len(self._task_queue),
            "active_tasks": len(self._active_tasks),
            "decisions_made": len(self._decisions),
            "system_health": self.get_system_health(),
            "halted": self._halted_due_to_contradiction,
        }

    def run_deterministic_synthesis_cycle(self) -> SynthesisCycleReport:
        """
        Детермінований цикл синтезу:

        1) Декомпозиція ентропії.
        2) Алгоритмічна синхронізація.
        3) Рекурсивна верифікація та самовідновлення.
        4) Побудова канонічного ``SubjectiveState`` і перевірка
           ``hidden_contradiction`` як fail-closed gate.
        """
        self._assert_not_halted("run_deterministic_synthesis_cycle")
        started_at = utc_now()
        self._synthesis_cycle_counter += 1
        cycle_id = f"cycle_{self._synthesis_cycle_counter}"

        conflicts = self._decompose_entropy()
        synchronized_agents = self._synchronize_dependencies()
        verification = self._recursive_verify()
        recovered_agents = self._recover_from_conflicts(conflicts)
        coherence_score = self._calculate_coherence_score(conflicts, verification)
        subjective_state = self._evaluate_subjective_state(
            conflicts=conflicts,
            synchronized_agents=synchronized_agents,
            verification_results=verification,
            recovered_agents=recovered_agents,
            coherence_score=coherence_score,
        )
        hidden_contradiction_detected = self._detect_hidden_contradiction(
            subjective_state=subjective_state
        )
        if hidden_contradiction_detected:
            self._halted_due_to_contradiction = True
            self._halted_state_snapshot = subjective_state
            self._record_halt_event(
                cycle_id=cycle_id,
                reason="hidden_contradiction_detected",
                subjective_state=subjective_state,
            )

        completed_at = utc_now()
        return SynthesisCycleReport(
            cycle_id=cycle_id,
            started_at=started_at,
            completed_at=completed_at,
            decomposed_conflicts=conflicts,
            synchronized_agents=synchronized_agents,
            verification_results=verification,
            recovered_agents=recovered_agents,
            coherence_score=coherence_score,
            subjective_state=subjective_state,
            hidden_contradiction_detected=hidden_contradiction_detected,
            halted=self._halted_due_to_contradiction,
        )

    @staticmethod
    def _state_payload_hash(payload: Optional[Dict[str, Any]]) -> Optional[str]:
        """Deterministic sha256 of an ``asdict``-ified ``SubjectiveState``.

        Returns ``None`` when the payload is ``None`` so that reset
        events that had no snapshot still produce a well-formed audit
        record.
        """
        if payload is None:
            return None
        serialised = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(serialised).hexdigest()

    def _record_halt_event(
        self, cycle_id: str, reason: str, subjective_state: SubjectiveState
    ) -> None:
        state_payload = asdict(subjective_state)
        state_hash = self._state_payload_hash(state_payload)
        self._halt_history.append(
            {
                "event_type": "halt",
                "halt_at": utc_now(),
                "reason": reason,
                "subjective_state": state_payload,
                "state_hash": state_hash,
                "cycle_id": cycle_id,
            }
        )

    def _decompose_entropy(self) -> List[ConflictDescriptor]:
        """Ізолює та формалізує точки конфлікту як функції."""
        conflicts: List[ConflictDescriptor] = []

        for agent_id, agent in self._agents.items():
            for dep_id in agent.dependencies:
                if dep_id not in self._agents:
                    conflicts.append(
                        ConflictDescriptor(
                            conflict_id=f"missing_dep:{agent_id}:{dep_id}",
                            agent_id=agent_id,
                            conflict_type="missing_dependency",
                            severity=Priority.HIGH,
                            function_expression=(f"f_missing_dep({agent_id},{dep_id})=1"),
                            details={"dependency": dep_id},
                        )
                    )
                    continue

                dep_agent = self._agents[dep_id]
                if dep_agent.status == AgentStatus.ERROR:
                    conflicts.append(
                        ConflictDescriptor(
                            conflict_id=f"error_dep:{agent_id}:{dep_id}",
                            agent_id=agent_id,
                            conflict_type="error_dependency",
                            severity=Priority.CRITICAL,
                            function_expression=f"f_error_dep({agent_id},{dep_id})=1",
                            details={"dependency": dep_id},
                        )
                    )

        if self.max_concurrent_tasks > 0:
            queue_pressure = len(self._task_queue) / self.max_concurrent_tasks
            if queue_pressure > 1.0:
                conflicts.append(
                    ConflictDescriptor(
                        conflict_id="queue_pressure",
                        agent_id="system",
                        conflict_type="throughput_pressure",
                        severity=Priority.HIGH,
                        function_expression=("f_queue=max(0, queued/max_concurrent_tasks - 1)"),
                        details={"queue_pressure": queue_pressure},
                    )
                )
        return conflicts

    def _synchronize_dependencies(self) -> List[str]:
        """Синхронізує залежності та виконує перерозподіл ресурсів."""
        synchronized: List[str] = []
        self._rebalance_resources()

        for agent_id, agent in self._agents.items():
            if self._check_dependencies(agent) and agent.status in {
                AgentStatus.IDLE,
                AgentStatus.ACTIVE,
            }:
                synchronized.append(agent_id)
        return synchronized

    def _recursive_verify(self) -> Dict[str, bool]:
        """Запускає рекурсивні валідатори; за відсутності - вбудовані перевірки."""
        results: Dict[str, bool] = {}

        if not self._validators:
            results["dependency_integrity"] = all(
                self._check_dependencies(agent) for agent in self._agents.values()
            )
            results["health_above_floor"] = float(self.get_system_health()["health_score"]) >= 50.0
            return results

        for validator_name, validator in self._validators.items():
            try:
                results[validator_name] = bool(validator(self))
            except Exception:
                results[validator_name] = False
        return results

    def _recover_from_conflicts(self, conflicts: List[ConflictDescriptor]) -> List[str]:
        """Самовідновлення: переводить конфліктні агенти в PAUSED
        для контрольованого деградування."""
        recovered: List[str] = []
        conflicted_agents = {
            c.agent_id for c in conflicts if c.agent_id != "system" and c.agent_id in self._agents
        }

        for agent_id in conflicted_agents:
            agent = self._agents[agent_id]
            if agent.status == AgentStatus.ERROR:
                agent.status = AgentStatus.PAUSED
                recovered.append(agent_id)
        return recovered

    def _calculate_coherence_score(
        self,
        conflicts: List[ConflictDescriptor],
        verification_results: Dict[str, bool],
    ) -> float:
        """Оцінює когерентність системи в діапазоні [0, 1]."""
        base = 1.0
        conflict_penalty = min(len(conflicts) * 0.15, 0.7)
        failed_verifications = sum(not ok for ok in verification_results.values())
        verification_penalty = min(failed_verifications * 0.2, 0.6)

        score = base - conflict_penalty - verification_penalty
        return max(0.0, min(1.0, score))

    def _evaluate_subjective_state(
        self,
        conflicts: List[ConflictDescriptor],
        synchronized_agents: List[str],
        verification_results: Dict[str, bool],
        recovered_agents: List[str],
        coherence_score: float,
    ) -> SubjectiveState:
        """
        Оцінює "цифровий суб'єктивізм" по п'яти осях цілісності.

        Осі:
        1) ``structural_integrity``  — 1 − conflict density per agent.
        2) ``temporal_stability``    — weighted mix of coherence and
           synchronisation ratio.
        3) ``verification_honesty``  — ratio of passing validators.
        4) ``dependency_coherence``  — 1 − dep-related-conflict density.
        5) ``recovery_readiness``    — penalised by recent recoveries.

        Production contract (Variant A): ``entropy`` is set to
        ``1.0 - coherence_score`` by construction. This keeps the
        sanity-guard in :meth:`SubjectiveState.hidden_contradiction`
        a **dead branch** in production; it only fires for externally
        constructed states.
        """
        total_agents = max(len(self._agents), 1)
        conflicts_count = len(conflicts)
        active_conflicts_ratio = min(conflicts_count / total_agents, 1.0)
        synchronized_ratio = min(len(synchronized_agents) / total_agents, 1.0)

        structural_integrity = max(0.0, 1.0 - active_conflicts_ratio)
        temporal_stability = max(0.0, min(1.0, 0.6 * coherence_score + 0.4 * synchronized_ratio))

        verification_total = max(len(verification_results), 1)
        verification_pass_ratio = (
            sum(1 for ok in verification_results.values() if ok) / verification_total
        )
        verification_honesty = verification_pass_ratio

        dependency_coherence = max(
            0.0,
            1.0
            - min(
                sum(
                    1
                    for c in conflicts
                    if c.conflict_type in {"missing_dependency", "error_dependency"}
                )
                / total_agents,
                1.0,
            ),
        )
        recovery_readiness = max(
            0.0,
            min(1.0, 1.0 - (len(recovered_agents) / total_agents) * 0.5),
        )

        axes = CoherenceAxes(
            structural_integrity=structural_integrity,
            temporal_stability=temporal_stability,
            verification_honesty=verification_honesty,
            dependency_coherence=dependency_coherence,
            recovery_readiness=recovery_readiness,
        )
        entropy = 1.0 - coherence_score
        state = SubjectiveState(axes=axes, coherence_score=coherence_score, entropy=entropy)
        self._last_subjective_state = state
        return state

    def _detect_hidden_contradiction(self, subjective_state: SubjectiveState) -> bool:
        """``HiddenContradiction(S)``: виявляє внутрішню брехню між
        ``truth`` і фактичною когерентністю.

        In production this is a dead branch (see the module docstring,
        *Entropy contract (Variant A — derived)*). The coordinator
        still routes every synthesis cycle through it so that any
        future regression that breaks the entropy derivation trips
        the halt gate immediately rather than silently corrupting
        downstream decisions.
        """
        return subjective_state.hidden_contradiction

    def reset_halt(self, reason: str, authorized_by: str) -> None:
        """Явне розблокування halt-стану через авторизовану дію.

        Always appends a ``reset`` event to ``_halt_history`` when the
        coordinator is halted, including an ``authorized_by`` identity
        and the sha256 of the snapshot that the reset supersedes.
        When called without an active halt, the method is a no-op and
        the audit trail is not mutated.
        """
        if not self._halted_due_to_contradiction:
            return
        state_payload = (
            asdict(self._halted_state_snapshot) if self._halted_state_snapshot is not None else None
        )
        state_hash = self._state_payload_hash(state_payload)
        self._halt_history.append(
            {
                "event_type": "reset",
                "reset_at": utc_now(),
                "reason": reason,
                "authorized_by": authorized_by,
                "subjective_state": state_payload,
                "state_hash": state_hash,
                "cycle_id": None,
            }
        )
        self._halted_due_to_contradiction = False
        self._halted_state_snapshot = None
