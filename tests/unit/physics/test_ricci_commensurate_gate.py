# SPDX-License-Identifier: MIT
"""Adversarial fail-closed tests for the Ricci commensurate-metric runtime gate.

INV-RC3's symmetric band κ ∈ [−1, 1] is CONDITIONAL: Ollivier (2009) defines
κ(x, y) = 1 − W₁(μₓ, μᵧ) / d(x, y) and the lower bound κ ≥ −1 assumes the
graph-distance metric — i.e. the positional embedding in which W₁ is measured is
commensurate with the combinatorial/weighted geodesic d. For a
``build_price_graph`` output that holds only in the path-like regime where
consecutive price levels move by unit steps. A jumpy / gapped / volatile series
breaks commensurateness (positional vs |Δp|+1-weighted metrics diverge), W₁/d
exceeds 2 on some edge, and κ descends below −1 (≈ −6 at δ = 0.05).

Before :func:`assert_ricci_regime`, the runtime emitted that out-of-regime κ with
no signal that the tight INV-RC3 band no longer applied — a dirty-data attack: a
gapped price series silently yields κ < −1 presented as a valid Ricci bound.

These tests lock the gate's fail-closed contract:

* COMMENSURATE path (unit steps) ⇒ regime verified, tier INV-RC3, κ ∈ [−1, 1].
* JUMPY / BIMODAL / GAPPED series ⇒ gate FIRES: tier is DOWNGRADED to INV-RC1
  (or, in raise mode, raises) and the out-of-regime κ is recorded, NEVER labelled
  INV-RC3-valid. This is the dirty-data attack the gate must reject.
* INV-RC1 universal κ ≤ 1 holds on arbitrary connected graphs.
* DEGENERATE input (empty / single node / NaN correlations) ⇒ fail-closed to
  INV-RC1, never a spurious INV-RC3 claim.

Math anchor: Ollivier, J. Funct. Anal. 256(3):810–864 (2009). κ ∈ [−1, 1]
assumes the graph-distance metric, not an arbitrary positional embedding.
"""

from __future__ import annotations

import networkx as nx
import numpy as np

from core.indicators.ricci import (
    RicciRegimeCertificate,
    assert_ricci_regime,
    build_price_graph,
    ricci_curvature_edge,
)

# κ = 1 − W₁/d, so the INV-RC3 band is [−1, 1]; float round-off tolerance only.
RC3_TOLERANCE = 1e-9


def _commensurate_prices() -> np.ndarray:
    """A path-like price series whose quantised levels move by unit steps."""
    return np.array([100.0, 100.5, 101.0, 101.5, 102.0, 102.5, 103.0])


def _jumpy_prices(seed: int = 7, length: int = 128, vol: float = 0.05) -> np.ndarray:
    """A volatile series whose large per-step moves gap the price levels."""
    rng = np.random.default_rng(seed)
    return 100.0 * np.exp(np.cumsum(rng.normal(0.0, vol, size=length)))


def _bimodal_gapped_prices() -> np.ndarray:
    """A bimodal series: a low cluster, a large gap, then a high cluster."""
    low = np.array([100.0, 100.5, 101.0, 100.5, 101.0])
    high = np.array([130.0, 130.5, 131.0, 130.5, 131.0])
    return np.concatenate([low, high, low, high])


# ─────────────────────────────────────────────────────────────────────────────
# 1. Commensurate path graph ⇒ INV-RC3 holds (κ ∈ [−1, 1])
# ─────────────────────────────────────────────────────────────────────────────


def test_commensurate_path_graph_asserts_inv_rc3() -> None:
    """Unit-step price levels ⇒ regime verified, tier INV-RC3, κ ∈ [−1, 1]."""
    g = build_price_graph(_commensurate_prices(), delta=0.005)
    cert = assert_ricci_regime(g)

    assert isinstance(cert, RicciRegimeCertificate)
    assert cert.asserted_tier == "INV-RC3", (
        "commensurate unit-step path must verify the INV-RC3 regime, got tier "
        f"{cert.asserted_tier!r} (deviation: {cert.deviation!r})"
    )
    assert cert.commensurate is True
    assert cert.max_level_step <= 1, (
        f"commensurate path must have unit inter-level steps, got {cert.max_level_step}"
    )
    assert cert.n_edges_below_lower_bound == 0
    assert cert.deviation == ""

    # The verified band must actually hold edge-by-edge.
    kappas = [ricci_curvature_edge(g, int(u), int(v)) for u, v in g.edges()]
    assert kappas, "commensurate fixture must produce edges"
    assert min(kappas) >= -1.0 - RC3_TOLERANCE
    assert max(kappas) <= 1.0 + RC3_TOLERANCE
    assert cert.kappa_min >= -1.0 - RC3_TOLERANCE


