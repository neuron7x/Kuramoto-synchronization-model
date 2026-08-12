from __future__ import annotations

from typing import TypedDict


class ModuleInfo(TypedDict):
    version: str
    order: int


MODULES: dict[str, ModuleInfo] = {
    "intent": {"version": "0.1.0", "order": 10},
    "reflection": {"version": "0.1.0", "order": 20},
    "introspection": {"version": "0.1.0", "order": 30},
    "reverse_inference": {"version": "0.1.0", "order": 40},
    "extrapolation": {"version": "0.1.0", "order": 50},
    "artifact_builder": {"version": "0.1.0", "order": 60},
    "safety": {"version": "0.1.0", "order": 70},
}


def module_exists(module_id: str) -> bool:
    return module_id in MODULES


def ordered_modules() -> list[str]:
    return [name for name, _ in sorted(MODULES.items(), key=lambda item: item[1]["order"])]
