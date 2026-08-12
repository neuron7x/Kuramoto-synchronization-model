# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""FastAPI application exposing thermodynamic telemetry."""

from __future__ import annotations

import hmac
import os
import time
from typing import Dict, Optional

import networkx as nx
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from runtime.thermo_controller import ThermoController

app = FastAPI(title="GeoSync Thermodynamic API", version="1.0.0")

_controller: Optional[ThermoController] = None


def _build_default_graph() -> nx.DiGraph:
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


def get_controller() -> ThermoController:
    global _controller
    if _controller is None:
        _controller = ThermoController(_build_default_graph())
    return _controller


class ManualOverrideRequest(BaseModel):
    token: str
    reason: str


def _get_manual_override_token() -> str:
    token = os.getenv("THERMO_OVERRIDE_TOKEN")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Manual override token is not configured",
        )
    return token


@app.get("/thermo/status")
def get_status() -> Dict[str, object]:
    controller = get_controller()
    return {
        "current_F": controller.get_current_F(),
        "dF_dt": controller.get_dF_dt(),
        "epsilon_adaptive": controller.epsilon_adaptive,
        "max_edge_cost": controller.get_bottleneck_cost(),
        "bottleneck_edge": controller.get_bottleneck_edge(),
        "topology_id": controller.get_topology_id(),
        "violations_total": controller.get_monotonic_violations_total(),
        "crisis_mode": (
            controller.telemetry_history[-1]["crisis_mode"]
            if controller.telemetry_history
            else "normal"
        ),
        "timestamp": time.time(),
    }


@app.get("/thermo/history")
def get_history(limit: int = 100) -> Dict[str, object]:
    controller = get_controller()
    records = controller.telemetry_history[-limit:]
    return {"records": records, "count": len(records)}


@app.get("/thermo/crisis")
def get_crisis_stats() -> Dict[str, object]:
    controller = get_controller()
    return controller.crisis_ga.get_crisis_statistics()


@app.get("/thermo/activations")
def get_activations(limit: int = 50) -> Dict[str, object]:
    controller = get_controller()
    activations = controller.link_activator.get_activation_history()[-limit:]
    total_cost = controller.link_activator.get_total_cost()
    return {"activations": activations, "total_cost": total_cost}


@app.post("/thermo/reset")
def reset_controller() -> Dict[str, object]:
    global _controller
    _controller = ThermoController(_build_default_graph())
    return {"status": "reset", "timestamp": time.time()}


@app.post("/thermo/override")
def manual_override(request: ManualOverrideRequest) -> Dict[str, object]:
    expected_token = _get_manual_override_token()
    if not hmac.compare_digest(request.token, expected_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    controller = get_controller()
    controller.manual_override(request.reason)
    return {"status": "override_accepted", "timestamp": time.time()}


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(
        "Deprecated entrypoint. Use: python -m application.runtime.server --config <path>"
    )