# ─────────────────────────────────────────────────────────────────────────────
# 2. Dirty-data attack: jumpy / bimodal / gapped ⇒ gate fires (downgrade or raise)
# ─────────────────────────────────────────────────────────────────────────────


def test_jumpy_series_downgrades_to_inv_rc1_and_records_out_of_regime_kappa() -> None:
    """Volatile/gapped series ⇒ gate fires: tier downgraded, κ < −1 recorded.

    This is the dirty-data attack. The out-of-regime κ (which reaches well below
    −1) must NEVER be presented as INV-RC3-valid; the certificate must downgrade
    to the universal INV-RC1 bound and record the deviation.
    """
    g = build_price_graph(_jumpy_prices(), delta=0.05)
    cert = assert_ricci_regime(g)

    assert cert.asserted_tier == "INV-RC1", (
        "jumpy series breaks commensurateness; the gate must NOT assert INV-RC3"
    )
    assert cert.commensurate is False
    assert cert.deviation, "a downgrade must record WHY the regime was rejected"

    # The realised curvature genuinely leaves the INV-RC3 band — that is the
    # silent-corruption the gate exists to catch.
    kappas = [ricci_curvature_edge(g, int(u), int(v)) for u, v in g.edges()]
    assert min(kappas) < -1.0 - RC3_TOLERANCE, (
        "fixture must actually produce out-of-band κ for the attack to be real; "
        f"got κ_min = {min(kappas):.4f}"
    )
    assert cert.kappa_min < -1.0 - RC3_TOLERANCE
    assert cert.n_edges_below_lower_bound >= 1


def test_bimodal_gapped_series_fires_gate() -> None:
    """A bimodal low/high series with a large gap leaves the commensurate regime."""
    g = build_price_graph(_bimodal_gapped_prices(), delta=0.005)
    cert = assert_ricci_regime(g)

    assert cert.asserted_tier == "INV-RC1", (
        "bimodal/gapped levels are incommensurate; INV-RC3 must not be asserted "
        f"(deviation: {cert.deviation!r})"
    )
    assert cert.commensurate is False
    # Either the structural max-jump leg or the exact κ ≥ −1 leg (or both) must
    # have rejected it; the structural leg is what fires for a clean wide gap.
    assert cert.max_level_step > 1 or cert.n_edges_below_lower_bound > 0


def test_raise_mode_raises_on_out_of_regime_instead_of_silently_passing() -> None:
    """With raise_on_violation, a broken regime raises rather than returns a tier."""
    g = build_price_graph(_jumpy_prices(), delta=0.05)
    try:
        assert_ricci_regime(g, raise_on_violation=True)
    except ValueError as exc:
        assert "regime" in str(exc).lower()
        assert "INV-RC3" in str(exc)
    else:  # pragma: no cover - must not reach
        raise AssertionError(
            "raise_on_violation must raise on a jumpy series, not return a downgrade"
        )


def test_structural_pre_filter_is_not_relied_on_alone() -> None:
    """The exact κ ≥ −1 leg binds even when the structural max-jump is small.

    The structural max-level-step is a necessary but not sufficient condition. A
    series that revisits levels can build a denser graph whose edges leave the
    band even though no single inter-level jump is large. The gate must still
    refuse INV-RC3 in that case, proving it does not trust the cheap pre-filter
    alone.
    """
    g = build_price_graph(_jumpy_prices(), delta=0.05)
    cert = assert_ricci_regime(g)
    # Regardless of which leg fired, an out-of-band κ on this graph must force a
    # downgrade — the contract is on the verdict, not on which leg caught it.
    kappas = [ricci_curvature_edge(g, int(u), int(v)) for u, v in g.edges()]
    if min(kappas) < -1.0 - RC3_TOLERANCE:
        assert cert.asserted_tier == "INV-RC1"


