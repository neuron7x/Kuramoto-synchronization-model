"""System Architecture Principles for TradePulse.

This module defines the seven core architectural principles that govern the design
and implementation of the TradePulse trading system. Each principle is implemented
as a concrete class with validation, configuration, and runtime behavior.

АРХІТЕКТУРНІ ПРИНЦИПИ СИСТЕМИ (Ukrainian):
1. Нейроорієнтована (Neuro-oriented) - Нейронаукові обчислювальні моделі
2. Модульна (Modular) - Незалежні, слабко пов'язані компоненти
3. Рольова (Role-based) - Чітке розділення відповідальностей та контроль доступу
4. Інтегративна (Integrative) - Безшовна інтеграція компонентів та потоків даних
5. Відтворювана (Reproducible) - Детерміністична поведінка та аудит стану
6. Контрольована (Controllable) - Повний операційний контроль та втручання
7. Автономна (Autonomous) - Саморегулювання та адаптивна поведінка
"""

from __future__ import annotations

import hashlib
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import (
    Any,
    Dict,
    FrozenSet,
    List,
    Literal,
    Mapping,
    Optional,
    Set,
    Tuple,
)

__all__ = [
    "ArchitecturePrinciple",
    "NeuroOrientedPrinciple",
    "ModularPrinciple",
    "RoleBasedPrinciple",
    "IntegrativePrinciple",
    "ReproduciblePrinciple",
    "ControllablePrinciple",
    "AutonomousPrinciple",
    "SystemArchitecture",
    "get_system_architecture",
    "PrincipleStatus",
    "PrincipleViolation",
    "ComponentRole",
    "ModuleCapability",
    "IntegrationContract",
    "StateSnapshot",
    "ControlAction",
    "AutonomyLevel",
]


# =============================================================================
# ENUMERATIONS AND BASE TYPES
# =============================================================================


class PrincipleStatus(Enum):
    """Status of an architectural principle implementation."""

    NOT_IMPLEMENTED = auto()
    PARTIAL = auto()
    IMPLEMENTED = auto()
    VALIDATED = auto()


class ComponentRole(Enum):
    """Roles that components can assume in the system.

    Ролі компонентів системи:
    - SENSOR: Сенсорний компонент для збору даних
    - PROCESSOR: Обробник даних та сигналів
    - ACTUATOR: Виконавець дій та торгових операцій
    - COORDINATOR: Координатор та оркестратор
    - MONITOR: Спостерігач та аудитор
    - GUARDIAN: Охоронець безпеки та ризиків
    """

    SENSOR = "sensor"
    PROCESSOR = "processor"
    ACTUATOR = "actuator"
    COORDINATOR = "coordinator"
    MONITOR = "monitor"
    GUARDIAN = "guardian"


class AutonomyLevel(Enum):
    """Levels of system autonomy.

    Рівні автономії системи:
    - MANUAL: Повністю ручне управління
    - ASSISTED: Рекомендації без автоматичного виконання
    - SUPERVISED: Автоматичне виконання з людським наглядом
    - AUTONOMOUS: Повна автономія з людським контролем тільки для критичних дій
    """

    MANUAL = 0
    ASSISTED = 1
    SUPERVISED = 2
    AUTONOMOUS = 3


class ModuleCapability(Enum):
    """Capabilities that modules can provide.

    Можливості модулів:
    - DATA_INGESTION: Прийом даних
    - SIGNAL_GENERATION: Генерація сигналів
    - RISK_ASSESSMENT: Оцінка ризиків
    - TRADE_EXECUTION: Виконання торгів
    - LEARNING: Машинне навчання
    - MONITORING: Моніторинг
    """

    DATA_INGESTION = "data_ingestion"
    SIGNAL_GENERATION = "signal_generation"
    RISK_ASSESSMENT = "risk_assessment"
    TRADE_EXECUTION = "trade_execution"
    LEARNING = "learning"
    MONITORING = "monitoring"


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass(frozen=True)
class PrincipleViolation:
    """Represents a violation of an architectural principle.

    Attributes
    ----------
    principle_name : str
        Name of the violated principle
    component : str
        Component where violation occurred
    description : str
        Description of the violation
    severity : Literal["low", "medium", "high", "critical"]
        Severity level
    timestamp : float
        Unix timestamp when violation was detected
    """

    principle_name: str
    component: str
    description: str
    severity: Literal["low", "medium", "high", "critical"]
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class IntegrationContract:
    """Defines an integration contract between components.

    Контракт інтеграції між компонентами:
    - source: Компонент-джерело
    - target: Компонент-споживач
    - data_schema: Схема даних
    - protocol: Протокол комунікації
    """

    source: str
    target: str
    data_schema: str
    protocol: Literal["sync", "async", "event", "stream"]
    version: str = "1.0.0"


