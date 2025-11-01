"""Admission control gate executed prior to deploying the thermodynamic controller."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import networkx as nx

# ``python scripts/admission_check.py`` places the ``scripts`` directory first on
# ``sys.path`` which prevents resolving project-local packages such as
# ``runtime``. Normalise the import order to ensure repository modules remain
# discoverable without requiring environment tweaks.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[0]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

script_dir_str = str(SCRIPT_DIR)
if script_dir_str in sys.path:
    sys.path.remove(script_dir_str)

try:  # pragma: no cover - optional dependency guarded for robustness
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised in CI when PyYAML missing
    yaml = None  # type: ignore[assignment]

from runtime.thermo_controller import ControlStepResult, ThermoController, ToleranceCheck

DEFAULT_TOPOLOGY_PATH = REPO_ROOT / "deploy" / "runtime" / "topology.yaml"


def build_default_topology() -> nx.DiGraph:
    """Return the canonical fallback topology."""

    graph = nx.DiGraph()
    graph.add_node("ingest", cpu_norm=0.4)
    graph.add_node("matcher", cpu_norm=0.6)
    graph.add_node("risk", cpu_norm=0.5)
    graph.add_node("broker", cpu_norm=0.3)

    graph.add_edge("ingest", "matcher", type="covalent", latency_norm=0.4, coherency=0.9)
    graph.add_edge("matcher", "risk", type="ionic", latency_norm=0.8, coherency=0.7)
    graph.add_edge("risk", "broker", type="metallic", latency_norm=0.2, coherency=0.85)
    graph.add_edge("broker", "ingest", type="hydrogen", latency_norm=1.1, coherency=0.6)
    return graph


def _load_structured_topology(path: Path) -> Mapping[str, Any]:
    text = path.read_text()
    if path.suffix.lower() in {".yaml", ".yml"}:
        if yaml is None:  # pragma: no cover - defensive fallback
            raise RuntimeError(
                "PyYAML is required to load topology files ending with .yaml/.yml"
            )
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)

    if not isinstance(data, Mapping):
        raise ValueError("Topology definition must be a mapping with 'nodes' and 'edges'.")
    return data


def _graph_from_payload(payload: Mapping[str, Any]) -> nx.DiGraph:
    graph = nx.DiGraph()

    nodes = payload.get("nodes", [])
    if not isinstance(nodes, (list, tuple)):
        raise ValueError("Topology nodes must be provided as a list of mappings.")
    for node in nodes:
        if not isinstance(node, Mapping) or "id" not in node:
            raise ValueError("Each node entry must be a mapping containing an 'id'.")
        identifier = str(node["id"])
        attrs = {k: v for k, v in node.items() if k != "id"}
        graph.add_node(identifier, **attrs)

    edges = payload.get("edges", [])
    if not isinstance(edges, (list, tuple)):
        raise ValueError("Topology edges must be provided as a list of mappings.")
    for edge in edges:
        if not isinstance(edge, Mapping) or {"source", "target"} - set(edge):
            raise ValueError(
                "Each edge entry must define 'source' and 'target' attributes."
            )
        src = str(edge["source"])
        dst = str(edge["target"])
        attrs = {k: v for k, v in edge.items() if k not in {"source", "target"}}
        graph.add_edge(src, dst, **attrs)

    if graph.number_of_nodes() == 0 or graph.number_of_edges() == 0:
        raise ValueError("Topology must contain at least one node and one edge.")

    return graph


def load_topology(topology_path: Path | None = None) -> nx.DiGraph:
    """Load the topology from disk or return the default fallback."""

    candidate_path: Path | None = topology_path
    if candidate_path is None:
        env_path = os.getenv("THERMO_TOPOLOGY_PATH")
        if env_path:
            candidate_path = Path(env_path)
        elif DEFAULT_TOPOLOGY_PATH.exists():
            candidate_path = DEFAULT_TOPOLOGY_PATH

    if candidate_path is None:
        return build_default_topology()

    resolved = candidate_path.expanduser()
    if not resolved.exists():
        raise FileNotFoundError(f"Topology file not found: {resolved}")

    payload = _load_structured_topology(resolved)
    return _graph_from_payload(payload)


def run_admission(topology_path: Path | None = None) -> ControlStepResult:
    """Execute the admission control simulation and return the outcome."""

    graph = load_topology(topology_path)
    controller = ThermoController(graph)
    result = controller.control_step(simulated=True)
    return result


def _format_failure_message(result: ControlStepResult) -> str:
    tolerance = result.tolerance
    reason = tolerance.reason if isinstance(tolerance, ToleranceCheck) else "n/a"
    return (
        "Admission check rejected the proposed topology.\n"
        f"  - circuit_breaker_active={result.circuit_breaker_active}\n"
        f"  - tolerance.accepted={getattr(tolerance, 'accepted', None)}\n"
        f"  - tolerance.reason={reason}\n"
        f"  - controller_state={result.controller_state}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "Admission control")
    parser.add_argument(
        "--topology",
        type=Path,
        default=None,
        help="Optional path to a JSON or YAML topology definition.",
    )
    args = parser.parse_args(argv)

    try:
        result = run_admission(args.topology)
    except Exception as exc:  # pragma: no cover - defensive CLI guard
        print(f"[admission] failed to execute admission check: {exc}", file=sys.stderr)
        return 1

    if not result.accepted:
        print(_format_failure_message(result), file=sys.stderr)
        return 1

    print("[admission] topology accepted by thermodynamic controller")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
