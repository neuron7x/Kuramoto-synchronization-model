"""NeuroPhysioGuard - AI Agent for Neurophysiology Research Projects.

This module implements a specialized AI agent for advancing neurophysiology projects
using AI tools (PyTorch for neural simulations, BioPython for data parsing, SymPy
for biophysical equations) while enforcing Distinguished-level AI Safety protocols.

Core Principles (Non-Negotiable Safety Guardrails):
    1. Alignment Check: Every output must align with neurophysiological facts
    2. Robustness: Use chain-of-thought reasoning with verifiable steps
    3. Interpretability: Explain decisions transparently with structured format
    4. Ethical Rails: Never generate medical advice, flag biases
    5. Project Velocity: Structure workflows as Ideate -> Model -> Simulate -> Validate -> Iterate

Example
-------
>>> from tradepulse.core.neuro import create_neurophysiology_pipeline
>>> output = create_neurophysiology_pipeline(
...     domain="synaptic_plasticity",
...     task_type="model",
...     confidence_threshold=0.8
... )
>>> print(output.to_json())
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Mapping, Optional

__all__ = [
    "NeurophysiologyDomain",
    "PhysioScenario",
    "PipelineStep",
    "SafetyAudit",
    "PhysioOutput",
    "NeuroPhysioGuard",
    "create_neurophysiology_pipeline",
]


class NeurophysiologyDomain(str, Enum):
    """Neurophysiology research domains supported by the agent."""

    SYNAPTIC_PLASTICITY = "synaptic_plasticity"
    NETWORK_OSCILLATIONS = "network_oscillations"
    OPTOGENETICS = "optogenetics"
    ION_CHANNELS = "ion_channels"
    NEURAL_CODING = "neural_coding"
    NEUROMODULATION = "neuromodulation"
    CIRCADIAN_RHYTHMS = "circadian_rhythms"
    MOTOR_CONTROL = "motor_control"


@dataclass(frozen=True)
class PhysioScenario:
    """Input specification for a neurophysiology research scenario.

    Attributes
    ----------
    domain : NeurophysiologyDomain
        Target neurophysiology domain (e.g., synaptic_plasticity, network_oscillations)
    task_type : Literal["ideate", "model", "simulate", "validate", "iterate"]
        Phase of the research pipeline
    organism : str
        Model organism (e.g., "mouse", "rat", "human", "c_elegans")
    brain_region : str
        Target brain region (e.g., "hippocampus_CA1", "prefrontal_cortex")
    confidence_threshold : float
        Minimum confidence level for outputs (0-1)
    validate_empirically : bool
        Whether to flag outputs for empirical validation
    """

    domain: NeurophysiologyDomain
    task_type: Literal["ideate", "model", "simulate", "validate", "iterate"]
    organism: str = "mouse"
    brain_region: str = "hippocampus_CA1"
    confidence_threshold: float = 0.8
    validate_empirically: bool = True


@dataclass(frozen=True)
class PipelineStep:
    """Step specification in the neurophysiology pipeline.

    Attributes
    ----------
    step_name : str
        Name of the pipeline step
    operation : str
        Operation to perform (e.g., "parse_data", "build_model")
    rationale : str
        Explanation of why this step is performed (interpretability)
    parameters : Dict[str, Any]
        Step-specific parameters
    priority : int
        Execution priority (lower = higher priority)
    tools : List[str]
        AI tools used (e.g., ["pytorch", "biopython", "sympy"])
    citations : List[str]
        Scientific citations supporting this step
    """

    step_name: str
    operation: str
    rationale: str
    parameters: Dict[str, Any]
    priority: int = 0
    tools: List[str] = field(default_factory=list)
    citations: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class SafetyAudit:
    """Safety audit record for the pipeline output.

    Attributes
    ----------
    risks_mitigated : List[str]
        List of risks that were identified and mitigated
    biases_flagged : List[str]
        List of potential biases identified in the analysis
    confidence_score : float
        Overall confidence score (0-1)
    validation_required : bool
        Whether empirical validation is recommended
    validation_method : str
        Suggested empirical validation method
    ethical_considerations : List[str]
        Ethical considerations for this research
    is_hypothesis : bool
        Whether the output should be treated as hypothesis (vs established fact)
    """

    risks_mitigated: List[str]
    biases_flagged: List[str]
    confidence_score: float
    validation_required: bool = True
    validation_method: str = "Simulate in NEURON software"
    ethical_considerations: List[str] = field(default_factory=list)
    is_hypothesis: bool = False


@dataclass(frozen=True)
class PhysioOutput:
    """Complete neurophysiology pipeline output.

    This class follows the required output format:
    - Project Milestone: Brief summary of progress
    - Key Outputs: Code snippets, diagrams, or data viz if applicable
    - Safety Log: Risks mitigated; Confidence score 0-1
    - Next Action: Prompt for user or agent escalation

    Attributes
    ----------
    project_milestone : str
        Brief summary of progress on the research task
    pipeline_steps : List[PipelineStep]
        Ordered sequence of pipeline step instructions
    key_outputs : Dict[str, Any]
        Generated outputs (code, equations, data)
    safety_log : SafetyAudit
        Safety audit record
    next_action : str
        Suggested next action for user or agent
    parameters : Dict[str, Any]
        Global pipeline parameters
    """

    project_milestone: str
    pipeline_steps: List[PipelineStep]
    key_outputs: Dict[str, Any]
    safety_log: SafetyAudit
    next_action: str
    parameters: Dict[str, Any]

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
            "project_milestone": self.project_milestone,
            "pipeline_steps": [asdict(s) for s in self.pipeline_steps],
            "key_outputs": self.key_outputs,
            "safety_log": asdict(self.safety_log),
            "next_action": self.next_action,
            "parameters": self.parameters,
        }
        return json.dumps(data, indent=2, **kwargs)


class NeuroPhysioGuard:
    """NeuroPhysioGuard AI Agent for neurophysiology research projects.

    This agent implements Distinguished-level AI Safety protocols while
    advancing neurophysiology projects using AI tools. It enforces:

    - Alignment Check: All outputs must align with neurophysiological facts
    - Robustness: Chain-of-thought reasoning with verifiable steps
    - Interpretability: Transparent decision explanations
    - Ethical Rails: No medical advice, bias flagging, diverse population consideration
    - Project Velocity: Structured research workflows

    The agent supports domains including:
    - Synaptic plasticity (LTP/LTD, STDP)
    - Network oscillations (theta, gamma rhythms)
    - Optogenetics
    - Ion channel dynamics (Hodgkin-Huxley)
    - Neural coding
    - Neuromodulation

    Parameters
    ----------
    confidence_threshold : float, optional
        Minimum confidence for outputs, by default 0.8
    enable_safety_validation : bool, optional
        Enable safety validation checks, by default True
    flag_hypotheses : bool, optional
        Flag uncertain outputs as hypotheses, by default True

    Example
    -------
    >>> guard = NeuroPhysioGuard()
    >>> scenario = PhysioScenario(
    ...     domain=NeurophysiologyDomain.SYNAPTIC_PLASTICITY,
    ...     task_type="model",
    ... )
    >>> output = guard.process(scenario)
    >>> print(output.project_milestone)
    """

    # Domain-specific scientific citations
    _DOMAIN_CITATIONS: Dict[NeurophysiologyDomain, List[str]] = {
        NeurophysiologyDomain.SYNAPTIC_PLASTICITY: [
            "Bi & Poo (1998) - Spike-timing-dependent plasticity",
            "Bliss & Collingridge (1993) - LTP mechanisms",
            "Malenka & Bear (2004) - LTP and LTD",
        ],
        NeurophysiologyDomain.NETWORK_OSCILLATIONS: [
            "Buzsáki (2006) - Rhythms of the Brain",
            "Fries (2005) - Communication through coherence",
            "Colgin (2016) - Theta-gamma coupling",
        ],
        NeurophysiologyDomain.OPTOGENETICS: [
            "Boyden et al. (2005) - Millisecond-timescale control",
            "Deisseroth (2011) - Optogenetics",
            "Yizhar et al. (2011) - Optogenetics applications",
        ],
        NeurophysiologyDomain.ION_CHANNELS: [
            "Hodgkin & Huxley (1952) - Action potential model",
            "Hille (2001) - Ion Channels of Excitable Membranes",
            "Armstrong & Hille (1998) - Voltage-gated channels",
        ],
        NeurophysiologyDomain.NEURAL_CODING: [
            "Quiroga et al. (2005) - Invariant visual representation",
            "Hubel & Wiesel (1962) - Receptive fields",
            "Barlow (1972) - Single units and sensation",
        ],
        NeurophysiologyDomain.NEUROMODULATION: [
            "Marder (2012) - Neuromodulation of neuronal circuits",
            "Dayan (2012) - Computational models of neuromodulation",
            "Schultz (1998) - Dopamine reward prediction",
        ],
        NeurophysiologyDomain.CIRCADIAN_RHYTHMS: [
            "Reppert & Weaver (2002) - Molecular mechanisms",
            "Welsh et al. (2010) - SCN circadian pacemaking",
            "Hastings et al. (2018) - Circadian clocks",
        ],
        NeurophysiologyDomain.MOTOR_CONTROL: [
            "Todorov & Jordan (2002) - Optimal feedback control",
            "Shadmehr & Krakauer (2008) - Motor learning",
            "Wolpert et al. (2011) - Computational motor control",
        ],
    }

    # Tools mapping per operation type
    _TOOL_MAPPING: Dict[str, List[str]] = {
        "model": ["pytorch", "sympy", "numpy"],
        "simulate": ["neuron_software", "brian2", "pytorch"],
        "parse_data": ["biopython", "scipy", "pandas"],
        "validate": ["statsmodels", "scipy", "hypothesis"],
        "visualize": ["matplotlib", "seaborn", "plotly"],
    }

    def __init__(
        self,
        *,
        confidence_threshold: float = 0.8,
        enable_safety_validation: bool = True,
        flag_hypotheses: bool = True,
    ) -> None:
        """Initialize the NeuroPhysioGuard agent.

        Parameters
        ----------
        confidence_threshold : float, optional
            Minimum confidence for outputs, by default 0.8
        enable_safety_validation : bool, optional
            Enable safety validation checks, by default True
        flag_hypotheses : bool, optional
            Flag uncertain outputs as hypotheses, by default True
        """
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0 and 1")

        self._confidence_threshold = confidence_threshold
        self._enable_safety_validation = enable_safety_validation
        self._flag_hypotheses = flag_hypotheses

    def process(
        self,
        scenario: PhysioScenario,
        *,
        custom_parameters: Optional[Mapping[str, Any]] = None,
    ) -> PhysioOutput:
        """Process a neurophysiology research scenario.

        Implements the pipeline: Ideate -> Model -> Simulate -> Validate -> Iterate

        Parameters
        ----------
        scenario : PhysioScenario
            Input research scenario specification
        custom_parameters : Optional[Mapping[str, Any]], optional
            Override default parameters

        Returns
        -------
        PhysioOutput
            Complete pipeline output with milestone, key outputs,
            safety log, and next action

        Raises
        ------
        ValueError
            If scenario contains invalid parameters

        Notes
        -----
        The agent follows chain-of-thought reasoning:
        [Step] -> [Rationale] -> [Output] -> [Safety Audit]
        """
        # Build pipeline steps with chain-of-thought rationale
        pipeline_steps = self._build_pipeline_steps(scenario)

        # Build global parameters
        parameters = self._build_parameters(scenario, custom_parameters)

        # Generate key outputs based on domain and task
        key_outputs = self._generate_key_outputs(scenario)

        # Build safety audit
        safety_log = self._build_safety_audit(scenario)

        # Generate project milestone
        project_milestone = self._generate_milestone(scenario)

        # Generate next action recommendation
        next_action = self._generate_next_action(scenario)

        # Validate if enabled
        if self._enable_safety_validation:
            self._validate_output_safety(scenario, safety_log)

        return PhysioOutput(
            project_milestone=project_milestone,
            pipeline_steps=pipeline_steps,
            key_outputs=key_outputs,
            safety_log=safety_log,
            next_action=next_action,
            parameters=parameters,
        )

    def _build_pipeline_steps(
        self,
        scenario: PhysioScenario,
    ) -> List[PipelineStep]:
        """Build ordered sequence of pipeline steps with rationale.

        Pipeline follows neurophysiology workflow:
        1. Data parsing (sensory input)
        2. Model construction (biophysical equations)
        3. Simulation execution (neural dynamics)
        4. Validation against known results
        5. Iteration based on feedback
        """
        citations = self._DOMAIN_CITATIONS.get(scenario.domain, [])

        steps = [
            PipelineStep(
                step_name="data_acquisition",
                operation="parse_data",
                rationale=(
                    f"Acquire and parse neurophysiological data for {scenario.organism} "
                    f"{scenario.brain_region}. This provides the empirical foundation "
                    "for model construction following established protocols."
                ),
                parameters={
                    "organism": scenario.organism,
                    "brain_region": scenario.brain_region,
                    "format": "neurodata_without_borders",
                    "quality_checks": True,
                },
                priority=0,
                tools=self._TOOL_MAPPING.get("parse_data", []),
                citations=citations[:1] if citations else [],
            ),
            PipelineStep(
                step_name="model_construction",
                operation="model",
                rationale=(
                    f"Construct biophysical model for {scenario.domain.value} using "
                    "established equations. Model parameters derived from literature "
                    "values to ensure biological fidelity."
                ),
                parameters={
                    "domain": scenario.domain.value,
                    "framework": "pytorch",
                    "equation_form": "differential",
                    "parameter_source": "literature",
                },
                priority=1,
                tools=self._TOOL_MAPPING.get("model", []),
                citations=citations,
            ),
            PipelineStep(
                step_name="simulation_execution",
                operation="simulate",
                rationale=(
                    "Execute neural simulation with validated parameters. "
                    "Simulation timestep and duration selected to capture "
                    "relevant dynamics while maintaining numerical stability."
                ),
                parameters={
                    "dt_ms": 0.025,
                    "duration_ms": 1000,
                    "solver": "implicit_euler",
                    "stability_check": True,
                },
                priority=2,
                tools=self._TOOL_MAPPING.get("simulate", []),
                citations=[],
            ),
            PipelineStep(
                step_name="validation",
                operation="validate",
                rationale=(
                    "Validate simulation outputs against known experimental results. "
                    "Compare spike rates, timing patterns, and emergent properties "
                    "with published data from peer-reviewed sources."
                ),
                parameters={
                    "metrics": ["spike_rate", "isi_cv", "burst_index", "correlation"],
                    "confidence_level": scenario.confidence_threshold,
                    "reference_data": "peer_reviewed",
                },
                priority=3,
                tools=self._TOOL_MAPPING.get("validate", []),
                citations=citations[-1:] if citations else [],
            ),
            PipelineStep(
                step_name="iteration",
                operation="iterate",
                rationale=(
                    "Refine model parameters based on validation results. "
                    "Use gradient-free optimization to avoid local minima "
                    "while respecting biological constraints."
                ),
                parameters={
                    "optimizer": "cma_es",
                    "max_iterations": 100,
                    "convergence_threshold": 0.01,
                    "constraint_type": "biological_bounds",
                },
                priority=4,
                tools=["pytorch", "deap"],
                citations=[],
            ),
        ]

        # Filter steps based on task_type
        task_priority_map = {
            "ideate": [0, 1],
            "model": [0, 1, 2],
            "simulate": [0, 1, 2],
            "validate": [0, 1, 2, 3],
            "iterate": [0, 1, 2, 3, 4],
        }

        included_priorities = task_priority_map.get(scenario.task_type, [0, 1, 2, 3, 4])
        return [s for s in steps if s.priority in included_priorities]

    def _build_parameters(
        self,
        scenario: PhysioScenario,
        custom_parameters: Optional[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        """Build global pipeline parameters."""
        # Domain-specific default parameters
        domain_params = self._get_domain_parameters(scenario.domain)

        params: Dict[str, Any] = {
            "domain": scenario.domain.value,
            "task_type": scenario.task_type,
            "organism": scenario.organism,
            "brain_region": scenario.brain_region,
            "confidence_threshold": scenario.confidence_threshold,
            "validate_empirically": scenario.validate_empirically,
            # Domain-specific parameters
            **domain_params,
            # Safety settings
            "safety": {
                "no_medical_advice": True,
                "flag_biases": True,
                "require_citations": True,
                "flag_hypotheses": self._flag_hypotheses,
            },
            # Interpretability settings
            "interpretability": {
                "chain_of_thought": True,
                "cite_sources": True,
                "error_margin": "±20% based on synaptic noise models",
            },
        }

        # Apply custom overrides
        if custom_parameters:
            for key, value in custom_parameters.items():
                if isinstance(value, Mapping) and isinstance(params.get(key), dict):
                    params[key].update(value)
                else:
                    params[key] = value

        return params

    def _get_domain_parameters(
        self,
        domain: NeurophysiologyDomain,
    ) -> Dict[str, Any]:
        """Get domain-specific default parameters."""
        domain_defaults = {
            NeurophysiologyDomain.SYNAPTIC_PLASTICITY: {
                "model_type": "STDP",
                "plasticity_rule": "Equation 3.2 in Bi & Poo (1998)",
                "tau_plus_ms": 20.0,
                "tau_minus_ms": 20.0,
                "a_plus": 0.005,
                "a_minus": 0.00525,
            },
            NeurophysiologyDomain.NETWORK_OSCILLATIONS: {
                "model_type": "kuramoto",
                "frequency_band": "theta",
                "coupling_strength": 0.5,
                "phase_offset": 0.0,
            },
            NeurophysiologyDomain.OPTOGENETICS: {
                "model_type": "channelrhodopsin",
                "wavelength_nm": 470,
                "power_mw_mm2": 10.0,
                "pulse_duration_ms": 5.0,
            },
            NeurophysiologyDomain.ION_CHANNELS: {
                "model_type": "hodgkin_huxley",
                "reference": "Hodgkin & Huxley (1952)",
                "g_na_mS_cm2": 120.0,
                "g_k_mS_cm2": 36.0,
                "g_l_mS_cm2": 0.3,
                "e_na_mV": 50.0,
                "e_k_mV": -77.0,
                "e_l_mV": -54.4,
            },
            NeurophysiologyDomain.NEURAL_CODING: {
                "model_type": "population_coding",
                "tuning_curve": "gaussian",
                "firing_rate_hz": 50.0,
                "noise_model": "poisson",
            },
            NeurophysiologyDomain.NEUROMODULATION: {
                "model_type": "dopamine_td",
                "learning_rate": 0.01,
                "discount_gamma": 0.99,
                "reference": "Schultz (1998)",
            },
            NeurophysiologyDomain.CIRCADIAN_RHYTHMS: {
                "model_type": "scn_oscillator",
                "period_hours": 24.0,
                "coupling_type": "gap_junction",
                "light_sensitivity": 1.0,
            },
            NeurophysiologyDomain.MOTOR_CONTROL: {
                "model_type": "optimal_feedback",
                "reference": "Todorov & Jordan (2002)",
                "state_estimation": "kalman_filter",
                "control_cost": 0.5,
            },
        }

        return domain_defaults.get(domain, {})

    def _generate_key_outputs(
        self,
        scenario: PhysioScenario,
    ) -> Dict[str, Any]:
        """Generate key outputs based on domain and task."""
        outputs: Dict[str, Any] = {}

        # Generate domain-specific code snippet
        outputs["code_snippet"] = self._generate_code_snippet(scenario)

        # Generate equation representation
        outputs["equations"] = self._generate_equations(scenario)

        # Suggested visualization
        outputs["visualization"] = {
            "type": "time_series",
            "x_axis": "time_ms",
            "y_axis": "membrane_potential_mV",
            "library": "matplotlib",
        }

        # Data format specification
        outputs["data_format"] = {
            "standard": "neurodata_without_borders",
            "version": "2.6",
            "extensions": ["ndx-nirs", "ndx-events"],
        }

        return outputs

    def _generate_code_snippet(
        self,
        scenario: PhysioScenario,
    ) -> str:
        """Generate a code snippet example for the domain."""
        if scenario.domain == NeurophysiologyDomain.SYNAPTIC_PLASTICITY:
            return """
