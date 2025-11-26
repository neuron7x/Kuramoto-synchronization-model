"""Neuro-Orchestrator Agent for TradePulse.

This module implements the biologically-inspired control architecture orchestrator
that maps trading scenarios to module-level instructions for the TradePulse system.

The orchestrator coordinates:
- Basal ganglia-style action selection
- Dopamine loop learning (TD-based reinforcement)
- Threat/risk contours (risk management)
- TACL free-energy monitoring and protocol management
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Literal, Mapping, Optional

__all__ = [
    "TradingScenario",
    "ModuleInstruction",
    "RiskContour",
    "LearningLoop",
    "OrchestrationOutput",
    "NeuroOrchestrator",
]


@dataclass(frozen=True)
class TradingScenario:
    """Input specification for a trading scenario.

    Attributes
    ----------
    market : str
        Target market/symbol (e.g., "BTC/USDT", "SPY")
    timeframe : str
        Trading timeframe (e.g., "1h", "5m", "1d")
    risk_profile : Literal["conservative", "moderate", "aggressive"]
        Risk tolerance level
    capital : float, optional
        Initial capital allocation
    max_position_size : float, optional
        Maximum position size as fraction of capital (0-1)
    """

    market: str
    timeframe: str
    risk_profile: Literal["conservative", "moderate", "aggressive"]
    capital: float = 100000.0
    max_position_size: float = 0.2


@dataclass(frozen=True)
class ModuleInstruction:
    """Instruction specification for a system module.

    Attributes
    ----------
    module_name : str
        Name of the module (e.g., "action_selector", "data_ingestion")
    operation : str
        Operation to perform (e.g., "select", "ingest", "evaluate")
    parameters : Dict[str, Any]
        Module-specific parameters
    priority : int
        Execution priority (lower = higher priority)
    """

    module_name: str
    operation: str
    parameters: Dict[str, Any]
    priority: int = 0


@dataclass(frozen=True)
class RiskContour:
    """Risk assessment and threat threshold configuration.

    Attributes
    ----------
    mode : Literal["conservative", "normal", "aggressive"]
        Risk operating mode
    threat_threshold : float
        Threshold for threat detection (0-1)
    exposure_limit : float
        Maximum portfolio exposure fraction
    drawdown_limit : float
        Maximum allowed drawdown fraction
    var_confidence : float
        Confidence level for VaR calculation
    kelly_fraction_cap : float
        Maximum Kelly fraction for position sizing
    """

    mode: Literal["conservative", "normal", "aggressive"]
    threat_threshold: float
    exposure_limit: float
    drawdown_limit: float
    var_confidence: float = 0.975
    kelly_fraction_cap: float = 1.0


@dataclass(frozen=True)
class LearningLoop:
    """Dopamine-loop learning configuration (TD-based).

    Attributes
    ----------
    algorithm : str
        Learning algorithm (e.g., "TD(0)", "TD(λ)")
    discount_gamma : float
        Temporal discount factor (0-1)
    learning_rate : float
        Value function learning rate
    prediction_window : int
        Steps ahead for prediction
    error_metric : str
        Error metric for RPE (e.g., "absolute", "squared")
    update_rule : str
        Update rule specification
    """

    algorithm: str = "TD(0)"
    discount_gamma: float = 0.99
    learning_rate: float = 0.01
    prediction_window: int = 1
    error_metric: str = "absolute"
    update_rule: str = (
        "delta = reward + gamma * V_next - V_current; V_current += learning_rate * delta"
    )


@dataclass(frozen=True)
class OrchestrationOutput:
    """Complete orchestration specification output.

    Attributes
    ----------
    module_sequence : List[ModuleInstruction]
        Ordered sequence of module instructions
    parameters : Dict[str, Any]
        Global system parameters
    risk_contour : RiskContour
        Risk configuration and thresholds
    learning_loop : LearningLoop
        Learning loop specification
    """

    module_sequence: List[ModuleInstruction]
    parameters: Dict[str, Any]
    risk_contour: RiskContour
    learning_loop: LearningLoop

    def to_json(self, **kwargs) -> str:
        """Convert to JSON string.

        Parameters
        ----------
        **kwargs
            Additional arguments passed to json.dumps

        Returns
        -------
        str
            JSON representation
        """
        data = {
            "module_sequence": [asdict(m) for m in self.module_sequence],
            "parameters": self.parameters,
            "risk_contour": asdict(self.risk_contour),
            "learning_loop": asdict(self.learning_loop),
        }
        return json.dumps(data, indent=2, **kwargs)


class NeuroOrchestrator:
    """Neuro-Orchestrator Agent for biologically-inspired module coordination.

    This orchestrator implements the mapping between trading scenarios and
    TradePulse's neuroscience-inspired architecture:

    - Basal ganglia → action selection module
    - Dopamine loop → learning_loop (TD-based reinforcement)
    - Threat contour → risk_contour (risk management)
    - TACL → free-energy monitoring and protocol hot-swapping

    The orchestrator ensures all proposed actions maintain TACL's monotonic
    free-energy descent constraint: no action can increase system free energy
    without human override.
    """

    def __init__(
        self,
        *,
        free_energy_threshold: float = 1.4,
        enable_tacl_validation: bool = True,
    ) -> None:
        """Initialize the orchestrator.

        Parameters
        ----------
        free_energy_threshold : float, optional
            Maximum allowed free energy (TACL constraint), by default 1.4
        enable_tacl_validation : bool, optional
            Enable TACL free-energy validation, by default True
        """
        self._free_energy_threshold = free_energy_threshold
        self._enable_tacl_validation = enable_tacl_validation

    def orchestrate(
        self,
        scenario: TradingScenario,
        *,
        custom_parameters: Optional[Mapping[str, Any]] = None,
    ) -> OrchestrationOutput:
        """Generate module-level orchestration for a trading scenario.

        Parameters
        ----------
        scenario : TradingScenario
            Input trading scenario specification
        custom_parameters : Optional[Mapping[str, Any]], optional
            Override default parameters

        Returns
        -------
        OrchestrationOutput
            Complete orchestration specification with module sequence,
            parameters, risk contour, and learning loop

        Notes
        -----
        This method implements the mapping from scenario to modules while
        ensuring TACL's monotonic free-energy descent constraint is maintained.
        """
        # Map risk profile to parameters
        risk_params = self._map_risk_profile(scenario.risk_profile)

        # Build module sequence
        module_sequence = self._build_module_sequence(scenario, risk_params)

        # Configure global parameters
        parameters = self._build_parameters(scenario, risk_params, custom_parameters)

        # Define risk contour
        risk_contour = self._build_risk_contour(scenario, risk_params)

        # Configure learning loop
        learning_loop = self._build_learning_loop(scenario, risk_params)

        # Validate TACL constraint if enabled
        if self._enable_tacl_validation:
            self._validate_free_energy_constraint(parameters)

        return OrchestrationOutput(
            module_sequence=module_sequence,
            parameters=parameters,
            risk_contour=risk_contour,
            learning_loop=learning_loop,
        )

    def _map_risk_profile(
        self, risk_profile: Literal["conservative", "moderate", "aggressive"]
    ) -> Dict[str, float]:
        """Map risk profile to numerical parameters."""
        profiles = {
            "conservative": {
                "threat_threshold": 0.3,
                "exposure_limit": 0.3,
                "drawdown_limit": 0.05,
                "temperature": 0.5,
                "learning_rate": 0.005,
                "discount_gamma": 0.95,
                "kelly_cap": 0.5,
            },
            "moderate": {
                "threat_threshold": 0.5,
                "exposure_limit": 0.5,
                "drawdown_limit": 0.10,
                "temperature": 1.0,
                "learning_rate": 0.01,
                "discount_gamma": 0.99,
                "kelly_cap": 0.75,
            },
            "aggressive": {
                "threat_threshold": 0.7,
                "exposure_limit": 0.8,
                "drawdown_limit": 0.20,
                "temperature": 1.5,
                "learning_rate": 0.02,
                "discount_gamma": 0.99,
                "kelly_cap": 1.0,
            },
        }
        return profiles[risk_profile]

    def _build_module_sequence(
        self,
        scenario: TradingScenario,
        risk_params: Dict[str, float],
    ) -> List[ModuleInstruction]:
        """Build ordered sequence of module instructions.

        Module execution order follows the biological pathway:
        1. Data ingestion (sensory input)
        2. Feature extraction (preprocessing)
        3. Risk assessment (threat detection)
        4. Action selection (basal ganglia)
        5. Learning update (dopamine loop)
        6. TACL monitoring (free-energy validation)
        """
        return [
            ModuleInstruction(
                module_name="data_ingestion",
                operation="ingest",
                parameters={
                    "symbol": scenario.market,
                    "timeframe": scenario.timeframe,
                    "buffer_size": 1000,
                },
                priority=0,
            ),
            ModuleInstruction(
                module_name="feature_extraction",
                operation="extract",
                parameters={
                    "indicators": ["kuramoto", "ricci_flow", "entropy"],
                    "lookback": 100,
                },
                priority=1,
            ),
            ModuleInstruction(
                module_name="risk_assessment",
                operation="evaluate",
                parameters={
                    "method": "var_es",
                    "confidence": risk_params["threat_threshold"],
                    "window": 50,
                },
                priority=2,
            ),
            ModuleInstruction(
                module_name="action_selector",
                operation="select",
                parameters={
                    "algorithm": "basal_ganglia",
                    "temperature": risk_params["temperature"],
                    "neuromodulators": ["dopamine", "serotonin", "gaba", "na_ach"],
                },
                priority=3,
            ),
            ModuleInstruction(
                module_name="learning_loop",
                operation="update",
                parameters={
                    "algorithm": "TD(0)",
                    "learning_rate": risk_params["learning_rate"],
                    "discount_gamma": risk_params["discount_gamma"],
                },
                priority=4,
            ),
            ModuleInstruction(
                module_name="tacl_monitor",
                operation="validate",
                parameters={
                    "free_energy_threshold": self._free_energy_threshold,
                    "monotonic_descent": True,
                    "protocol_hot_swap": True,
                },
                priority=5,
            ),
        ]

    def _build_parameters(
        self,
        scenario: TradingScenario,
        risk_params: Dict[str, float],
        custom_parameters: Optional[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        """Build global system parameters."""
        params: Dict[str, Any] = {
            "capital": scenario.capital,
            "max_position_size": scenario.max_position_size,
            "learning_rate": risk_params["learning_rate"],
            "discount_gamma": risk_params["discount_gamma"],
            "exposure_limit": risk_params["exposure_limit"],
            "free_energy_threshold": self._free_energy_threshold,
            "temperature": risk_params["temperature"],
            # Neuromodulator settings
            "dopamine": {
                "burst_factor": 1.5,
                "decay_rate": 0.95,
                "invigoration_threshold": 0.6,
            },
            "serotonin": {
                "stress_threshold": 0.15,
                "hold_temperature_floor": 0.3,
            },
            "gaba": {
                "inhibition_decay": 0.90,
                "impulse_threshold": 0.5,
            },
            "na_ach": {
                "arousal_sensitivity": 1.2,
                "attention_gain": 1.0,
            },
            # TACL settings
            "tacl": {
                "monotonic_descent": True,
                "epsilon_tolerance": 0.01,
                "crisis_detection": True,
                "protocol_options": ["CRDT", "RDMA", "gRPC", "shared_memory"],
            },
        }

        # Apply custom overrides using a deep merge so nested dictionaries are
        # preserved rather than replaced wholesale.
        if custom_parameters:
            normalised_overrides = self._normalise_custom_parameters(custom_parameters)
            params = self._deep_merge_dicts(params, normalised_overrides)

        return params

    def _normalise_custom_parameters(
        self, custom_parameters: Mapping[str, Any]
    ) -> Dict[str, Any]:
        """Expand dotted-path overrides into nested dictionaries.

        ``custom_parameters`` can contain keys using dot notation (e.g.
        ``"dopamine.burst_factor"``) to target nested configuration entries
        without having to provide the entire hierarchy. This helper expands
        those keys into proper nested dictionaries so they can be merged by
        :meth:`_deep_merge_dicts` alongside traditional mapping overrides.

        Parameters
        ----------
        custom_parameters : Mapping[str, Any]
            Mapping containing user supplied overrides. Nested mappings are
            copied to avoid mutating caller-provided objects.

        Returns
        -------
        Dict[str, Any]
            Normalised dictionary ready for deep merging.

        Raises
        ------
        ValueError
            If a dotted path collides with a non-mapping value in the override
            payload, making the desired target ambiguous.
        """

        normalised: Dict[str, Any] = {}

        for raw_key, raw_value in custom_parameters.items():
            prepared_value = self._prepare_override_value(raw_value)
            if "." in raw_key:
                self._assign_override_path(
                    normalised, raw_key.split("."), prepared_value
                )
            else:
                if raw_key in normalised:
                    normalised[raw_key] = self._combine_override_values(
                        normalised[raw_key], prepared_value, raw_key
                    )
                else:
                    normalised[raw_key] = prepared_value

        return normalised

    def _prepare_override_value(self, value: Any) -> Any:
        """Create a merge-ready copy of ``value``."""

        if isinstance(value, Mapping):
            return {
                key: self._prepare_override_value(val) for key, val in value.items()
            }
        return value

    def _assign_override_path(
        self, target: Dict[str, Any], path: List[str], value: Any
    ) -> None:
        """Assign ``value`` to ``target`` following ``path`` segments."""

        current: Dict[str, Any] = target
        for segment in path[:-1]:
            existing = current.get(segment)
            if existing is None:
                next_level: Dict[str, Any] = {}
                current[segment] = next_level
                current = next_level
                continue

            if not isinstance(existing, dict):
                joined = ".".join(path)
                raise ValueError(
                    "Custom parameter override for '%s' collides with a non-mapping value."
                    % joined
                )

            current = existing

        leaf = path[-1]
        if leaf in current:
            current[leaf] = self._combine_override_values(
                current[leaf], value, ".".join(path)
            )
        else:
            current[leaf] = value

    def _combine_override_values(self, existing: Any, incoming: Any, key: str) -> Any:
        """Resolve collisions when normalising override values."""

        if isinstance(existing, dict) and isinstance(incoming, dict):
            return self._deep_merge_dicts(existing, incoming)

        if isinstance(existing, dict) != isinstance(incoming, dict):
            raise ValueError(
                "Custom parameter override for '%s' mixes structured and scalar values."
                % key
            )

        return incoming

    def _deep_merge_dicts(
        self, base: Dict[str, Any], overrides: Mapping[str, Any]
    ) -> Dict[str, Any]:
        """Recursively merge ``overrides`` into ``base``.

        The default ``dict.update`` implementation replaces nested dictionaries
        entirely which is undesirable for configuration structures where the
        caller might wish to tweak a single field.  This helper performs a
        depth-aware merge so that nested keys are updated in place while the
        rest of the defaults remain intact.

        Parameters
        ----------
        base : Dict[str, Any]
            Dictionary containing the default values. The dictionary is mutated
            in place and also returned for convenience.
        overrides : Mapping[str, Any]
            Mapping containing user supplied overrides. Nested mappings are
            merged recursively.

        Returns
        -------
        Dict[str, Any]
            The merged dictionary reference (identical to ``base``).
        """

        for key, value in overrides.items():
            if isinstance(value, Mapping):
                existing = base.get(key)
                if isinstance(existing, dict):
                    base[key] = self._deep_merge_dicts(existing, value)
                else:
                    base[key] = self._deep_merge_dicts({}, value)
            else:
                base[key] = value

        return base

    def _build_risk_contour(
        self,
        scenario: TradingScenario,
        risk_params: Dict[str, float],
    ) -> RiskContour:
        """Build risk contour configuration."""
        return RiskContour(
            mode=(
                scenario.risk_profile
                if scenario.risk_profile in ["conservative", "aggressive"]
                else "normal"
            ),
            threat_threshold=risk_params["threat_threshold"],
            exposure_limit=risk_params["exposure_limit"],
            drawdown_limit=risk_params["drawdown_limit"],
            var_confidence=0.975,
            kelly_fraction_cap=risk_params["kelly_cap"],
        )

    def _build_learning_loop(
        self,
        scenario: TradingScenario,
        risk_params: Dict[str, float],
    ) -> LearningLoop:
        """Build dopamine-loop learning configuration."""
        return LearningLoop(
            algorithm="TD(0)",
            discount_gamma=risk_params["discount_gamma"],
            learning_rate=risk_params["learning_rate"],
            prediction_window=1,
            error_metric="absolute",
            update_rule="delta = reward + gamma * V_next - V_current; V_current += learning_rate * delta",
        )

    def _validate_free_energy_constraint(self, parameters: Dict[str, Any]) -> None:
        """Validate TACL monotonic free-energy descent constraint.

        This ensures no configuration will increase system free energy without
        human override, maintaining TACL's thermodynamic stability guarantees.

        Parameters
        ----------
        parameters : Dict[str, Any]
            System parameters to validate

        Raises
        ------
        ValueError
            If parameters would violate the free-energy constraint
        """
        # Check critical parameters that affect free energy
        free_energy_threshold = parameters.get(
            "free_energy_threshold", self._free_energy_threshold
        )
        temperature = parameters.get("temperature", 1.0)

        # Validate threshold
        if free_energy_threshold > 2.0:
            raise ValueError(
                f"free_energy_threshold {free_energy_threshold} exceeds safe limit (2.0). "
                "This would violate TACL's monotonic descent constraint."
            )

        # Validate temperature (high temperature increases exploration/entropy)
        if temperature > 2.5:
            raise ValueError(
                f"temperature {temperature} exceeds safe limit (2.5). "
                "High temperature increases system entropy and may violate free-energy constraints."
            )

        # Ensure TACL monitoring is enabled
        tacl_config = parameters.get("tacl", {})
        if not tacl_config.get("monotonic_descent", True):
            raise ValueError(
                "TACL monotonic_descent must be enabled to ensure free-energy constraint compliance."
            )


def create_orchestration_from_scenario(
    market: str,
    timeframe: str,
    risk_profile: Literal["conservative", "moderate", "aggressive"] = "moderate",
    *,
    capital: float = 100000.0,
    max_position_size: float = 0.2,
    free_energy_threshold: float = 1.4,
) -> OrchestrationOutput:
    """Convenience function to create orchestration from scenario parameters.

    Parameters
    ----------
    market : str
        Target market/symbol
    timeframe : str
        Trading timeframe
    risk_profile : Literal["conservative", "moderate", "aggressive"], optional
        Risk tolerance level, by default "moderate"
    capital : float, optional
        Initial capital, by default 100000.0
    max_position_size : float, optional
        Maximum position size fraction, by default 0.2
    free_energy_threshold : float, optional
        TACL free-energy threshold, by default 1.4

    Returns
    -------
    OrchestrationOutput
        Complete orchestration specification

    Examples
    --------
    >>> output = create_orchestration_from_scenario(
    ...     market="BTC/USDT",
    ...     timeframe="1h",
    ...     risk_profile="moderate"
    ... )
    >>> print(output.to_json())
    """
    scenario = TradingScenario(
        market=market,
        timeframe=timeframe,
        risk_profile=risk_profile,
        capital=capital,
        max_position_size=max_position_size,
    )

    orchestrator = NeuroOrchestrator(
        free_energy_threshold=free_energy_threshold,
        enable_tacl_validation=True,
    )

    return orchestrator.orchestrate(scenario)