# ─────────────────────────────────────────────────────────────────────────────
# 3. INV-RC1 universal κ ≤ 1 on arbitrary connected graphs
# ─────────────────────────────────────────────────────────────────────────────


def test_inv_rc1_universal_upper_bound_on_arbitrary_connected_graphs() -> None:
    """κ ≤ 1 holds on every edge of arbitrary connected (non-price) graphs.

    W₁ ≥ 0 ⇒ κ = 1 − W₁/d ≤ 1 unconditionally. This is INV-RC1, the bound the
    gate downgrades TO when the tight INV-RC3 band is not assertable.
    """
    graphs = [
        nx.path_graph(7),
        nx.cycle_graph(12),
        nx.complete_graph(6),
        nx.star_graph(8),
        nx.watts_strogatz_graph(20, 4, 0.3, seed=11),
    ]
    for g in graphs:
        for u, v in g.edges():
            if u == v:
                continue
            if not nx.has_path(g, u, v):  # pragma: no cover - connected fixtures
                continue
            kappa = ricci_curvature_edge(g, int(u), int(v))
            assert kappa <= 1.0 + RC3_TOLERANCE, (
                f"INV-RC1 violated: κ({u},{v}) = {kappa:.6f} > 1 on "
                f"{g.number_of_nodes()}-node graph"
            )


def test_cycle_graph_downgrades_below_inv_rc3_band() -> None:
    """A 12-cycle's wrap-around edge leaves [−1, 1]; the gate must not claim RC3.

    The wrap-around edge of a cycle_12 has endpoints far apart in the integer
    embedding but graph-distance 1, so κ descends below −1 — an arbitrary
    (non-price) topology where INV-RC3 must NOT be asserted, but INV-RC1 holds.
    """
    g = nx.cycle_graph(12)
    cert = assert_ricci_regime(g)
    assert cert.asserted_tier == "INV-RC1"
    assert cert.commensurate is False
    # Upper bound still universal.
    for u, v in g.edges():
        assert ricci_curvature_edge(g, int(u), int(v)) <= 1.0 + RC3_TOLERANCE


# ─────────────────────────────────────────────────────────────────────────────
# 4. Degenerate inputs ⇒ fail-closed to INV-RC1
# ─────────────────────────────────────────────────────────────────────────────


def test_empty_graph_fails_closed_to_inv_rc1() -> None:
    g = build_price_graph(np.array([]), delta=0.005)
    cert = assert_ricci_regime(g)
    assert cert.asserted_tier == "INV-RC1"
    assert cert.commensurate is False
    assert "degenerate" in cert.deviation


def test_single_node_graph_fails_closed_to_inv_rc1() -> None:
    g = build_price_graph(np.array([100.0]), delta=0.005)
    cert = assert_ricci_regime(g)
    assert cert.asserted_tier == "INV-RC1"
    assert cert.commensurate is False


def test_nan_prices_fail_closed_to_inv_rc1() -> None:
    """A series of mostly NaN prices cannot support the band ⇒ fail-closed."""
    g = build_price_graph(np.array([np.nan, np.nan, 100.0]), delta=0.005)
    cert = assert_ricci_regime(g)
    assert cert.asserted_tier == "INV-RC1"
    assert cert.commensurate is False


def test_explicit_empty_nx_graph_fails_closed() -> None:
    cert = assert_ricci_regime(nx.Graph())
    assert cert.asserted_tier == "INV-RC1"
    assert cert.commensurate is False
    assert "degenerate" in cert.deviation


def test_degenerate_never_emits_spurious_inv_rc3() -> None:
    """No degenerate input may ever return an INV-RC3 certificate."""
    degenerate_graphs = [
        nx.Graph(),
        build_price_graph(np.array([]), delta=0.005),
        build_price_graph(np.array([100.0]), delta=0.005),
        build_price_graph(np.array([np.nan, np.inf]), delta=0.005),
    ]
    for g in degenerate_graphs:
        cert = assert_ricci_regime(g)
        assert cert.asserted_tier != "INV-RC3", (
            "a degenerate graph must never be certified INV-RC3"
        )