@dataclass(frozen=True)
class StateSnapshot:
    """Immutable snapshot of system state for reproducibility.

    Знімок стану системи для відтворюваності:
    - component_states: Стани компонентів
    - random_seeds: Зерна випадковості
    - configuration: Конфігурація
    - timestamp: Мітка часу
    """

    component_states: Mapping[str, Any]
    random_seeds: Mapping[str, int]
    configuration: Mapping[str, Any]
    timestamp: float
    checksum: str = ""

    def __post_init__(self) -> None:
        if not self.checksum:
            object.__setattr__(self, "checksum", self._compute_checksum())

    def _compute_checksum(self) -> str:
        """Compute SHA-256 checksum of state."""
        data = {
            "component_states": dict(self.component_states),
            "random_seeds": dict(self.random_seeds),
            "configuration": dict(self.configuration),
            "timestamp": self.timestamp,
        }
        serialized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()


@dataclass(frozen=True)
class ControlAction:
    """Represents a control action that can be applied to the system.

    Дія контролю системи:
    - action_type: Тип дії
    - target_component: Цільовий компонент
    - parameters: Параметри дії
    - requires_approval: Чи потребує схвалення
    """

    action_type: Literal["start", "stop", "pause", "resume", "reconfigure", "override"]
    target_component: str
    parameters: Mapping[str, Any]
    requires_approval: bool = False
    approval_level: int = 0


# =============================================================================
# ABSTRACT BASE CLASS
# =============================================================================


class ArchitecturePrinciple(ABC):
    """Abstract base class for architectural principles.

    Each principle defines:
    1. A name and description (Ukrainian and English)
    2. Validation logic to check compliance
    3. Configuration interface
    4. Runtime behavior enforcement
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """English name of the principle."""

    @property
    @abstractmethod
    def name_ua(self) -> str:
        """Ukrainian name of the principle."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of the principle."""

    @property
    @abstractmethod
    def status(self) -> PrincipleStatus:
        """Current implementation status."""

    @abstractmethod
    def validate(self, context: Mapping[str, Any]) -> List[PrincipleViolation]:
        """Validate principle compliance in given context.

        Parameters
        ----------
        context : Mapping[str, Any]
            Context containing system state and configuration

        Returns
        -------
        List[PrincipleViolation]
            List of detected violations (empty if compliant)
        """

    @abstractmethod
    def configure(self, settings: Mapping[str, Any]) -> None:
        """Configure the principle with given settings.

        Parameters
        ----------
        settings : Mapping[str, Any]
            Configuration settings for the principle
        """


# =============================================================================
# PRINCIPLE IMPLEMENTATIONS
# =============================================================================


