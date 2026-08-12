# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T3 — Forman-Ricci curvature tests."""

import numpy as np
import pytest

from core.physics.forman_ricci import (
    _MARGIN_ESCALATION_ONSET,
    DualTrackRicciMonitor,
    FormanRicciCurvature,
    FormanRicciResult,
)


@pytest.fixture
def frc() -> FormanRicciCurvature:
    return FormanRicciCurvature(threshold=0.3)


@pytest.fixture
def complete_graph_corr():
    """4-node complete graph (all corr = 0.8)."""
    n = 4
    corr = np.full((n, n), 0.8)
    np.fill_diagonal(corr, 1.0)
    return corr


@pytest.fixture
def star_graph_corr():
    """Star graph: node 0 connected to all, others disconnected."""
    n = 5
    corr = np.eye(n)
    for i in range(1, n):
        corr[0, i] = corr[i, 0] = 0.6
    return corr


class TestFormanCurvatureFormula:
    """κ_F(i,j) = 4 - d_i - d_j + 3·T_ij."""

    def test_complete_graph_positive_curvature(self, frc, complete_graph_corr):
        """Complete K4: every edge in 2 triangles, degree=3.
        κ = 4 - 3 - 3 + 3·2 = 4 > 0."""
        result = frc.compute_from_correlation(complete_graph_corr)
        assert all(v > 0 for v in result.edge_curvatures.values())
        assert result.kappa_min > 0

    def test_star_graph_negative_curvature(self, frc, star_graph_corr):
        """Star: no triangles, hub degree=4, leaf degree=1.
        κ = 4 - 4 - 1 + 0 = -1."""
        result = frc.compute_from_correlation(star_graph_corr)
        assert result.kappa_min < 0

    def test_single_edge_curvature(self, frc):
        """2 nodes: d_i=d_j=1, T=0. κ = 4-1-1+0 = 2."""
        corr = np.array([[1.0, 0.5], [0.5, 1.0]])
        result = frc.compute_from_correlation(corr)
        assert len(result.edge_curvatures) == 1
        assert abs(list(result.edge_curvatures.values())[0] - 2.0) < 1e-10


class TestHerdingDetection:
    """κ_min → 0 = herding."""

    def test_herding_index(self, frc, complete_graph_corr):
        result = frc.compute_from_correlation(complete_graph_corr)
        assert result.herding_index > 0, "Complete graph should show herding"

    def test_fragmented_low_herding(self, frc, star_graph_corr):
        result = frc.compute_from_correlation(star_graph_corr)
        assert result.herding_index < 1.0


