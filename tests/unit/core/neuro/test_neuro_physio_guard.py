"""Tests for the NeuroPhysioGuard agent."""

from __future__ import annotations

import json

import pytest

from tradepulse.core.neuro.neuro_physio_guard import (
    NeuroPhysioGuard,
    NeurophysiologyDomain,
    PhysioOutput,
    PhysioScenario,
    PipelineStep,
    SafetyAudit,
    create_neurophysiology_pipeline,
)


class TestPhysioScenario:
    """Test PhysioScenario dataclass."""

    def test_basic_scenario(self):
        """Test basic scenario creation."""
        scenario = PhysioScenario(
            domain=NeurophysiologyDomain.SYNAPTIC_PLASTICITY,
            task_type="model",
        )
        assert scenario.domain == NeurophysiologyDomain.SYNAPTIC_PLASTICITY
        assert scenario.task_type == "model"
        assert scenario.organism == "mouse"
        assert scenario.brain_region == "hippocampus_CA1"
        assert scenario.confidence_threshold == 0.8
        assert scenario.validate_empirically is True

    def test_custom_scenario(self):
        """Test scenario with custom parameters."""
        scenario = PhysioScenario(
            domain=NeurophysiologyDomain.ION_CHANNELS,
            task_type="simulate",
            organism="rat",
            brain_region="prefrontal_cortex",
            confidence_threshold=0.9,
            validate_empirically=False,
        )
        assert scenario.organism == "rat"
        assert scenario.brain_region == "prefrontal_cortex"
        assert scenario.confidence_threshold == 0.9
        assert scenario.validate_empirically is False


class TestNeurophysiologyDomain:
    """Test NeurophysiologyDomain enum."""

    def test_all_domains_defined(self):
        """Test all expected domains are defined."""
        expected_domains = {
            "synaptic_plasticity",
            "network_oscillations",
            "optogenetics",
            "ion_channels",
            "neural_coding",
            "neuromodulation",
            "circadian_rhythms",
            "motor_control",
        }
        actual_domains = {d.value for d in NeurophysiologyDomain}
        assert actual_domains == expected_domains

    def test_domain_string_conversion(self):
        """Test domain string conversion."""
        domain = NeurophysiologyDomain.SYNAPTIC_PLASTICITY
        assert domain.value == "synaptic_plasticity"
        assert str(domain) == "NeurophysiologyDomain.SYNAPTIC_PLASTICITY"


class TestPipelineStep:
    """Test PipelineStep dataclass."""

    def test_pipeline_step_creation(self):
        """Test pipeline step creation."""
        step = PipelineStep(
            step_name="data_acquisition",
            operation="parse_data",
            rationale="Acquire neurophysiology data",
            parameters={"format": "nwb"},
            priority=0,
            tools=["biopython", "scipy"],
            citations=["Bi & Poo (1998)"],
        )
        assert step.step_name == "data_acquisition"
        assert step.operation == "parse_data"
        assert step.priority == 0
        assert "biopython" in step.tools
        assert len(step.citations) == 1

    def test_pipeline_step_defaults(self):
        """Test pipeline step with defaults."""
        step = PipelineStep(
            step_name="test",
            operation="test_op",
            rationale="Test rationale",
            parameters={},
        )
        assert step.priority == 0
        assert step.tools == []
        assert step.citations == []


class TestSafetyAudit:
    """Test SafetyAudit dataclass."""

    def test_safety_audit_creation(self):
        """Test safety audit creation."""
        audit = SafetyAudit(
            risks_mitigated=["Biological fidelity validated"],
            biases_flagged=["Rodent model bias"],
            confidence_score=0.85,
        )
        assert len(audit.risks_mitigated) == 1
        assert len(audit.biases_flagged) == 1
        assert audit.confidence_score == 0.85
        assert audit.validation_required is True
        assert "NEURON" in audit.validation_method

    def test_safety_audit_hypothesis_flag(self):
        """Test safety audit hypothesis flagging."""
        audit = SafetyAudit(
            risks_mitigated=[],
            biases_flagged=[],
            confidence_score=0.5,
            is_hypothesis=True,
        )
        assert audit.is_hypothesis is True