class NeuroOrientedPrinciple(ArchitecturePrinciple):
    """Neuro-oriented architecture principle.

    Нейроорієнтована архітектура:
    - Використання нейронаукових обчислювальних моделей
    - Біологічно-інспіровані алгоритми прийняття рішень
    - Дофамінова петля навчання (TD-learning)
    - Серотонінова система управління ризиками
    - Базальні ганглії для вибору дій
    """

    def __init__(self) -> None:
        self._status = PrincipleStatus.IMPLEMENTED
        self._required_neuromodulators: Set[str] = {
            "dopamine",
            "serotonin",
            "gaba",
            "na_ach",
        }
        self._required_components: Set[str] = {
            "basal_ganglia_selector",
            "dopamine_learning_loop",
            "serotonin_risk_manager",
            "tacl_monitor",
        }
        self._settings: Dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "Neuro-Oriented"

    @property
    def name_ua(self) -> str:
        return "Нейроорієнтована"

    @property
    def description(self) -> str:
        return (
            "Brain-inspired computational models using neuroscience principles "
            "for decision making, learning, and risk management"
        )

    @property
    def status(self) -> PrincipleStatus:
        return self._status

    def validate(self, context: Mapping[str, Any]) -> List[PrincipleViolation]:
        violations: List[PrincipleViolation] = []

        # Check for required neuromodulators
        active_neuromodulators = set(context.get("neuromodulators", []))
        missing = self._required_neuromodulators - active_neuromodulators
        if missing:
            violations.append(
                PrincipleViolation(
                    principle_name=self.name,
                    component="neuromodulator_system",
                    description=f"Missing neuromodulators: {missing}",
                    severity="medium",
                )
            )

        # Check for required components
        active_components = set(context.get("components", []))
        missing_components = self._required_components - active_components
        if missing_components:
            violations.append(
                PrincipleViolation(
                    principle_name=self.name,
                    component="architecture",
                    description=f"Missing neuro-components: {missing_components}",
                    severity="high",
                )
            )

        # Check dopamine learning loop configuration
        learning_config = context.get("learning_loop", {})
        if not learning_config.get("algorithm"):
            violations.append(
                PrincipleViolation(
                    principle_name=self.name,
                    component="learning_loop",
                    description="Dopamine learning loop algorithm not configured",
                    severity="medium",
                )
            )

        return violations

    def configure(self, settings: Mapping[str, Any]) -> None:
        self._settings = dict(settings)
        if "required_neuromodulators" in settings:
            self._required_neuromodulators = set(settings["required_neuromodulators"])
        if "required_components" in settings:
            self._required_components = set(settings["required_components"])


class ModularPrinciple(ArchitecturePrinciple):
    """Modular architecture principle.

    Модульна архітектура:
    - Незалежні, слабко пов'язані компоненти
    - Чіткі інтерфейси та контракти
    - Горизонтальне масштабування
    - Незалежне розгортання
    """

    def __init__(self) -> None:
        self._status = PrincipleStatus.IMPLEMENTED
        self._max_coupling_score: float = 0.3
        self._min_cohesion_score: float = 0.7
        self._settings: Dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "Modular"

    @property
    def name_ua(self) -> str:
        return "Модульна"

    @property
    def description(self) -> str:
        return (
            "Loosely coupled, independently deployable components with clear "
            "interfaces and contracts enabling horizontal scaling"
        )

    @property
    def status(self) -> PrincipleStatus:
        return self._status

    def validate(self, context: Mapping[str, Any]) -> List[PrincipleViolation]:
        violations: List[PrincipleViolation] = []

        # Check coupling score
        coupling_score = context.get("coupling_score", 0.0)
        if coupling_score > self._max_coupling_score:
            violations.append(
                PrincipleViolation(
                    principle_name=self.name,
                    component="module_dependencies",
                    description=(
                        f"Coupling score {coupling_score:.2f} exceeds maximum "
                        f"{self._max_coupling_score:.2f}"
                    ),
                    severity="medium",
                )
            )

        # Check cohesion score
        cohesion_score = context.get("cohesion_score", 1.0)
        if cohesion_score < self._min_cohesion_score:
            violations.append(
                PrincipleViolation(
                    principle_name=self.name,
                    component="module_structure",
                    description=(
                        f"Cohesion score {cohesion_score:.2f} below minimum "
                        f"{self._min_cohesion_score:.2f}"
                    ),
                    severity="low",
                )
            )

        # Check for circular dependencies
        circular_deps = context.get("circular_dependencies", [])
        if circular_deps:
            violations.append(
                PrincipleViolation(
                    principle_name=self.name,
                    component="module_dependencies",
                    description=f"Circular dependencies detected: {circular_deps}",
                    severity="high",
                )
            )

        return violations

    def configure(self, settings: Mapping[str, Any]) -> None:
        self._settings = dict(settings)
        if "max_coupling_score" in settings:
            self._max_coupling_score = float(settings["max_coupling_score"])
        if "min_cohesion_score" in settings:
            self._min_cohesion_score = float(settings["min_cohesion_score"])