class TestDualTrackMonitor:
    def test_update_and_margin(self):
        monitor = DualTrackRicciMonitor(forman_threshold=0.3, correlation_window=10)
        rng = np.random.default_rng(42)
        prices = 100 + np.cumsum(rng.normal(0, 1, (30, 5)), axis=0)

        result = monitor.update(prices)
        assert isinstance(result, FormanRicciResult)
        margin = monitor.margin_multiplier()
        assert margin >= 1.0, "Margin multiplier should be ≥ 1"

    def test_herding_increases_margin(self):
        monitor = DualTrackRicciMonitor(margin_sensitivity=3.0)
        # Simulate herding result
        herding = FormanRicciResult(
            edge_curvatures={(0, 1): 1.0},
            kappa_min=0.5,
            kappa_mean=0.5,
            kappa_max=0.5,
            herding_index=1.0,
        )
        normal = FormanRicciResult(
            edge_curvatures={(0, 1): -3.0},
            kappa_min=-3.0,
            kappa_mean=-3.0,
            kappa_max=-3.0,
            herding_index=0.0,
        )
        assert monitor.margin_multiplier(herding) > monitor.margin_multiplier(normal)

    def test_escalation_floor_is_intentional_not_silent_clamp(self):
        """Below the escalation onset the multiplier floors at base *by design*.

        Combinatorial Forman-Ricci is unbounded below, so κ_min ≪ onset is
        expected, not anomalous. The ``max(0, κ_min − onset)`` is the documented
        "fragmented → base margin" policy floor: two structures far below the
        onset (κ_min = −2.0 and κ_min = −96.0) must both return exactly the base
        multiplier. This pins the floor as a deliberate policy choice so it
        cannot be mistaken for, or "fixed" as, a silent clamp.
        """
        base = 1.5
        monitor = DualTrackRicciMonitor(margin_multiplier_base=base, margin_sensitivity=2.0)

        def _at(kappa_min: float) -> FormanRicciResult:
            return FormanRicciResult(
                edge_curvatures={(0, 1): kappa_min},
                kappa_min=kappa_min,
                kappa_mean=kappa_min,
                kappa_max=kappa_min,
                herding_index=0.0,
            )

        # The onset is a policy threshold, not a curvature bound.
        assert _MARGIN_ESCALATION_ONSET == -2.0
        # At the onset and far below it, the multiplier saturates at base.
        assert monitor.margin_multiplier(_at(_MARGIN_ESCALATION_ONSET)) == base
        assert monitor.margin_multiplier(_at(-96.0)) == base
        # Distinct fragile structures map to the identical floored multiplier:
        # the floor is intentional, and the un-escalated κ_min is preserved on
        # the result (kappa_min) rather than discarded.
        assert monitor.margin_multiplier(_at(-2.0)) == monitor.margin_multiplier(_at(-50.0))

    def test_margin_escalates_smoothly_above_onset(self):
        """Just above the onset escalation is linear in (κ_min − onset)."""
        base, sens = 1.0, 2.0
        monitor = DualTrackRicciMonitor(margin_multiplier_base=base, margin_sensitivity=sens)
        result = FormanRicciResult(
            edge_curvatures={(0, 1): 0.0},
            kappa_min=0.0,
            kappa_mean=0.0,
            kappa_max=0.0,
            herding_index=0.0,
        )
        # κ_min = 0 ⇒ shift = 0 − onset = 2.0 ⇒ base·(1 + sens·2.0).
        expected = base * (1.0 + sens * (0.0 - _MARGIN_ESCALATION_ONSET))
        assert monitor.margin_multiplier(result) == pytest.approx(expected)

    def test_is_herding(self):
        monitor = DualTrackRicciMonitor()
        assert monitor.is_herding(
            FormanRicciResult(
                edge_curvatures={},
                kappa_min=0.0,
                kappa_mean=0.0,
                kappa_max=0.0,
                herding_index=0.0,
            )
        )
        assert not monitor.is_herding(
            FormanRicciResult(
                edge_curvatures={},
                kappa_min=-5.0,
                kappa_mean=-5.0,
                kappa_max=-5.0,
                herding_index=0.0,
            )
        )

    def test_fragility_trend(self):
        monitor = DualTrackRicciMonitor(forman_threshold=0.3, correlation_window=10)
        rng = np.random.default_rng(7)
        for t in range(15):
            prices = 100 + np.cumsum(rng.normal(0, 1, (20, 4)), axis=0)
            monitor.update(prices)
        trend = monitor.fragility_trend(lookback=10)
        assert np.isfinite(trend)


class TestComputeFromPrices:
    def test_basic_computation(self, frc):
        rng = np.random.default_rng(42)
        prices = 100 + np.cumsum(rng.normal(0, 1, (60, 5)), axis=0)
        result = frc.compute_from_prices(prices, window=20)
        assert isinstance(result, FormanRicciResult)
        assert np.isfinite(result.kappa_mean)


class TestInputValidation:
    def test_threshold_bounds(self):
        with pytest.raises(ValueError):
            FormanRicciCurvature(threshold=0.0)
        with pytest.raises(ValueError):
            FormanRicciCurvature(threshold=1.0)

    def test_non_square_corr(self, frc):
        with pytest.raises(ValueError):
            frc.compute_from_correlation(np.ones((3, 4)))

    def test_insufficient_prices(self, frc):
        with pytest.raises(ValueError):
            frc.compute_from_prices(np.ones((1, 5)))