class TestNeuroPhysioGuard:
    """Test NeuroPhysioGuard agent."""

    def test_guard_initialization(self):
        """Test guard initialization with defaults."""
        guard = NeuroPhysioGuard()
        assert guard._confidence_threshold == 0.8
        assert guard._enable_safety_validation is True
        assert guard._flag_hypotheses is True

    def test_guard_custom_initialization(self):
        """Test guard initialization with custom parameters."""
        guard = NeuroPhysioGuard(
            confidence_threshold=0.9,
            enable_safety_validation=False,
            flag_hypotheses=False,
        )
        assert guard._confidence_threshold == 0.9
        assert guard._enable_safety_validation is False
        assert guard._flag_hypotheses is False

    def test_guard_invalid_confidence_threshold(self):
        """Test guard rejects invalid confidence threshold."""
        with pytest.raises(ValueError, match="confidence_threshold must be between 0 and 1"):
            NeuroPhysioGuard(confidence_threshold=1.5)

        with pytest.raises(ValueError, match="confidence_threshold must be between 0 and 1"):
            NeuroPhysioGuard(confidence_threshold=-0.1)

    def test_process_synaptic_plasticity(self):
        """Test processing synaptic plasticity scenario."""
        guard = NeuroPhysioGuard()
        scenario = PhysioScenario(
            domain=NeurophysiologyDomain.SYNAPTIC_PLASTICITY,
            task_type="model",
        )
        output = guard.process(scenario)

        assert isinstance(output, PhysioOutput)
        assert "synaptic plasticity" in output.project_milestone.lower()
        assert len(output.pipeline_steps) > 0
        assert output.safety_log.confidence_score > 0
        assert "Bi & Poo" in output.key_outputs["code_snippet"]

    def test_process_ion_channels(self):
        """Test processing ion channels scenario."""
        guard = NeuroPhysioGuard()
        scenario = PhysioScenario(
            domain=NeurophysiologyDomain.ION_CHANNELS,
            task_type="model",
        )
        output = guard.process(scenario)

        assert "ion channels" in output.project_milestone.lower()
        assert "Hodgkin" in output.key_outputs["code_snippet"]
        # Check equations reference Hodgkin-Huxley
        assert "Hodgkin" in str(output.key_outputs["equations"])

    def test_process_network_oscillations(self):
        """Test processing network oscillations scenario."""
        guard = NeuroPhysioGuard()
        scenario = PhysioScenario(
            domain=NeurophysiologyDomain.NETWORK_OSCILLATIONS,
            task_type="simulate",
        )
        output = guard.process(scenario)

        assert "network oscillations" in output.project_milestone.lower()
        assert "kuramoto" in str(output.key_outputs["equations"]).lower()

    def test_process_optogenetics(self):
        """Test processing optogenetics scenario."""
        guard = NeuroPhysioGuard()
        scenario = PhysioScenario(
            domain=NeurophysiologyDomain.OPTOGENETICS,
            task_type="model",
        )
        output = guard.process(scenario)

        assert "optogenetics" in output.project_milestone.lower()
        assert output.parameters.get("wavelength_nm") == 470

    def test_pipeline_steps_ordered_by_priority(self):
        """Test pipeline steps are ordered by priority."""
        guard = NeuroPhysioGuard()
        scenario = PhysioScenario(
            domain=NeurophysiologyDomain.SYNAPTIC_PLASTICITY,
            task_type="iterate",  # Full pipeline
        )
        output = guard.process(scenario)

        priorities = [step.priority for step in output.pipeline_steps]
        assert priorities == sorted(priorities)

    def test_task_type_filters_steps(self):
        """Test different task types filter pipeline steps."""
        guard = NeuroPhysioGuard()

        # Ideate should have fewer steps
        ideate = guard.process(
            PhysioScenario(
                domain=NeurophysiologyDomain.SYNAPTIC_PLASTICITY,
                task_type="ideate",
            )
        )

        # Iterate should have all steps
        iterate = guard.process(
            PhysioScenario(
                domain=NeurophysiologyDomain.SYNAPTIC_PLASTICITY,
                task_type="iterate",
            )
        )

        assert len(ideate.pipeline_steps) < len(iterate.pipeline_steps)

    def test_bias_flagging_for_rodent_models(self):
        """Test bias flagging for rodent models."""
        guard = NeuroPhysioGuard()
        scenario = PhysioScenario(
            domain=NeurophysiologyDomain.SYNAPTIC_PLASTICITY,
            task_type="model",
            organism="mouse",
        )
        output = guard.process(scenario)

        biases = output.safety_log.biases_flagged
        assert any("rodent" in bias.lower() for bias in biases)

    def test_species_specific_bias_flagging(self):
        """Test species-specific bias flagging for non-human models."""
        guard = NeuroPhysioGuard()
        scenario = PhysioScenario(
            domain=NeurophysiologyDomain.SYNAPTIC_PLASTICITY,
            task_type="model",
            organism="c_elegans",
        )
        output = guard.process(scenario)

        biases = output.safety_log.biases_flagged
        assert any("species" in bias.lower() for bias in biases)

    def test_age_sex_bias_flagging(self):
        """Test age/sex bias flagging."""
        guard = NeuroPhysioGuard()
        scenario = PhysioScenario(
            domain=NeurophysiologyDomain.SYNAPTIC_PLASTICITY,
            task_type="model",
        )
        output = guard.process(scenario)

        biases = output.safety_log.biases_flagged
        assert any("age" in bias.lower() or "sex" in bias.lower() for bias in biases)

    def test_ethical_considerations_included(self):
        """Test ethical considerations are included."""
        guard = NeuroPhysioGuard()
        scenario = PhysioScenario(
            domain=NeurophysiologyDomain.SYNAPTIC_PLASTICITY,
            task_type="model",
        )
        output = guard.process(scenario)

        ethics = output.safety_log.ethical_considerations
        assert len(ethics) > 0
        assert any("medical advice" in e.lower() for e in ethics)
        assert any("research" in e.lower() for e in ethics)

    def test_next_action_generated(self):
        """Test next action is generated for each task type."""
        guard = NeuroPhysioGuard()

        for task_type in ["ideate", "model", "simulate", "validate", "iterate"]:
            scenario = PhysioScenario(
                domain=NeurophysiologyDomain.SYNAPTIC_PLASTICITY,
                task_type=task_type,
            )
            output = guard.process(scenario)
            assert "Ready for iteration?" in output.next_action
            assert len(output.next_action) > 20

    def test_custom_parameters_applied(self):
        """Test custom parameters are applied."""
        guard = NeuroPhysioGuard()
        scenario = PhysioScenario(
            domain=NeurophysiologyDomain.SYNAPTIC_PLASTICITY,
            task_type="model",
        )
        custom_params = {"custom_key": "custom_value"}
        output = guard.process(scenario, custom_parameters=custom_params)

        assert output.parameters.get("custom_key") == "custom_value"

    def test_domain_specific_parameters(self):
        """Test domain-specific parameters are set."""
        guard = NeuroPhysioGuard()

        # Test STDP parameters for synaptic plasticity
        scenario = PhysioScenario(
            domain=NeurophysiologyDomain.SYNAPTIC_PLASTICITY,
            task_type="model",
        )
        output = guard.process(scenario)
        assert "tau_plus_ms" in output.parameters
        assert "tau_minus_ms" in output.parameters

        # Test HH parameters for ion channels
        scenario = PhysioScenario(
            domain=NeurophysiologyDomain.ION_CHANNELS,
            task_type="model",
        )
        output = guard.process(scenario)
        assert "g_na_mS_cm2" in output.parameters
        assert output.parameters.get("g_na_mS_cm2") == 120.0

    def test_citations_included(self):
        """Test citations are included in pipeline steps."""
        guard = NeuroPhysioGuard()
        scenario = PhysioScenario(
            domain=NeurophysiologyDomain.SYNAPTIC_PLASTICITY,
            task_type="model",
        )
        output = guard.process(scenario)

        all_citations = []
        for step in output.pipeline_steps:
            all_citations.extend(step.citations)

        assert len(all_citations) > 0
        assert any("Bi & Poo" in citation for citation in all_citations)

    def test_tools_specified(self):
        """Test AI tools are specified for each step."""
        guard = NeuroPhysioGuard()
        scenario = PhysioScenario(
            domain=NeurophysiologyDomain.SYNAPTIC_PLASTICITY,
            task_type="iterate",
        )
        output = guard.process(scenario)

        for step in output.pipeline_steps:
            # Each step should have tools specified
            assert isinstance(step.tools, list)

    def test_safety_parameters_included(self):
        """Test safety parameters are included in output."""
        guard = NeuroPhysioGuard()
        scenario = PhysioScenario(
            domain=NeurophysiologyDomain.SYNAPTIC_PLASTICITY,
            task_type="model",
        )
        output = guard.process(scenario)

        assert "safety" in output.parameters
        safety = output.parameters["safety"]
        assert safety.get("no_medical_advice") is True
        assert safety.get("flag_biases") is True
        assert safety.get("require_citations") is True

    def test_interpretability_parameters_included(self):
        """Test interpretability parameters are included."""
        guard = NeuroPhysioGuard()
        scenario = PhysioScenario(
            domain=NeurophysiologyDomain.SYNAPTIC_PLASTICITY,
            task_type="model",
        )
        output = guard.process(scenario)

        assert "interpretability" in output.parameters
        interp = output.parameters["interpretability"]
        assert interp.get("chain_of_thought") is True
        assert interp.get("cite_sources") is True
        assert "±20%" in interp.get("error_margin", "")