class RoleBasedPrinciple(ArchitecturePrinciple):
    """Role-based architecture principle.

    Рольова архітектура:
    - Чітке розділення відповідальностей
    - Контроль доступу на основі ролей
    - Принцип найменших привілеїв
    - Аудит дій за ролями
    """

    def __init__(self) -> None:
        self._status = PrincipleStatus.IMPLEMENTED
        self._required_roles: Set[ComponentRole] = {
            ComponentRole.SENSOR,
            ComponentRole.PROCESSOR,
            ComponentRole.ACTUATOR,
            ComponentRole.COORDINATOR,
            ComponentRole.MONITOR,
            ComponentRole.GUARDIAN,
        }
        self._role_permissions: Dict[ComponentRole, Set[str]] = {
            ComponentRole.SENSOR: {"read_market_data", "emit_events"},
            ComponentRole.PROCESSOR: {
                "process_signals",
                "emit_events",
                "read_features",
            },
            ComponentRole.ACTUATOR: {"execute_orders", "emit_events"},
            ComponentRole.COORDINATOR: {
                "orchestrate",
                "emit_events",
                "read_all",
                "configure",
            },
            ComponentRole.MONITOR: {"read_all", "emit_alerts"},
            ComponentRole.GUARDIAN: {
                "read_all",
                "veto_actions",
                "emit_alerts",
                "halt_system",
            },
        }
        self._settings: Dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "Role-Based"

    @property
    def name_ua(self) -> str:
        return "Рольова"

    @property
    def description(self) -> str:
        return (
            "Clear separation of responsibilities with role-based access control, "
            "least privilege principle, and role-based action auditing"
        )

    @property
    def status(self) -> PrincipleStatus:
        return self._status

    def validate(self, context: Mapping[str, Any]) -> List[PrincipleViolation]:
        violations: List[PrincipleViolation] = []

        # Check that all required roles are assigned
        assigned_roles = set(context.get("assigned_roles", []))
        missing_roles = self._required_roles - assigned_roles
        if missing_roles:
            violations.append(
                PrincipleViolation(
                    principle_name=self.name,
                    component="role_assignment",
                    description=f"Missing required roles: {[r.value for r in missing_roles]}",
                    severity="medium",
                )
            )

        # Check for permission violations
        permission_violations = context.get("permission_violations", [])
        for violation in permission_violations:
            violations.append(
                PrincipleViolation(
                    principle_name=self.name,
                    component=violation.get("component", "unknown"),
                    description=(
                        f"Unauthorized access attempt: {violation.get('action', 'unknown')} "
                        f"by role {violation.get('role', 'unknown')}"
                    ),
                    severity="high",
                )
            )

        return violations

    def configure(self, settings: Mapping[str, Any]) -> None:
        self._settings = dict(settings)
        if "role_permissions" in settings:
            for role_str, perms in settings["role_permissions"].items():
                role = ComponentRole(role_str)
                self._role_permissions[role] = set(perms)

    def get_permissions(self, role: ComponentRole) -> FrozenSet[str]:
        """Get permissions for a specific role."""
        return frozenset(self._role_permissions.get(role, set()))


class IntegrativePrinciple(ArchitecturePrinciple):
    """Integrative architecture principle.

    Інтегративна архітектура:
    - Безшовна інтеграція компонентів
    - Уніфіковані потоки даних
    - Контракти інтеграції
    - Спільні схеми даних
    """

    def __init__(self) -> None:
        self._status = PrincipleStatus.IMPLEMENTED
        self._integration_contracts: List[IntegrationContract] = []
        self._required_integrations: Set[Tuple[str, str]] = {
            ("data_ingestion", "feature_extraction"),
            ("feature_extraction", "risk_assessment"),
            ("risk_assessment", "action_selector"),
            ("action_selector", "execution"),
            ("execution", "monitoring"),
        }
        self._settings: Dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "Integrative"

    @property
    def name_ua(self) -> str:
        return "Інтегративна"

    @property
    def description(self) -> str:
        return (
            "Seamless component integration with unified data flows, "
            "integration contracts, and shared data schemas"
        )

    @property
    def status(self) -> PrincipleStatus:
        return self._status

    def validate(self, context: Mapping[str, Any]) -> List[PrincipleViolation]:
        violations: List[PrincipleViolation] = []

        # Check for required integrations
        active_integrations = set(
            (c["source"], c["target"]) for c in context.get("integration_contracts", [])
        )
        missing = self._required_integrations - active_integrations
        if missing:
            violations.append(
                PrincipleViolation(
                    principle_name=self.name,
                    component="integration_layer",
                    description=f"Missing required integrations: {missing}",
                    severity="high",
                )
            )

        # Check for schema mismatches
        schema_errors = context.get("schema_mismatches", [])
        for error in schema_errors:
            violations.append(
                PrincipleViolation(
                    principle_name=self.name,
                    component=f"{error.get('source', '?')}->{error.get('target', '?')}",
                    description=f"Schema mismatch: {error.get('description', 'unknown')}",
                    severity="high",
                )
            )

        return violations

    def configure(self, settings: Mapping[str, Any]) -> None:
        self._settings = dict(settings)
        if "required_integrations" in settings:
            self._required_integrations = {
                tuple(pair) for pair in settings["required_integrations"]
            }

    def register_contract(self, contract: IntegrationContract) -> None:
        """Register an integration contract."""
        self._integration_contracts.append(contract)