class TestRepresentationHonesty:
    """Metamorphic locks for the declared unweighted/unsigned semantics.

    These tests do not change behaviour; they pin the *actual* semantics of
    the binarized ``|ρ| > threshold`` graph so the module cannot silently
    drift to claiming weight- or sign-sensitivity it does not have. The
    provenance fields are asserted to declare exactly the information the
    projection discards.
    """

    def test_provenance_fields_declare_unweighted_unsigned(self) -> None:
        frc = FormanRicciCurvature(threshold=0.3)
        corr = np.full((4, 4), 0.8)
        np.fill_diagonal(corr, 1.0)
        result = frc.compute_from_correlation(corr)
        assert result.weighted is False
        assert result.signed is False
        assert result.representation == "graph"
        assert "edge_weight_magnitude" in result.information_loss
        assert "correlation_sign" in result.information_loss

    def test_weight_insensitivity_is_declared_not_hidden(self) -> None:
        # Two graphs with IDENTICAL above-threshold topology but different
        # magnitudes must produce identical curvature — the honest signature
        # of an unweighted method. The result declares weighted=False so this
        # invariance is documented, not a masked "weighted" claim.
        frc = FormanRicciCurvature(threshold=0.3)
        n = 4
        weak = np.full((n, n), 0.4)
        np.fill_diagonal(weak, 1.0)
        strong = np.full((n, n), 0.95)
        np.fill_diagonal(strong, 1.0)
        r_weak = frc.compute_from_correlation(weak)
        r_strong = frc.compute_from_correlation(strong)
        assert r_weak.edge_curvatures == r_strong.edge_curvatures
        assert r_weak.weighted is False and r_strong.weighted is False

    def test_sign_erasure_is_recorded(self) -> None:
        # ρ = +0.8 and ρ = −0.8 collapse to the same edge under |ρ|, so the
        # anti-correlation case yields identical output. This is real
        # information loss and must be declared via information_loss / signed.
        frc = FormanRicciCurvature(threshold=0.3)
        n = 4
        pos = np.full((n, n), 0.8)
        np.fill_diagonal(pos, 1.0)
        neg = -np.full((n, n), 0.8)
        np.fill_diagonal(neg, 1.0)
        r_pos = frc.compute_from_correlation(pos)
        r_neg = frc.compute_from_correlation(neg)
        assert r_pos.edge_curvatures == r_neg.edge_curvatures
        assert r_pos.signed is False
        assert "correlation_sign" in r_pos.information_loss

    def test_empty_graph_result_also_declares_provenance(self) -> None:
        # A below-threshold (edgeless) correlation matrix still returns a
        # provenance-bearing result, not a bare zero with no declared loss.
        frc = FormanRicciCurvature(threshold=0.9)
        corr = np.eye(3) + 0.1 * (np.ones((3, 3)) - np.eye(3))
        result = frc.compute_from_correlation(corr)
        assert result.edge_curvatures == {}
        assert result.weighted is False
        assert result.information_loss == ("edge_weight_magnitude", "correlation_sign")