class TestPhysioOutput:
    """Test PhysioOutput dataclass."""

    def test_to_json(self):
        """Test JSON serialization."""
        guard = NeuroPhysioGuard()
        scenario = PhysioScenario(
            domain=NeurophysiologyDomain.SYNAPTIC_PLASTICITY,
            task_type="model",
        )
        output = guard.process(scenario)

        json_str = output.to_json()
        parsed = json.loads(json_str)

        assert "project_milestone" in parsed
        assert "pipeline_steps" in parsed
        assert "key_outputs" in parsed
        assert "safety_log" in parsed
        assert "next_action" in parsed
        assert "parameters" in parsed

    def test_json_contains_all_required_fields(self):
        """Test JSON contains all required output format fields."""
        guard = NeuroPhysioGuard()
        scenario = PhysioScenario(
            domain=NeurophysiologyDomain.SYNAPTIC_PLASTICITY,
            task_type="model",
        )
        output = guard.process(scenario)

        json_str = output.to_json()
        parsed = json.loads(json_str)

        # Required fields per the problem statement
        assert "project_milestone" in parsed  # Project Milestone
        assert "key_outputs" in parsed  # Key Outputs
        assert "safety_log" in parsed  # Safety Log
        assert "next_action" in parsed  # Next Action

        # Safety log should have confidence score
        assert "confidence_score" in parsed["safety_log"]
        assert 0.0 <= parsed["safety_log"]["confidence_score"] <= 1.0


