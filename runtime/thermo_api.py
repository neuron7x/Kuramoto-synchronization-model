"""FastAPI surface exposing thermodynamic control telemetry."""

from __future__ import annotations

import networkx as nx
from fastapi import FastAPI

from runtime.thermo_controller import ThermoController


def _build_default_controller() -> ThermoController:
    graph = nx.DiGraph()
    graph.add_node("PulseGen", cpu_norm=0.2)
    graph.add_node("Analyzer", cpu_norm=0.25)
    graph.add_node("Trader", cpu_norm=0.35)
    graph.add_node("RiskMgr", cpu_norm=0.3)

    graph.add_edge(
        "PulseGen",
        "Analyzer",
        type="metallic",
        latency_norm=0.8,
        coherency=0.92,
    )
    graph.add_edge(
        "Trader",
        "RiskMgr",
        type="ionic",
        latency_norm=0.6,
        coherency=0.88,
    )

    controller = ThermoController(graph)
    controller.control_step()
    return controller


def create_app(controller: ThermoController | None = None) -> FastAPI:
    """Return a FastAPI app exposing thermodynamic telemetry."""

    thermo = controller or _build_default_controller()
    app = FastAPI(title="TradePulse Thermodynamic Control", version="1.0.0")

    @app.get("/thermo/status")
    def thermo_status() -> dict[str, object]:
        """Expose the latest controller snapshot for SRE dashboards."""

        return thermo.collect_telemetry()

    return app


__all__ = ["create_app"]
