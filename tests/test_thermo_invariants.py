from __future__ import annotations

import networkx as nx

from runtime.thermo_controller import ThermoController


def _graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node("ingest", cpu_norm=0.4)
    g.add_node("matcher", cpu_norm=0.6)
    g.add_node("risk", cpu_norm=0.5)
    g.add_node("broker", cpu_norm=0.3)

    g.add_edge("ingest", "matcher", type="covalent", latency_norm=0.4, coherency=0.9)
    g.add_edge("matcher", "risk", type="ionic", latency_norm=0.8, coherency=0.7)
    g.add_edge("risk", "broker", type="metallic", latency_norm=0.2, coherency=0.85)
    g.add_edge("broker", "ingest", type="hydrogen", latency_norm=1.1, coherency=0.6)
    return g


def _copy_snapshot(controller: ThermoController):
    snap = controller._latest_snapshot  # internal:
    return type(snap)(
        latencies=dict(snap.latencies),
        coherency=dict(snap.coherency),
        resource_usage=snap.resource_usage,
        entropy=snap.entropy,
    )


def test_monotonic_acceptance():
    c = ThermoController(_graph())
    F_old = c._compute_free_energy(snapshot=c._latest_snapshot)
    new_topology, F_new, _meta = c.crisis_ga.evolve(c.current_topology, F_old)

    tol = c._check_monotonic_with_tolerance(F_old, F_new)
    assert tol.accepted, f"TACL gate rejected improvement: {tol.reason}"

    eps = c._monotonic_tolerance_budget(F_old)
    assert F_new <= F_old + eps + 1e-12, (
        f"Monotonicity broken: F_old={F_old}, F_new={F_new}, eps={eps}"
    )


def test_monotonic_rejection_on_degradation():
    c = ThermoController(_graph())
    snap = _copy_snapshot(c)
    F_old = c._compute_free_energy(snapshot=snap)

    degraded = []
    for i, (src, dst, bond) in enumerate(list(c.current_topology)):
        degraded.append((src, dst, "ionic" if i % 2 == 0 else "hydrogen"))

    F_bad = c._compute_free_energy(topology=degraded, snapshot=snap)
    tol = c._check_monotonic_with_tolerance(F_old, F_bad)
    assert not tol.accepted, f"Degraded topology was accepted: {tol.reason}"


def test_circuit_breaker_triggers_on_sustained_rise():
    c = ThermoController(_graph())
    # Simulate sustained free energy rise by directly manipulating controller state
    # and calling control_step which checks for sustained rises
    for i in range(7):
        # Mock a rising free energy by manipulating the snapshot
        snap = c._latest_snapshot
        # Force previous_F to be lower than computed F to trigger rise detection
        base_F = c._compute_free_energy(snapshot=snap)
        c.previous_F = base_F - 0.05 * (i + 1)
        c.previous_t = float(i)
        # Now call control_step which will detect the sustained rise
        c.control_step()

    assert c.circuit_breaker_active, (
        "Circuit breaker did not activate on sustained rise"
    )