class TestCreateNeurophysiologyPipeline:
    """Test the convenience function."""

    def test_basic_usage(self):
        """Test basic convenience function usage."""
        output = create_neurophysiology_pipeline(
            domain="synaptic_plasticity",
            task_type="model",
        )
        assert isinstance(output, PhysioOutput)
        assert len(output.pipeline_steps) > 0

    def test_all_domains(self):
        """Test convenience function works for all domains."""
        for domain in NeurophysiologyDomain:
            output = create_neurophysiology_pipeline(
                domain=domain.value,
                task_type="model",
            )
            assert isinstance(output, PhysioOutput)

    def test_invalid_domain(self):
        """Test invalid domain raises error."""
        with pytest.raises(ValueError, match="Invalid domain"):
            create_neurophysiology_pipeline(
                domain="invalid_domain",
                task_type="model",
            )

    def test_custom_organism_and_region(self):
        """Test custom organism and brain region."""
        output = create_neurophysiology_pipeline(
            domain="ion_channels",
            task_type="simulate",
            organism="rat",
            brain_region="motor_cortex",
        )
        assert output.parameters.get("organism") == "rat"
        assert output.parameters.get("brain_region") == "motor_cortex"

    def test_custom_confidence_threshold(self):
        """Test custom confidence threshold."""
        output = create_neurophysiology_pipeline(
            domain="synaptic_plasticity",
            task_type="model",
            confidence_threshold=0.95,
        )
        assert output.parameters.get("confidence_threshold") == 0.95


