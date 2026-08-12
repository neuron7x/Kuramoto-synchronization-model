from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RIEEMode:
    name: str
    description: str


def supported_modes() -> list[RIEEMode]:
    return [
        RIEEMode(
            "cloud_native",
            "Kubernetes/Mesh sidecar integration contract (workflow/guard orchestration).",
        ),
        RIEEMode("local_edge", "Local daemon/CLI enforcement around runtime guards."),
        RIEEMode(
            "application_sdk",
            "Python decorator SDK via runtime.riee.sdk.riee_guard and RIEE_ENABLE=1.",
        ),
    ]


if __name__ == "__main__":
    for mode in supported_modes():
        print(f"{mode.name}: {mode.description}")