class TestLayerBoundaryAndNanPolicy:
    """Layer-B labeling, claim boundary, and non-finite-input honesty.

    Extends the representation-honesty contract: the result declares its layer
    and claim boundary so ``herding_index`` cannot be read as a physics or
    trading claim without validation, and non-finite correlations are recorded
    and excluded rather than silently erased (or fabricating a phantom edge).
    """

    def test_layer_and_claim_boundary_declared(self) -> None:
        frc = FormanRicciCurvature(threshold=0.3)
        corr = np.full((4, 4), 0.8)
        np.fill_diagonal(corr, 1.0)
        result = frc.compute_from_correlation(corr)
        assert result.layer == "market_descriptor"
        assert result.physical_claim is False
        assert result.claim_boundary == "derived_unsigned_unweighted_topology_descriptor"
        assert result.projection_policy == "abs_correlation_threshold_binary"
        assert result.nan_policy == "nonfinite_excluded_and_recorded"

    def test_herding_index_carries_descriptor_boundary(self) -> None:
        # Declarative provenance (not enforcement): any result exposing
        # herding_index also exposes physical_claim=False + the descriptor
        # claim_boundary, so a consumer that READS them learns the value is
        # descriptor-only. Nothing forces that read — DualTrackRicciMonitor is
        # the known un-enforced descriptor->action path.
        frc = FormanRicciCurvature(threshold=0.3)
        corr = np.full((4, 4), 0.8)
        np.fill_diagonal(corr, 1.0)
        result = frc.compute_from_correlation(corr)
        assert result.herding_index >= 0.0
        assert result.physical_claim is False
        assert "descriptor" in result.claim_boundary

    def test_nan_corr_not_silently_erased(self) -> None:
        # A NaN and an inf correlation must be recorded (nonfinite_input_count)
        # and excluded from the graph — NOT silently dropped, and critically
        # NOT fabricating an edge: np.abs(inf) > threshold is True, so without
        # the finiteness guard an inf would create a phantom edge.
        frc = FormanRicciCurvature(threshold=0.5)
        n = 4
        corr = np.full((n, n), 0.9)  # all finite strong edges by default
        np.fill_diagonal(corr, 1.0)
        corr[0, 1] = corr[1, 0] = np.nan
        corr[2, 3] = corr[3, 2] = np.inf
        result = frc.compute_from_correlation(corr)
        # 2 symmetric off-diagonal pairs = 4 non-finite entries recorded
        assert result.nonfinite_input_count == 4
        # neither the NaN pair nor the inf pair is an edge
        assert (0, 1) not in result.edge_curvatures
        assert (2, 3) not in result.edge_curvatures
        # a genuinely finite strong edge survives
        assert (0, 2) in result.edge_curvatures

    def test_inf_correlation_does_not_create_phantom_edge(self) -> None:
        # Isolated regression for the latent bug: a lone inf among otherwise
        # sub-threshold correlations must yield NO edges, not one phantom edge.
        frc = FormanRicciCurvature(threshold=0.5)
        n = 3
        corr = np.full((n, n), 0.1)
        np.fill_diagonal(corr, 1.0)
        corr[0, 1] = corr[1, 0] = np.inf
        result = frc.compute_from_correlation(corr)
        assert result.edge_curvatures == {}
        assert result.nonfinite_input_count == 2

    def test_finite_inputs_unchanged_count_zero(self) -> None:
        # Regression: a fully finite correlation matrix records zero non-finite
        # and produces the same curvature as before the hardening.
        frc = FormanRicciCurvature(threshold=0.3)
        corr = np.full((4, 4), 0.8)
        np.fill_diagonal(corr, 1.0)
        result = frc.compute_from_correlation(corr)
        assert result.nonfinite_input_count == 0
        assert all(v > 0 for v in result.edge_curvatures.values())

    def test_nonfinite_count_is_directed_entries_not_pairs(self) -> None:
        # Semantics lock (PR #1102 review): nonfinite_input_count counts matrix
        # ENTRIES, not unordered pairs. A one-sided NaN (only (0,1), not (1,0))
        # counts as exactly 1.
        frc = FormanRicciCurvature(threshold=0.3)
        corr = np.full((3, 3), 0.8)
        np.fill_diagonal(corr, 1.0)
        corr[0, 1] = np.nan  # asymmetric: (1, 0) stays finite
        result = frc.compute_from_correlation(corr)
        assert result.nonfinite_input_count == 1