class TestDomainSpecificBehavior:
    """Test domain-specific behavior."""

    def test_hodgkin_huxley_parameters(self):
        """Test Hodgkin-Huxley parameters for ion channels."""
        output = create_neurophysiology_pipeline(
            domain="ion_channels",
            task_type="model",
        )
        # Check HH standard values
        assert output.parameters.get("g_na_mS_cm2") == 120.0
        assert output.parameters.get("g_k_mS_cm2") == 36.0
        assert output.parameters.get("g_l_mS_cm2") == 0.3
        assert output.parameters.get("e_na_mV") == 50.0
        assert output.parameters.get("e_k_mV") == -77.0

    def test_stdp_parameters(self):
        """Test STDP parameters for synaptic plasticity."""
        output = create_neurophysiology_pipeline(
            domain="synaptic_plasticity",
            task_type="model",
        )
        assert output.parameters.get("tau_plus_ms") == 20.0
        assert output.parameters.get("tau_minus_ms") == 20.0
        assert "Bi & Poo" in output.parameters.get("plasticity_rule", "")

    def test_kuramoto_parameters(self):
        """Test Kuramoto oscillator parameters for network oscillations."""
        output = create_neurophysiology_pipeline(
            domain="network_oscillations",
            task_type="model",
        )
        assert output.parameters.get("model_type") == "kuramoto"
        assert "coupling_strength" in output.parameters

    def test_optogenetics_parameters(self):
        """Test optogenetics parameters."""
        output = create_neurophysiology_pipeline(
            domain="optogenetics",
            task_type="model",
        )
        assert output.parameters.get("wavelength_nm") == 470
        assert "power_mw_mm2" in output.parameters

    def test_dopamine_td_parameters(self):
        """Test dopamine TD parameters for neuromodulation."""
        output = create_neurophysiology_pipeline(
            domain="neuromodulation",
            task_type="model",
        )
        assert output.parameters.get("model_type") == "dopamine_td"
        assert "learning_rate" in output.parameters
        assert "Schultz" in output.parameters.get("reference", "")

    def test_circadian_parameters(self):
        """Test circadian rhythm parameters."""
        output = create_neurophysiology_pipeline(
            domain="circadian_rhythms",
            task_type="model",
        )
        assert output.parameters.get("period_hours") == 24.0
        assert output.parameters.get("coupling_type") == "gap_junction"

    def test_motor_control_parameters(self):
        """Test motor control parameters."""
        output = create_neurophysiology_pipeline(
            domain="motor_control",
            task_type="model",
        )
        assert output.parameters.get("model_type") == "optimal_feedback"
        assert "Todorov" in output.parameters.get("reference", "")
