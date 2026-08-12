from __future__ import annotations

from dataclasses import dataclass

from runtime.rebus_gate import RebusConfig, RebusGate

REBUS_PROTOCOL_NAME = "rebus_v1"


@dataclass(frozen=True)
class ProtocolRegistration:
    name: str
    version: str
    descriptor: dict[str, object]


_PROTOCOL_REGISTRY: dict[str, ProtocolRegistration] = {}


def build_protocol(config: RebusConfig | None = None) -> dict[str, object]:
    resolved_config = config or RebusConfig()
    gate = RebusGate(config=resolved_config)
    return {
        "name": REBUS_PROTOCOL_NAME,
        "version": "1.0",
        "gate": gate,
        "activation_conditions": {
            "requires_nominal": True,
            "min_coherence_baseline": resolved_config.activation_coherence_threshold,
            "max_concurrent_instances": 1,
            "stressed_state_blocked": True,
        },
        "safety": {
            "kill_switch_forces_emergency_exit": True,
            "stressed_state_forces_emergency_exit": True,
            "max_entropy_ceiling": 0.35,
            "reintegration_required": True,
            "attenuated_apply_confirmation_required": True,
            "restore_apply_confirmation_required": True,
        },
    }


def register_protocol(config: RebusConfig | None = None) -> ProtocolRegistration:
    descriptor = build_protocol(config)
    registration = ProtocolRegistration(
        name=str(descriptor["name"]),
        version=str(descriptor["version"]),
        descriptor=descriptor,
    )
    _PROTOCOL_REGISTRY[registration.name] = registration
    return registration


def get_registered_protocol(
    name: str = REBUS_PROTOCOL_NAME,
) -> ProtocolRegistration | None:
    return _PROTOCOL_REGISTRY.get(name)


def clear_registered_protocols() -> None:
    _PROTOCOL_REGISTRY.clear()


def apply_external_controller(
    gate: RebusGate,
    *,
    kill_switch_active: bool,
    stressed_state: bool,
) -> dict[str, float] | None:
    return gate.apply_external_safety_signal(
        kill_switch_active=kill_switch_active,
        stressed_state=stressed_state,
    )


def protocol_schema_keys() -> dict[str, tuple[str, ...]]:
    return {
        "root": ("name", "version", "gate", "activation_conditions", "safety"),
        "activation_conditions": (
            "requires_nominal",
            "min_coherence_baseline",
            "max_concurrent_instances",
            "stressed_state_blocked",
        ),
        "safety": (
            "kill_switch_forces_emergency_exit",
            "stressed_state_forces_emergency_exit",
            "max_entropy_ceiling",
            "reintegration_required",
            "attenuated_apply_confirmation_required",
            "restore_apply_confirmation_required",
        ),
    }
