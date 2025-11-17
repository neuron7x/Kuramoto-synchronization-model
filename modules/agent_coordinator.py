"""
Agent Coordinator Module

Модуль для координації між різними агентами в системі TradePulse,
включаючи TACL, ризик-менеджер, та торгові агенти.

Features:
- Централізована координація агентів
- Розподіл ресурсів між агентами
- Синхронізація станів
- Вирішення конфліктів
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


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
    registered_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
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
    callback: Optional[Callable] = None
    created_at: datetime = field(default_factory=datetime.now)
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
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentCoordinator:
    """
    Координатор агентів

    Управляє взаємодією між різними агентами в системі,
    забезпечує узгоджену роботу та розв'язує конфлікти.
    """

    def __init__(
        self, max_concurrent_tasks: int = 10, enable_conflict_resolution: bool = True
    ):
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
        if agent_id in self._agents:
            # Скасувати всі активні задачі агента
            tasks_to_remove = [
                task_id
                for task_id, task in self._active_tasks.items()
                if task.agent_id == agent_id
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
        callback: Optional[Callable] = None,
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

    def process_tasks(self) -> List[str]:
        """
        Обробка задач з черги

        Returns:
            Список ID оброблених задач
        """
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
                self._agents[task.agent_id].last_active = datetime.now()
                self._agents[task.agent_id].task_count += 1

                task.started_at = datetime.now()
                self._active_tasks[task.task_id] = task

                # Виконуємо задачу (в реальності це буде async)
                handler = self._agent_handlers[task.agent_id]
                result = self._execute_task(handler, task)

                task.completed_at = datetime.now()
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
        # В реальній імплементації тут буде виклик методів handler
        # На основі task_type та payload
        return {"status": "completed", "task_id": task.task_id}

    def make_decision(
        self, decision_type: str, context: Dict[str, Any]
    ) -> CoordinationDecision:
        """
        Прийняття координаційного рішення

        Args:
            decision_type: Тип рішення
            context: Контекст для прийняття рішення

        Returns:
            CoordinationDecision
        """
        affected_agents = []
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
        if agent_id in self._agents:
            self._agents[agent_id].status = status
            self._agents[agent_id].last_active = datetime.now()

    def get_agent_info(self, agent_id: str) -> Optional[Dict]:
        """
        Отримання інформації про агента

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

    def get_system_health(self) -> Dict:
        """
        Отримання стану системи

        Returns:
            Словник зі станом здоров'я системи
        """
        total_agents = len(self._agents)
        active_agents = sum(
            1
            for a in self._agents.values()
            if a.status == AgentStatus.ACTIVE or a.status == AgentStatus.BUSY
        )
        error_agents = sum(
            1 for a in self._agents.values() if a.status == AgentStatus.ERROR
        )

        # Обчислюємо health score
        health_score = 100.0
        if total_agents > 0:
            health_score -= (error_agents / total_agents) * 50
            health_score -= (
                len(self._task_queue) / max(self.max_concurrent_tasks, 1)
            ) * 25

        health_score = max(0.0, min(100.0, health_score))

        return {
            "health_score": f"{health_score:.1f}",
            "total_agents": total_agents,
            "active_agents": active_agents,
            "idle_agents": sum(
                1 for a in self._agents.values() if a.status == AgentStatus.IDLE
            ),
            "error_agents": error_agents,
            "queued_tasks": len(self._task_queue),
            "active_tasks": len(self._active_tasks),
            "completed_tasks": len(self._completed_tasks),
            "recent_decisions": len(self._decisions[-10:]),
        }

    def get_coordination_summary(self) -> Dict:
        """
        Отримання загального звіту координації

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
        }