class ReproduciblePrinciple(ArchitecturePrinciple):
    """Reproducible architecture principle.

    Відтворювана архітектура:
    - Детерміністична поведінка
    - Аудит стану системи
    - Версіонування конфігурації
    - Контрольні точки та знімки стану
    """

    def __init__(self) -> None:
        self._status = PrincipleStatus.IMPLEMENTED
        self._snapshots: List[StateSnapshot] = []
        self._max_snapshots: int = 100
        self._require_random_seed: bool = True
        self._settings: Dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "Reproducible"

    @property
    def name_ua(self) -> str:
        return "Відтворювана"

    @property
    def description(self) -> str:
        return (
            "Deterministic behavior with full state auditing, configuration "
            "versioning, and checkpoint/snapshot capabilities"
        )

    @property
    def status(self) -> PrincipleStatus:
        return self._status

    def validate(self, context: Mapping[str, Any]) -> List[PrincipleViolation]:
        violations: List[PrincipleViolation] = []

        # Check for random seed configuration
        if self._require_random_seed:
            random_seeds = context.get("random_seeds", {})
            components = context.get("stochastic_components", [])
            for component in components:
                if component not in random_seeds:
                    violations.append(
                        PrincipleViolation(
                            principle_name=self.name,
                            component=component,
                            description=(
                                f"Stochastic component '{component}' lacks configured "
                                "random seed for reproducibility"
                            ),
                            severity="medium",
                        )
                    )

        # Check for state snapshot capability
        if not context.get("snapshot_enabled", False):
            violations.append(
                PrincipleViolation(
                    principle_name=self.name,
                    component="state_management",
                    description="State snapshot capability not enabled",
                    severity="low",
                )
            )

        # Check configuration versioning
        if not context.get("config_versioned", False):
            violations.append(
                PrincipleViolation(
                    principle_name=self.name,
                    component="configuration",
                    description="Configuration versioning not enabled",
                    severity="low",
                )
            )

        return violations

    def configure(self, settings: Mapping[str, Any]) -> None:
        self._settings = dict(settings)
        if "max_snapshots" in settings:
            self._max_snapshots = int(settings["max_snapshots"])
        if "require_random_seed" in settings:
            self._require_random_seed = bool(settings["require_random_seed"])

    def create_snapshot(
        self,
        component_states: Mapping[str, Any],
        random_seeds: Mapping[str, int],
        configuration: Mapping[str, Any],
    ) -> StateSnapshot:
        """Create and store a state snapshot."""
        snapshot = StateSnapshot(
            component_states=component_states,
            random_seeds=random_seeds,
            configuration=configuration,
            timestamp=time.time(),
        )
        self._snapshots.append(snapshot)

        # Trim old snapshots if necessary
        if len(self._snapshots) > self._max_snapshots:
            self._snapshots = self._snapshots[-self._max_snapshots :]

        return snapshot