class TestMonitorConsumerBoundary:
    """The descriptor *consumer* (monitor) must declare its own boundary.

    PR #1102 review (P1 semantic leak): ``DualTrackRicciMonitor`` re-expresses a
    Layer-B descriptor as margin/herding language, so it must carry a
    machine-readable boundary marking those outputs as advisory transforms, not
    a validated physical or trading claim.
    """

    def test_monitor_declares_descriptor_consumer_boundary(self) -> None:
        monitor = DualTrackRicciMonitor()
        boundary = monitor.descriptor_consumer_boundary
        assert "advisory" in boundary
        assert "not_validated" in boundary
        # class-level so static consumers can read it without instantiating
        assert DualTrackRicciMonitor.descriptor_consumer_boundary == boundary

    def test_degenerate_price_input_recorded_not_crashed(self) -> None:
        # A constant (zero-variance) column yields NaN correlations from
        # corrcoef. They must be excluded and counted, not crash and not
        # zero-filled into phantom no-edges. Output stays a finite descriptor.
        frc = FormanRicciCurvature(threshold=0.3)
        rng = np.random.default_rng(0)
        prices = 100 + np.cumsum(rng.normal(0, 1, (40, 4)), axis=0)
        prices[:, 1] = 100.0  # degenerate constant column
        result = frc.compute_from_prices(prices, window=20)
        assert isinstance(result, FormanRicciResult)
        assert np.isfinite(result.kappa_mean)
        # the degenerate column's correlations are undefined → recorded, excluded
        assert result.nonfinite_input_count > 0
        assert all(1 not in edge for edge in result.edge_curvatures)


class TestIssue1101DescriptorContract:
    """Issue #1101 verbatim descriptor-contract tests (GAP-001..004).

    Thin, exact-named locks over behaviour already covered by the
    representation-honesty / layer-boundary suites above. They exist so the
    machine-readable claim-boundary, non-finite, undefined-correlation and
    descriptor-consumer contracts named in #1101 are each pinned under their
    issue-canonical name. No source behaviour changes — these assert the
    current, already-implemented contract.
    """

    def test_result_declares_layer_claim_boundary_and_projection_policy(self) -> None:
        """GAP-001: the result carries layer, claim-boundary and projection
        policy so ``herding_index`` cannot be read as a physical or trading
        claim without an explicit validation artifact."""
        frc = FormanRicciCurvature(threshold=0.3)
        corr = np.full((4, 4), 0.8)
        np.fill_diagonal(corr, 1.0)
        result = frc.compute_from_correlation(corr)
        assert result.layer == "market_descriptor"
        assert result.physical_claim is False
        assert result.claim_boundary == "derived_unsigned_unweighted_topology_descriptor"
        assert result.projection_policy == "abs_correlation_threshold_binary"

    def test_nonfinite_correlation_rejected_before_projection(self) -> None:
        """GAP-002: non-finite (NaN/inf) correlations are not projected into the
        topology silently.

        The implementation chose the issue's OR-clause ("emit explicit
        nonfinite_policy metadata") over the ValueError option: non-finite
        inputs are excluded from the adjacency BEFORE projection and recorded
        via ``nonfinite_input_count``, with the policy declared on
        ``nan_policy``. This is the auditable-exclusion contract, NOT a raised
        error — critically, an ``inf`` (where ``np.abs(inf) > threshold`` is
        True) must never fabricate a phantom edge.
        """
        frc = FormanRicciCurvature(threshold=0.5)
        n = 4
        corr = np.full((n, n), 0.9)
        np.fill_diagonal(corr, 1.0)
        corr[0, 1] = corr[1, 0] = np.nan
        corr[2, 3] = corr[3, 2] = np.inf
        result = frc.compute_from_correlation(corr)
        assert result.nan_policy == "nonfinite_excluded_and_recorded"
        # 2 symmetric off-diagonal pairs = 4 non-finite entries recorded.
        assert result.nonfinite_input_count == 4
        # Neither the NaN nor the inf pair becomes an edge (no phantom edge).
        assert (0, 1) not in result.edge_curvatures
        assert (2, 3) not in result.edge_curvatures
        # A genuinely finite strong edge survives the exclusion.
        assert (0, 2) in result.edge_curvatures

    def test_undefined_correlation_not_silently_zeroed_without_policy(self) -> None:
        """GAP-003: an undefined correlation (zero-variance column → NaN from
        ``corrcoef``) is not silently zero-filled below threshold.

        ``compute_from_prices`` passes the raw correlation through rather than
        ``nan_to_num``, so the undefined entries are excluded and counted
        (``nonfinite_input_count > 0``) under the declared ``nan_policy`` — the
        provenance is explicit, not a masked below-threshold zero.
        """
        frc = FormanRicciCurvature(threshold=0.3)
        rng = np.random.default_rng(0)
        prices = 100 + np.cumsum(rng.normal(0, 1, (40, 4)), axis=0)
        prices[:, 1] = 100.0  # degenerate constant column → undefined corr
        result = frc.compute_from_prices(prices, window=20)
        assert result.nan_policy == "nonfinite_excluded_and_recorded"
        assert result.nonfinite_input_count > 0
        # The undefined column never silently becomes a zero-weight edge.
        assert all(1 not in edge for edge in result.edge_curvatures)

    def test_dual_track_monitor_exposes_descriptor_consumer_boundary(self) -> None:
        """GAP-004: the descriptor consumer declares, machine-readably, that its
        margin/herding outputs are advisory transforms — not physics validation
        or trading readiness."""
        monitor = DualTrackRicciMonitor()
        boundary = monitor.descriptor_consumer_boundary
        assert "advisory" in boundary
        assert "not_validated" in boundary
        # Readable statically without instantiating, for consumers at the boundary.
        assert DualTrackRicciMonitor.descriptor_consumer_boundary == boundary


