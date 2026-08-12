# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the RicciFlowTrace wrapper (Task 3).

Falsifier witnesses: κ > 1, price-graph κ outside [−1, 1], a flow energy that
increases while the verdict claims non-increase, a non-zero exact Gauss–Bonnet
residual, and a missing validity domain. The builder path proves the trace only
wraps the existing Ricci/Gauss–Bonnet primitives.
"""

from __future__ import annotations

from typing import Any

from fractions import Fraction

import networkx as nx
import pytest

from physics_contracts.manifold.ricci_trace import (
    _is_finite,
    PRICE_GRAPH_DOMAIN,
    RicciFlowTrace,
    build_ricci_flow_trace,
    classify_monotonicity,
    flow_energy,
)


def _trace(**overrides: object) -> RicciFlowTrace:
    base: dict[str, Any] = {
        "snapshot_id": "snap",
        "kappa_before": 0.5,
        "kappa_after": 0.4,
        "flow_energy_before": 1.0,
        "flow_energy_after": 0.9,
        "monotonicity_verdict": "non_increasing",
        "gauss_bonnet_residual": Fraction(0),
        "validity_domain": "general",
    }
    base.update(overrides)
    return RicciFlowTrace(**base)


def test_happy_path_trace_and_digest_determinism() -> None:
    trace = _trace()
    assert trace.trace_digest == _trace().trace_digest
    assert trace.monotonicity_verdict == "non_increasing"


def test_kappa_above_one_is_rejected() -> None:
    with pytest.raises(ValueError, match="INV-RC1"):
        _trace(kappa_after=1.5)


def test_price_graph_kappa_below_minus_one_is_rejected() -> None:
    with pytest.raises(ValueError, match="INV-RC3"):
        _trace(validity_domain=PRICE_GRAPH_DOMAIN, kappa_after=-2.0)


def test_general_domain_allows_kappa_below_minus_one() -> None:
    # Only the universal upper bound applies off the price-graph embedding.
    trace = _trace(validity_domain="general_topology", kappa_after=-2.0)
    assert trace.kappa_after == -2.0


def test_energy_increase_under_non_increasing_verdict_is_rejected() -> None:
    with pytest.raises(ValueError, match="flow_monotonicity"):
        _trace(flow_energy_before=1.0, flow_energy_after=2.0)


def test_nonzero_gauss_bonnet_residual_is_rejected() -> None:
    with pytest.raises(ValueError, match="gauss_bonnet"):
        _trace(gauss_bonnet_residual=Fraction(1, 7))


def test_missing_validity_domain_is_rejected() -> None:
    with pytest.raises(ValueError, match="validity_domain is empty"):
        _trace(validity_domain="")


def test_flow_energy_is_sum_of_squares() -> None:
    assert flow_energy([0.3, -0.4]) == pytest.approx(0.25)


def test_classify_monotonicity_uses_law_slack() -> None:
    assert classify_monotonicity(1.0, 1.0) == "non_increasing"
    assert classify_monotonicity(1.0, 1.5) == "increased"


def test_build_ricci_flow_trace_wraps_primitives() -> None:
    graph = nx.cycle_graph(6)
    trace = build_ricci_flow_trace(
        snapshot_id="s",
        graph_before=graph,
        graph_after=graph,
        edge_curvatures_before=[0.5, 0.5, 0.5],
        edge_curvatures_after=[0.4, 0.4, 0.4],
        validity_domain="general_topology",
    )
    # Recomputed Gauss–Bonnet residual on an untampered graph is exactly zero.
    assert trace.gauss_bonnet_residual == 0
    assert trace.monotonicity_verdict == "non_increasing"


def test_build_ricci_flow_trace_rejects_tampered_curvature_field() -> None:
    graph = nx.cycle_graph(5)
    tampered = {node: Fraction(1) for node in graph.nodes()}  # wrong field
    with pytest.raises(ValueError, match="gauss_bonnet"):
        build_ricci_flow_trace(
            snapshot_id="s",
            graph_before=graph,
            graph_after=graph,
            edge_curvatures_before=[0.5],
            edge_curvatures_after=[0.4],
            validity_domain="general_topology",
            curvature_field=tampered,
        )


def test_is_finite_rejects_inf_and_nan() -> None:
    """`x == x and x not in (inf, -inf)` -- both halves required.

    NaN fails the first half, ±inf the second; under And->Or either would read
    as finite and leak a non-finite energy/curvature into the trace.
    """
    assert _is_finite(1.0) is True
    assert _is_finite(float("inf")) is False
    assert _is_finite(float("-inf")) is False
    assert _is_finite(float("nan")) is False


def test_negative_flow_energy_is_rejected() -> None:
    """`not _is_finite(energy) or energy < 0.0` -- a finite negative energy fails.

    Rule-Zero note: F = Σ κ_e² ≥ 0 is a definitional non-negativity contract on
    the flow energy, not a tunable law. Under Or->And a finite but negative
    energy slips past the guard.
    """
    with pytest.raises(ValueError, match="non-negative"):
        _trace(flow_energy_before=-1.0)


def test_classify_monotonicity_rejects_non_finite_energy() -> None:
    """`not _is_finite(before) or not _is_finite(after)` -- EITHER NaN fails.

    Under Or->And one finite energy masks a NaN partner and the classification
    proceeds on a non-finite comparison.
    """
    import math

    with pytest.raises(ValueError, match="finite"):
        classify_monotonicity(math.nan, 0.0)
    with pytest.raises(ValueError, match="finite"):
        classify_monotonicity(0.0, math.nan)
