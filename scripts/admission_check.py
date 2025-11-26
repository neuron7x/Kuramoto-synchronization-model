"""CI gate ensuring thermodynamic monotonicity invariants hold."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Tuple

import networkx as nx

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[0]

if str(SCRIPT_DIR) in sys.path:
    sys.path.remove(str(SCRIPT_DIR))

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.thermo_controller import MetricsSnapshot, ThermoController  # noqa: E402


def _compute_epsilon_spike(controller: ThermoController, F_old: float) -> float:
    return controller._monotonic_tolerance_budget(F_old)


def _build_reference_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node("alpha", cpu_norm=0.6)
    graph.add_node("beta", cpu_norm=0.55)
    graph.add_node("gamma", cpu_norm=0.5)
    graph.add_node("delta", cpu_norm=0.52)
    graph.add_edge("alpha", "beta", type="metallic", latency_norm=0.9, coherency=0.7)
    graph.add_edge("beta", "gamma", type="hydrogen", latency_norm=1.1, coherency=0.6)
    graph.add_edge("gamma", "delta", type="metallic", latency_norm=0.85, coherency=0.65)
    graph.add_edge("delta", "alpha", type="hydrogen", latency_norm=1.2, coherency=0.6)
    graph.add_edge("alpha", "gamma", type="metallic", latency_norm=1.0, coherency=0.68)
    return graph


def _degrade_topology(
    controller: ThermoController,
) -> Tuple[MetricsSnapshot, list[tuple[str, str, str]]]:
    snapshot = MetricsSnapshot(
        latencies=dict(controller._latest_snapshot.latencies),
        coherency=dict(controller._latest_snapshot.coherency),
        resource_usage=controller._latest_snapshot.resource_usage,
        entropy=controller._latest_snapshot.entropy,
    )
    topology = list(controller.current_topology)
    threshold = max(1, int(0.2 * len(topology)))
    degraded: list[tuple[str, str, str]] = []
    for idx, (src, dst, bond) in enumerate(topology):
        if idx < threshold:
            degraded.append((src, dst, "covalent"))
        else:
            degraded.append((src, dst, "ionic"))
    return snapshot, degraded


def _validate_monotonic_acceptance() -> bool:
    controller = ThermoController(_build_reference_graph())
    F_old = controller._compute_free_energy(snapshot=controller._latest_snapshot)
    new_topology, F_new, _ = controller.crisis_ga.evolve(
        controller.current_topology, F_old
    )
    epsilon_spike = _compute_epsilon_spike(controller, F_old)

    tolerance = controller._check_monotonic_with_tolerance(F_old, F_new)
    if not tolerance.accepted:
        print(
            "Thermodynamic gate rejected GA proposal:",
            tolerance.reason,
            file=sys.stderr,
        )
        return False

    if F_new > F_old + epsilon_spike:
        print(
            "Thermodynamic gate detected free energy regression:",
            f"F_old={F_old:.6e}",
            f"F_new={F_new:.6e}",
            f"epsilon={epsilon_spike:.6e}",
            file=sys.stderr,
        )
        return False

    return True


def _validate_monotonic_rejection() -> bool:
    controller = ThermoController(_build_reference_graph())
    snapshot, degraded = _degrade_topology(controller)
    F_old = controller._compute_free_energy(snapshot=snapshot)
    F_bad = controller._compute_free_energy(topology=degraded, snapshot=snapshot)

    tolerance = controller._check_monotonic_with_tolerance(F_old, F_bad)
    if tolerance.accepted:
        print(
            "Thermodynamic gate failed to reject degraded topology:",
            tolerance.reason,
            f"F_old={F_old:.6e}",
            f"F_bad={F_bad:.6e}",
            file=sys.stderr,
        )
        return False

    return True


def main() -> int:
    acceptance_ok = _validate_monotonic_acceptance()
    rejection_ok = _validate_monotonic_rejection()

    if not (acceptance_ok and rejection_ok):
        return 1

    print("Thermodynamic admission check passed: monotonic invariants respected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
