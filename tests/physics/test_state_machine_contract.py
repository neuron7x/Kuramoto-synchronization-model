from core.physics.cognitive_core import CognitiveCore as _Core

_FULL = {
    "order_parameter_R": 0.5,
    "z_abs": 0.4,
    "ollivier_kappa": 0.2,
    "gamma": 1.5,
    "serotonin_level": 0.3,
    "gaba_gate": 0.8,
    "dopamine_signal": 0.5,
    "kelly_fraction": 0.25,
    "free_energy_components": (1.0, 0.5, 0.2),
}


def test_complete_state_passes() -> None:
    assert _Core().admissibility(_FULL).admissible is True


def test_single_field_state_fails() -> None:
    verdict = _Core().admissibility({"order_parameter_R": 0.5})
    assert verdict.admissible is False
    assert verdict.status.value == "INADMISSIBLE"