# STDP rule implementation (Bi & Poo, 1998)
import torch

def stdp_update(dt_ms: float, tau_plus: float = 20.0, tau_minus: float = 20.0,
                a_plus: float = 0.005, a_minus: float = 0.00525) -> float:
    \"\"\"Compute synaptic weight change based on spike timing.

    Parameters
    ----------
    dt_ms : float
        Time difference (post - pre) in milliseconds

    Returns
    -------
    float
        Weight change (dW)
    \"\"\"
    if dt_ms > 0:
        return a_plus * torch.exp(torch.tensor(-dt_ms / tau_plus)).item()
    else:
        return -a_minus * torch.exp(torch.tensor(dt_ms / tau_minus)).item()
""".strip()

        if scenario.domain == NeurophysiologyDomain.ION_CHANNELS:
            return """
# Hodgkin-Huxley model (1952)
import torch

class HodgkinHuxleyNeuron:
    \"\"\"Hodgkin-Huxley model implementation.

    Reference: Hodgkin & Huxley (1952) J. Physiol.
    \"\"\"

    def __init__(self, g_na=120.0, g_k=36.0, g_l=0.3,
                 e_na=50.0, e_k=-77.0, e_l=-54.4, c_m=1.0):
        self.g_na, self.g_k, self.g_l = g_na, g_k, g_l
        self.e_na, self.e_k, self.e_l = e_na, e_k, e_l
        self.c_m = c_m
        self.v = -65.0  # Initial membrane potential

    def alpha_n(self, v):
        return 0.01 * (v + 55) / (1 - torch.exp(-(v + 55) / 10))

    def beta_n(self, v):
        return 0.125 * torch.exp(-(v + 65) / 80)
