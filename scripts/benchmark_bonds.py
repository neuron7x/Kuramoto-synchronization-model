from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

import networkx as nx

# ``python scripts/benchmark_bonds.py`` sets ``sys.path[0]`` to the ``scripts``
# directory, which omits the project root and shadows the top-level ``runtime``
# namespace with ``scripts/runtime``. Normalise the path order so that imports
# resolve against the repository packages without requiring PYTHONPATH tweaks.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[0]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

script_dir_str = str(SCRIPT_DIR)
if script_dir_str in sys.path:
    sys.path.remove(script_dir_str)

from core.energy import delta_free_energy  # noqa: E402 - after sys.path setup
from runtime.thermo_controller import ThermoController  # noqa: E402


def run_benchmark(iterations: int = 200) -> dict[str, float | int]:
    graph = nx.DiGraph()
    graph.add_node("ingest", cpu_norm=0.4)
    graph.add_node("matcher", cpu_norm=0.6)
    graph.add_node("risk", cpu_norm=0.5)
    graph.add_node("broker", cpu_norm=0.3)
    graph.add_node("audit", cpu_norm=0.7)

    graph.add_edge(
        "ingest", "matcher", type="covalent", latency_norm=0.4, coherency=0.92
    )
    graph.add_edge("matcher", "risk", type="ionic", latency_norm=0.8, coherency=0.71)
    graph.add_edge("risk", "broker", type="metallic", latency_norm=0.15, coherency=0.88)
    graph.add_edge("broker", "audit", type="hydrogen", latency_norm=1.2, coherency=0.63)
    graph.add_edge("audit", "ingest", type="vdw", latency_norm=0.9, coherency=0.5)

    controller = ThermoController(graph)
    dFdt_values: list[float] = []

    controller.control_step()
    prev_F = controller.prev_F
    prev_t = controller.prev_t

    for _ in range(iterations):
        controller.control_step()
        new_F = controller.prev_F
        new_t = controller.prev_t
        if prev_F is None or prev_t is None or new_F is None or new_t is None:
            continue
        dFdt = delta_free_energy(prev_F, new_F, new_t - prev_t)
        dFdt_values.append(dFdt)
        prev_F, prev_t = new_F, new_t
        time.sleep(0.0005)

    if not dFdt_values:
        raise RuntimeError("No dF/dt samples collected during benchmark")

    return {
        "dFdt_mean": statistics.mean(dFdt_values),
        "dFdt_min": min(dFdt_values),
        "dFdt_max": max(dFdt_values),
        "samples": len(dFdt_values),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-dF", type=float, default=1e-10)
    parser.add_argument("--iterations", type=int, default=200)
    args = parser.parse_args()

    metrics = run_benchmark(iterations=args.iterations)
    print("[benchmark_bonds] metrics:", metrics)

    mean_abs = abs(metrics["dFdt_mean"])
    if mean_abs > args.target_dF:
        raise SystemExit(
            f"dF/dt gate failed. mean_abs={mean_abs} > target={args.target_dF}"
        )


if __name__ == "__main__":
    main()
