"""Admission control check for thermodynamic controller deployments."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

import networkx as nx

from runtime.thermo_controller import ControlStepResult, ThermoController


def _load_topology_from_file(path: Path) -> nx.DiGraph:
    with path.open("r", encoding="utf-8") as file:
        payload: Dict[str, Any] = json.load(file)

    graph = nx.DiGraph()
    for node in payload.get("nodes", []):
        if isinstance(node, dict):
            identifier = node.get("id") or node.get("name")
            if identifier is None:
                raise ValueError("node entry missing 'id'/'name' keys")
            attributes = {k: v for k, v in node.items() if k not in {"id", "name"}}
            graph.add_node(identifier, **attributes)
        else:
            graph.add_node(node)

    for edge in payload.get("edges", []):
        src = edge.get("src") or edge.get("source")
        dst = edge.get("dst") or edge.get("target")
        if src is None or dst is None:
            raise ValueError("edge entry missing 'src'/'dst' keys")
        attributes = {k: v for k, v in edge.items() if k not in {"src", "dst", "source", "target"}}
        graph.add_edge(src, dst, **attributes)

    return graph


def load_topology(path: Path | None) -> nx.DiGraph:
    if path is not None:
        if not path.exists():
            raise FileNotFoundError(f"Topology file not found: {path}")
        return _load_topology_from_file(path)

    # Fall back to the default deployment topology used by the runtime API.
    from runtime.thermo_api import _build_default_graph  # lazy import to avoid FastAPI at import time

    return _build_default_graph()


def perform_admission_check(topology_path: Path | None = None) -> ControlStepResult:
    graph = load_topology(topology_path)
    controller = ThermoController(graph)
    return controller.control_step(simulated=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run pre-deployment admission checks for the thermo controller")
    parser.add_argument(
        "--topology",
        type=Path,
        default=None,
        help="Optional path to a JSON topology description. Defaults to the runtime's built-in topology.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = perform_admission_check(args.topology)
    except Exception as exc:  # pragma: no cover - defensive guard for CLI usage
        print(f"[admission] failed to execute check: {exc}", file=sys.stderr)
        return 1

    if not result.accepted or result.circuit_breaker_active:
        reason = result.tolerance.reason if result.tolerance is not None else "circuit_breaker_active"
        print(
            "[admission] blocked deployment due to simulated controller rejection",
            f"accepted={result.accepted}",
            f"circuit_breaker={result.circuit_breaker_active}",
            f"reason={reason}",
        )
        return 1

    print(
        "[admission] controller simulation accepted topology",
        f"state={result.controller_state}",
        f"reason={result.tolerance.reason if result.tolerance else 'baseline'}",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