class ControllablePrinciple(ArchitecturePrinciple):
    """Controllable architecture principle.

    Контрольована архітектура:
    - Повний операційний контроль
    - Можливість втручання
    - Аварійна зупинка (kill switch)
    - Рівневий контроль доступу
    """

    def __init__(self) -> None:
        self._status = PrincipleStatus.IMPLEMENTED
        self._kill_switch_enabled: bool = True
        self._circuit_breakers_enabled: bool = True
        self._approval_levels: Dict[str, int] = {
            "observe": 0,
            "configure": 1,
            "override": 2,
            "halt": 3,
        }
        self._settings: Dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "Controllable"

    @property
    def name_ua(self) -> str:
        return "Контрольована"

    @property
    def description(self) -> str:
        return (
            "Full operational oversight with intervention capabilities, "
            "kill switch, circuit breakers, and tiered access control"
        )

    @property
    def status(self) -> PrincipleStatus:
        return self._status

    def validate(self, context: Mapping[str, Any]) -> List[PrincipleViolation]:
        violations: List[PrincipleViolation] = []

        # Check kill switch availability
        if self._kill_switch_enabled and not context.get(
            "kill_switch_available", False
        ):
            violations.append(
                PrincipleViolation(
                    principle_name=self.name,
                    component="kill_switch",
                    description="Kill switch not available",
                    severity="critical",
                )
            )

        # Check circuit breakers
        if self._circuit_breakers_enabled:
            breakers = context.get("circuit_breakers", {})
            if not breakers:
                violations.append(
                    PrincipleViolation(
                        principle_name=self.name,
                        component="circuit_breakers",
                        description="No circuit breakers configured",
                        severity="high",
                    )
                )

        # Check monitoring capability
        if not context.get("monitoring_enabled", False):
            violations.append(
                PrincipleViolation(
                    principle_name=self.name,
                    component="monitoring",
                    description="System monitoring not enabled",
                    severity="medium",
                )
            )

        return violations

    def configure(self, settings: Mapping[str, Any]) -> None:
        self._settings = dict(settings)
        if "kill_switch_enabled" in settings:
            self._kill_switch_enabled = bool(settings["kill_switch_enabled"])
        if "circuit_breakers_enabled" in settings:
            self._circuit_breakers_enabled = bool(settings["circuit_breakers_enabled"])
        if "approval_levels" in settings:
            self._approval_levels = dict(settings["approval_levels"])

    def validate_action(self, action: ControlAction, operator_level: int) -> bool:
        """Validate if an operator can perform a control action.

        Parameters
        ----------
        action : ControlAction
            The control action to validate
        operator_level : int
            The operator's approval level

        Returns
        -------
        bool
            True if action is allowed
        """
        if action.requires_approval:
            return operator_level >= action.approval_level
        return True


class AutonomousPrinciple(ArchitecturePrinciple):
    """Autonomous architecture principle.

    Автономна архітектура:
    - Саморегулювання
    - Адаптивна поведінка
    - Рівні автономії
    - Автоматичне відновлення
    """

    def __init__(self) -> None:
        self._status = PrincipleStatus.IMPLEMENTED
        self._autonomy_level: AutonomyLevel = AutonomyLevel.SUPERVISED
        self._max_autonomy_level: AutonomyLevel = AutonomyLevel.AUTONOMOUS
        self._self_healing_enabled: bool = True
        self._adaptation_enabled: bool = True
        self._settings: Dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "Autonomous"

    @property
    def name_ua(self) -> str:
        return "Автономна"

    @property
    def description(self) -> str:
        return (
            "Self-regulating and adaptive behavior with configurable autonomy "
            "levels and automatic recovery capabilities"
        )

    @property
    def status(self) -> PrincipleStatus:
        return self._status

    @property
    def autonomy_level(self) -> AutonomyLevel:
        return self._autonomy_level

    def validate(self, context: Mapping[str, Any]) -> List[PrincipleViolation]:
        violations: List[PrincipleViolation] = []

        # Check self-healing capability
        if self._self_healing_enabled and not context.get(
            "self_healing_available", False
        ):
            violations.append(
                PrincipleViolation(
                    principle_name=self.name,
                    component="self_healing",
                    description="Self-healing capability not available",
                    severity="medium",
                )
            )

        # Check adaptation capability
        if self._adaptation_enabled and not context.get("adaptation_available", False):
            violations.append(
                PrincipleViolation(
                    principle_name=self.name,
                    component="adaptation",
                    description="Adaptation capability not available",
                    severity="low",
                )
            )

        # Check autonomy constraints
        current_level = context.get("current_autonomy_level", AutonomyLevel.MANUAL)
        if isinstance(current_level, int):
            current_level = AutonomyLevel(current_level)
        if current_level.value > self._max_autonomy_level.value:
            violations.append(
                PrincipleViolation(
                    principle_name=self.name,
                    component="autonomy_control",
                    description=(
                        f"Current autonomy level {current_level.name} exceeds maximum "
                        f"allowed {self._max_autonomy_level.name}"
                    ),
                    severity="high",
                )
            )

        return violations

    def configure(self, settings: Mapping[str, Any]) -> None:
        self._settings = dict(settings)
        if "autonomy_level" in settings:
            self._autonomy_level = AutonomyLevel(settings["autonomy_level"])
        if "max_autonomy_level" in settings:
            self._max_autonomy_level = AutonomyLevel(settings["max_autonomy_level"])
        if "self_healing_enabled" in settings:
            self._self_healing_enabled = bool(settings["self_healing_enabled"])
        if "adaptation_enabled" in settings:
            self._adaptation_enabled = bool(settings["adaptation_enabled"])

    def set_autonomy_level(self, level: AutonomyLevel) -> bool:
        """Set the system autonomy level.

        Parameters
        ----------
        level : AutonomyLevel
            The desired autonomy level

        Returns
        -------
        bool
            True if level was set successfully
        """
        if level.value <= self._max_autonomy_level.value:
            self._autonomy_level = level
            return True
        return False