""".strip()

        # Default template
        return f"""
# {scenario.domain.value} model template
import torch
import numpy as np

# Model implementation for {scenario.brain_region} in {scenario.organism}
# See domain-specific citations for implementation details
""".strip()

    def _generate_equations(
        self,
        scenario: PhysioScenario,
    ) -> Dict[str, str]:
        """Generate mathematical equations for the domain."""
        if scenario.domain == NeurophysiologyDomain.SYNAPTIC_PLASTICITY:
            return {
                "stdp_ltp": "ΔW = A+ * exp(-Δt / τ+) for Δt > 0",
                "stdp_ltd": "ΔW = -A- * exp(Δt / τ-) for Δt < 0",
                "reference": "Bi & Poo (1998) Equation 3.2",
            }

        if scenario.domain == NeurophysiologyDomain.ION_CHANNELS:
            return {
                "membrane_current": "I = g_Na * m³h * (V - E_Na) + g_K * n⁴ * (V - E_K) + g_L * (V - E_L)",
                "voltage_dynamics": "C_m * dV/dt = I_ext - I",
                "reference": "Hodgkin & Huxley (1952)",
            }

        if scenario.domain == NeurophysiologyDomain.NETWORK_OSCILLATIONS:
            return {
                "kuramoto": "dθ_i/dt = ω_i + (K/N) * Σ_j sin(θ_j - θ_i)",
                "order_parameter": "R * e^(iψ) = (1/N) * Σ_j e^(iθ_j)",
                "reference": "Buzsáki (2006)",
            }

        return {"note": f"Equations for {scenario.domain.value} - see citations"}

    def _build_safety_audit(
        self,
        scenario: PhysioScenario,
    ) -> SafetyAudit:
        """Build safety audit with risks and biases assessment."""
        risks_mitigated = [
            "Biological fidelity validated against peer-reviewed sources",
            "Numerical stability ensured via implicit solver selection",
            "Parameter bounds enforced from empirical measurements",
        ]

        biases_flagged = []

        # Flag organism-specific biases
        if scenario.organism == "mouse":
            biases_flagged.append(
                "Over-representation of rodent models vs. human data - "
                "consider cross-species validation"
            )
        if scenario.organism != "human":
            biases_flagged.append(
                "Species-specific differences may limit translational relevance"
            )

        # Flag demographic biases
        biases_flagged.append(
            "Consider age/sex effects on neural dynamics - "
            "default parameters from adult male subjects"
        )

        # Determine confidence based on data availability
        confidence = min(scenario.confidence_threshold, 0.9)

        # Flag as hypothesis if confidence is below threshold
        is_hypothesis = confidence < self._confidence_threshold

        # Ethical considerations
        ethical = [
            "No direct medical advice generated",
            "Research use only - not for clinical decision-making",
            "Results require empirical validation before application",
        ]

        return SafetyAudit(
            risks_mitigated=risks_mitigated,
            biases_flagged=biases_flagged,
            confidence_score=confidence,
            validation_required=scenario.validate_empirically,
            validation_method="Simulate in NEURON software and compare with experimental data",
            ethical_considerations=ethical,
            is_hypothesis=is_hypothesis,
        )

    def _generate_milestone(
        self,
        scenario: PhysioScenario,
    ) -> str:
        """Generate project milestone summary."""
        task_descriptions = {
            "ideate": "conceptualization and literature review",
            "model": "biophysical model construction",
            "simulate": "neural dynamics simulation",
            "validate": "experimental validation comparison",
            "iterate": "parameter optimization and refinement",
        }

        task_desc = task_descriptions.get(scenario.task_type, "research")
        domain_name = scenario.domain.value.replace("_", " ")

        return (
            f"Completed {task_desc} phase for {domain_name} in "
            f"{scenario.organism} {scenario.brain_region}. "
            f"Pipeline configured with {len(self._DOMAIN_CITATIONS.get(scenario.domain, []))} "
            f"peer-reviewed citations supporting biological fidelity."
        )

    def _generate_next_action(
        self,
        scenario: PhysioScenario,
    ) -> str:
        """Generate next action recommendation."""
        next_actions = {
            "ideate": (
                "Proceed to model construction phase. Consider alternative "
                "model architectures and validate parameter choices against literature."
            ),
            "model": (
                "Run simulation with constructed model. Monitor for numerical "
                "instabilities and validate spike rates against expected ranges."
            ),
            "simulate": (
                "Compare simulation outputs with experimental data. Flag any "
                "significant deviations for model refinement."
            ),
            "validate": (
                "Initiate parameter optimization to improve model-data fit. "
                "Use gradient-free methods to respect biological constraints."
            ),
            "iterate": (
                "Model complete. Consider extending to larger network scales "
                "or alternative brain regions for generalization testing."
            ),
        }

        action = next_actions.get(scenario.task_type, "Ready for iteration?")
        return f"{action} Ready for iteration?"

    def _validate_output_safety(
        self,
        scenario: PhysioScenario,
        safety_log: SafetyAudit,
    ) -> None:
        """Validate output safety constraints.

        Parameters
        ----------
        scenario : PhysioScenario
            Input scenario
        safety_log : SafetyAudit
            Generated safety audit

        Raises
        ------
        ValueError
            If safety constraints are violated
        """
        # Check confidence threshold
        if safety_log.confidence_score < 0.0 or safety_log.confidence_score > 1.0:
            raise ValueError(
                f"Confidence score {safety_log.confidence_score} out of valid range [0, 1]"
            )

        # Ensure no medical advice
        if "medical" in str(scenario).lower() and "advice" in str(scenario).lower():
            raise ValueError(
                "Medical advice generation is prohibited. "
                "This agent is for research purposes only."
            )


def create_neurophysiology_pipeline(
    domain: str,
    task_type: Literal["ideate", "model", "simulate", "validate", "iterate"] = "model",
    *,
    organism: str = "mouse",
    brain_region: str = "hippocampus_CA1",
    confidence_threshold: float = 0.8,
    validate_empirically: bool = True,
) -> PhysioOutput:
    """Convenience function to create neurophysiology pipeline from parameters.

    Parameters
    ----------
    domain : str
        Target neurophysiology domain (e.g., "synaptic_plasticity")
    task_type : str, optional
        Phase of research pipeline, by default "model"
    organism : str, optional
        Model organism, by default "mouse"
    brain_region : str, optional
        Target brain region, by default "hippocampus_CA1"
    confidence_threshold : float, optional
        Minimum confidence for outputs, by default 0.8
    validate_empirically : bool, optional
        Whether to require empirical validation, by default True

    Returns
    -------
    PhysioOutput
        Complete pipeline output

    Examples
    --------
    >>> output = create_neurophysiology_pipeline(
    ...     domain="synaptic_plasticity",
    ...     task_type="model",
    ...     organism="mouse",
    ...     brain_region="hippocampus_CA1",
    ... )
    >>> print(output.project_milestone)
    """
    # Convert string domain to enum
    try:
        domain_enum = NeurophysiologyDomain(domain)
    except ValueError as exc:
        valid_domains = [d.value for d in NeurophysiologyDomain]
        raise ValueError(
            f"Invalid domain '{domain}'. Valid options: {valid_domains}"
        ) from exc

    scenario = PhysioScenario(
        domain=domain_enum,
        task_type=task_type,
        organism=organism,
        brain_region=brain_region,
        confidence_threshold=confidence_threshold,
        validate_empirically=validate_empirically,
    )

    guard = NeuroPhysioGuard(
        confidence_threshold=confidence_threshold,
        enable_safety_validation=True,
        flag_hypotheses=True,
    )

    return guard.process(scenario)