def _result(kappa_min: float) -> FormanRicciResult:
    """A minimal result carrying only the kappa_min the trend fit reads."""
    return FormanRicciResult(
        edge_curvatures={},
        kappa_min=kappa_min,
        kappa_mean=kappa_min,
        kappa_max=kappa_min,
        herding_index=0.0,
    )


class TestFragilityTrendGuards:
    """The κ_min slope needs at least two points; below that it must abstain."""

    def test_rising_kappa_min_gives_positive_trend(self) -> None:
        """>= 2 history points with rising κ_min yield a positive slope.

        Pins :396 (`len(history) < 2`) and :400 (`len(kappas) < 2`): under Lt->GtE
        either guard would abstain (return 0.0) exactly when enough points exist,
        erasing a real fragility trend.
        """
        monitor = DualTrackRicciMonitor()
        monitor._history.extend(_result(k) for k in (-0.9, -0.5, -0.1))
        assert monitor.fragility_trend() > 0.0

    def test_single_point_history_abstains(self) -> None:
        """< 2 points: no slope is defined, so the trend is exactly 0.0."""
        monitor = DualTrackRicciMonitor()
        monitor._history.append(_result(-0.5))
        assert monitor.fragility_trend() == 0.0


def test_compute_from_prices_uses_only_the_trailing_window() -> None:
    """`returns.shape[0] > window` selects the trailing `window` returns.

    Rule-Zero note: this guards the ESTIMATION WINDOW, not the curvature law --
    κ is still computed by the unchanged Forman routine on the selected
    correlation. Under Gt->LtE the slice inverts to use ALL returns, so a long
    history with a different early regime would shift κ_min. Pinned by requiring
    the full-history result to equal the result on just the trailing window.
    """
    frc = FormanRicciCurvature(threshold=0.3)
    rng = np.random.default_rng(7)
    # Early regime: 8 steps of independent noise; late regime: 5 steps where all
    # three assets move together (high correlation) -> different κ than the whole.
    early = rng.normal(0.0, 1.0, size=(8, 3))
    common = rng.normal(0.0, 1.0, size=(5, 1))
    late = common + 0.01 * rng.normal(0.0, 1.0, size=(5, 3))
    returns = np.vstack([early, late])
    prices = 100.0 * np.exp(np.cumsum(returns, axis=0))  # (13, 3) positive prices

    full = frc.compute_from_prices(prices, window=5)
    trailing = frc.compute_from_prices(prices[-6:], window=5)  # exactly 5 returns
    assert full.kappa_min == pytest.approx(trailing.kappa_min)