# =============================================================================
# SYSTEM ARCHITECTURE CONTAINER
# =============================================================================


class SystemArchitecture:
    """Container for all system architecture principles.

    Архітектура системи TradePulse:
    Об'єднує всі сім архітектурних принципів та забезпечує
    централізовану валідацію та конфігурацію.
    """

    def __init__(self) -> None:
        self._principles: Dict[str, ArchitecturePrinciple] = {
            "neuro_oriented": NeuroOrientedPrinciple(),
            "modular": ModularPrinciple(),
            "role_based": RoleBasedPrinciple(),
            "integrative": IntegrativePrinciple(),
            "reproducible": ReproduciblePrinciple(),
            "controllable": ControllablePrinciple(),
            "autonomous": AutonomousPrinciple(),
        }

    @property
    def principles(self) -> Mapping[str, ArchitecturePrinciple]:
        """Get all architecture principles."""
        return self._principles

    def get_principle(self, name: str) -> Optional[ArchitecturePrinciple]:
        """Get a specific principle by name."""
        return self._principles.get(name)

    def validate_all(
        self, context: Mapping[str, Any]
    ) -> Dict[str, List[PrincipleViolation]]:
        """Validate all principles against given context.

        Parameters
        ----------
        context : Mapping[str, Any]
            System context for validation

        Returns
        -------
        Dict[str, List[PrincipleViolation]]
            Dictionary mapping principle names to their violations
        """
        return {
            name: principle.validate(context)
            for name, principle in self._principles.items()
        }

    def configure_all(self, settings: Mapping[str, Mapping[str, Any]]) -> None:
        """Configure all principles from settings.

        Parameters
        ----------
        settings : Mapping[str, Mapping[str, Any]]
            Dictionary mapping principle names to their settings
        """
        for name, principle_settings in settings.items():
            principle = self._principles.get(name)
            if principle:
                principle.configure(principle_settings)

    def get_summary(self) -> Dict[str, Dict[str, str]]:
        """Get summary of all principles.

        Returns
        -------
        Dict[str, Dict[str, str]]
            Dictionary with principle information
        """
        return {
            name: {
                "name": principle.name,
                "name_ua": principle.name_ua,
                "description": principle.description,
                "status": principle.status.name,
            }
            for name, principle in self._principles.items()
        }

    def to_json(self) -> str:
        """Serialize architecture summary to JSON."""
        return json.dumps(self.get_summary(), indent=2, ensure_ascii=False)


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================


_system_architecture: Optional[SystemArchitecture] = None


def get_system_architecture() -> SystemArchitecture:
    """Get the singleton system architecture instance.

    Returns
    -------
    SystemArchitecture
        The global system architecture instance
    """
    global _system_architecture
    if _system_architecture is None:
        _system_architecture = SystemArchitecture()
    return _system_architecture
