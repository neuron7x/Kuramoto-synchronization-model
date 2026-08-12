# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Integration invariants for the CoherenceBridge GeoSync adapter.

Ledger id: coherence-bridge-geosync-adapter (PARTIAL -> OPERATIONAL, ADD_TEST).
Source module: coherence_bridge/geosync_adapter.py.

MECHANISM
---------
``GeoSyncAdapter`` is a transport-agnostic bridge: it maps GeoSync physics-kernel
outputs (Kuramoto order parameter ``R``, augmented-Forman Ricci ``kappa``, gamma,
Lyapunov, regime) onto the 12-field ``SignalEngine`` contract that downstream risk
gates consume. These tests exercise the adapter end-to-end on deterministic,
synthetic OHLCV (no live server, no real market data) and assert that the two
physics invariants the ledger binds to this adapter are *preserved* through the
relay, not merely re-derived inside it.

  * INV-K1 (Kuramoto order parameter): R in [0, 1]. The adapter relays
    ``order_parameter_R`` from ``GeoSyncCompositeEngine``; the relayed value must
    stay inside the unit interval for every emitted signal.
  * INV-RC1 (Ollivier-Ricci universal upper bound): kappa <= 1 per edge of any
    connected weighted graph. INV-RC1 governs the *Ollivier* curvature operator
    (``core.indicators.ricci.ricci_curvature_edge``), NOT the augmented-Forman
    blend the adapter happens to expose in its ``ricci_curvature`` field (Forman
    curvature is legitimately unbounded above; ``invariants.verify_T5`` classifies
    that field as P1/finite-only). The honest preservation check is therefore on
    the Ollivier operator over the same lagged-return topology the adapter builds.

VALIDITY
--------
Synthetic-only. OHLCV is generated from a seeded ``numpy`` Generator so every run
is bit-reproducible; the transport is the in-process adapter (or the deterministic
``MockEngine`` for the upstream-fault path), never a network socket. No claim about
real markets is made or implied.

FALSIFIER
---------
The adapter is advisory and read-only: it must NOT mutate or fabricate invariant
values. If an *upstream* engine emits an out-of-band value (R > 1, or non-finite
kappa), a faithful bridge relays it verbatim and the contract verifier *flags* it
(``InvariantViolation``) rather than silently coercing it into a plausible in-band
number. A test that observes the bridge quietly clamping R = 1.5 down to 1.0 -- or
the Ollivier operator returning kappa > 1 + eps on a connected graph -- refutes the
preservation claim and must fail loudly.

NON-CLAIM
---------
Advisory transport adapter, read-only; does not create scientific claims;
synthetic-only. These tests verify contract preservation, not market edge.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from coherence_bridge.geosync_adapter import GeoSyncAdapter
from coherence_bridge.invariants import (
    InvariantViolation,
    verify_signal,
    verify_T4,
)
from coherence_bridge.mock_engine import MockEngine
from coherence_bridge.physics_contract import (
    BridgeDecision,
    PhysicsContractStatus,
    validate_physics_contract,
)
from coherence_bridge.server import _sanitize_signal
from core.indicators.ricci import build_price_graph, ricci_curvature_edge

pytestmark = pytest.mark.integration

# --- Formula-derived tolerances (no magic numbers) ---------------------------
# INV-RC1 numerical slack: identical to the canonical Ollivier-Ricci geometry
# witness (tests/physics_contracts/test_ricci_geometry_witnesses.py:CURVATURE_EPS).
# It absorbs only floating-point rounding in the optimal-transport solve; the
# definitional bound is kappa <= 1, so the admissible ceiling is 1 + eps.
CURVATURE_EPS: float = 1e-9
KAPPA_UPPER_BOUND: float = 1.0 + CURVATURE_EPS

# INV-K1 is an exact closed interval [0, 1] for the Kuramoto order parameter; the
# adapter rounds emitted floats to 6 decimals, so the only slack we admit is that
# half-ulp-of-rounding, well below any physical scale.
R_ROUNDING_EPS: float = 0.5e-6
R_LOWER_BOUND: float = 0.0 - R_ROUNDING_EPS
R_UPPER_BOUND: float = 1.0 + R_ROUNDING_EPS

# Synthetic-data shape: enough bars to clear the adapter's len(df) >= 30 gate and
# to give the Ollivier price-graph a non-trivial node set.
_N_BARS: int = 200
_SEEDS: tuple[int, ...] = (1, 7, 42, 99, 2026)


def _synthetic_ohlcv(seed: int, n: int = _N_BARS) -> pd.DataFrame:
    """Deterministic geometric-random-walk OHLCV with a DatetimeIndex.

    Pure function of ``seed`` via ``numpy.random.default_rng`` -- no global state,
    no real data. Shape matches the adapter's ``update_market_data`` contract
    (close/high/low/open/volume columns + DatetimeIndex).
    """
    rng = np.random.default_rng(seed)
    log_returns = rng.standard_normal(n) * 1e-3
    close = 1.10 * np.exp(np.cumsum(log_returns))
    high = close * (1.0 + np.abs(rng.standard_normal(n)) * 5e-4)
    low = close * (1.0 - np.abs(rng.standard_normal(n)) * 5e-4)
    open_ = np.concatenate([[close[0]], close[:-1]])
    volume = rng.integers(100, 1000, n).astype(float)
    index = pd.date_range("2024-01-01", periods=n, freq="min")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )


def _adapter_signals() -> list[dict[str, object]]:
    """Drive the real adapter over every seed and collect the emitted signals."""
    adapter = GeoSyncAdapter()
    instrument = adapter.instruments[0]
    signals: list[dict[str, object]] = []
    for seed in _SEEDS:
        adapter.update_market_data(instrument, _synthetic_ohlcv(seed))
        sig = adapter.get_signal(instrument)
        assert sig is not None, f"adapter returned no signal for seed={seed}"
        signals.append(sig)
    return signals


# --- INV-K1: Kuramoto R in [0, 1], preserved through the adapter -------------


def test_inv_k1_order_parameter_relayed_in_unit_interval() -> None:
    """End-to-end: every R the adapter relays stays inside [0, 1] (INV-K1)."""
    for seed, sig in zip(_SEEDS, _adapter_signals()):
        r = sig["order_parameter_R"]
        assert isinstance(r, float)
        assert R_LOWER_BOUND <= r <= R_UPPER_BOUND, (
            f"INV-K1 violated: seed={seed} order_parameter_R={r:.6f} "
            f"outside [{R_LOWER_BOUND}, {R_UPPER_BOUND}]"
        )
        # Scope to the invariant THIS ledger entry binds: T4 == INV-K1. Other
        # theorems (e.g. T3 gamma >= 0) are governed by their own ledger entries
        # and may legitimately be relayed out-of-band by this advisory adapter --
        # asserting them here would test a different contract.
        t4 = verify_T4(_sanitize_signal(sig))
        assert t4.passed, f"seed={seed} INV-K1 contract failure: {t4.message}"


# --- INV-RC1: Ollivier kappa <= 1, preserved over the adapter's topology -----


def test_inv_rc1_ollivier_bound_on_adapter_lagged_topology() -> None:
    """The Ollivier operator INV-RC1 governs stays <= 1 on the adapter's series.

    The adapter builds curvature from lagged log-returns of the close series; we
    rebuild the *Ollivier* price graph over the same close prices and assert the
    universal per-edge upper bound holds. This is the curvature notion INV-RC1
    binds -- the adapter's Forman-blend ``ricci_curvature`` field is deliberately
    NOT asserted <= 1 (Forman curvature is unbounded above; see module docstring).
    """
    for seed in _SEEDS:
        prices = _synthetic_ohlcv(seed)["close"].to_numpy(dtype=np.float64)
        graph = build_price_graph(prices)
        edges = list(graph.edges())
        assert edges, f"seed={seed} produced an empty Ollivier price graph"
        worst = max(ricci_curvature_edge(graph, int(u), int(v)) for u, v in edges)
        assert worst <= KAPPA_UPPER_BOUND, (
            f"INV-RC1 violated: seed={seed} worst Ollivier kappa={worst:.12f} "
            f"exceeds bound {KAPPA_UPPER_BOUND:.12f}"
        )


# --- Falsifier: advisory / read-only / transport-agnostic --------------------


def test_adapter_does_not_fabricate_or_mutate_in_band_values() -> None:
    """Read-only relay: in-band upstream values pass through byte-for-byte.

    The deterministic ``MockEngine`` is a stand-in transport. A faithful bridge
    relays its physics fields verbatim -- it neither rescales nor regenerates R,
    kappa, gamma. We assert the relayed (sanitized) signal preserves the exact
    upstream values for an in-band sample.
    """
    engine = MockEngine()
    instrument = engine.instruments[0]
    upstream = engine.get_signal(instrument)
    assert upstream is not None
    relayed = _sanitize_signal(upstream)
    for field in ("order_parameter_R", "ricci_curvature", "gamma", "lyapunov_max"):
        assert relayed[field] == upstream[field], (
            f"advisory contract violated: {field} mutated {upstream[field]!r} -> {relayed[field]!r}"
        )


def test_out_of_band_upstream_R_is_flagged_not_coerced() -> None:
    """Out-of-band R from upstream is refused/flagged, never silently clamped.

    Falsifier for the preservation claim: if the bridge quietly coerced an
    out-of-range R = 1.5 down into [0, 1], INV-K1 would *look* preserved while the
    physics was being fabricated. A read-only bridge must instead relay 1.5 and let
    the contract verifier raise InvariantViolation(T4).
    """
    poisoned: dict[str, object] = {
        "timestamp_ns": 1_700_000_000_000_000_000,
        "instrument": "EURUSD",
        "gamma": 1.0,
        "order_parameter_R": 1.5,  # deliberately > 1
        "ricci_curvature": 0.0,
        "lyapunov_max": 0.0,
        "regime": "METASTABLE",
        "regime_confidence": 0.7,
        "regime_duration_s": 1.0,
        "signal_strength": 0.0,
        "risk_scalar": 1.0,
        "sequence_number": 0,
    }
    relayed = _sanitize_signal(poisoned)
    # 1. Not coerced: the bridge relays the out-of-band value verbatim.
    assert relayed["order_parameter_R"] == 1.5, (
        "INV-K1 falsifier: bridge silently coerced out-of-band R into [0, 1]"
    )
    # 2. Flagged: the contract verifier refuses the signal on T4 (INV-K1).
    assert not verify_T4(relayed).passed
    with pytest.raises(InvariantViolation) as exc_info:
        verify_signal(relayed)
    assert exc_info.value.theorem == "T4"


def test_non_finite_upstream_kappa_is_flagged_not_coerced() -> None:
    """Non-finite kappa from upstream is flagged (T5), never fabricated to 0.

    Mirror falsifier for INV-RC1's relay: the bridge must not invent a finite
    curvature when upstream is broken. ``_sanitize_signal`` only fail-closes on
    non-finite *gamma*; a non-finite kappa with finite gamma is left intact so the
    verifier can refuse it on T5.
    """
    poisoned: dict[str, object] = {
        "timestamp_ns": 1_700_000_000_000_000_000,
        "instrument": "EURUSD",
        "gamma": 1.0,
        "order_parameter_R": 0.5,
        "ricci_curvature": float("inf"),  # deliberately non-finite
        "lyapunov_max": 0.0,
        "regime": "METASTABLE",
        "regime_confidence": 0.7,
        "regime_duration_s": 1.0,
        "signal_strength": 0.0,
        "risk_scalar": 0.0,
        "sequence_number": 0,
    }
    relayed = _sanitize_signal(poisoned)
    # Not fabricated: kappa relayed verbatim (still non-finite).
    assert relayed["ricci_curvature"] == float("inf")
    with pytest.raises(InvariantViolation) as exc_info:
        verify_signal(relayed)
    assert exc_info.value.theorem == "T5"


# --- INV-CBR1: fail-closed physics-contract gate (Ollivier vs Forman split) --


def _base_signal(**overrides: object) -> dict[str, object]:
    """A fully in-band relayed signal; tests override one field at a time."""
    sig: dict[str, object] = {
        "timestamp_ns": 1_700_000_000_000_000_000,
        "instrument": "EURUSD",
        "gamma": 1.0,
        "order_parameter_R": 0.5,
        "augmented_forman_ricci": 0.2,
        "ollivier_kappa": 0.1,
        "ricci_curvature": 0.2,
        "lyapunov_max": 0.0,
        "regime": "METASTABLE",
        "regime_confidence": 0.7,
        "regime_duration_s": 1.0,
        "signal_strength": 0.0,
        "risk_scalar": 1.0,
        "sequence_number": 0,
    }
    sig.update(overrides)
    return sig


def test_cbr1_in_band_signal_is_valid_and_passes() -> None:
    """A fully in-band signal yields VALID / PASS with a bounded risk scalar."""
    verdict = validate_physics_contract(_base_signal())
    assert verdict.status is PhysicsContractStatus.VALID
    assert verdict.decision is BridgeDecision.PASS
    assert 0.0 <= verdict.safe_risk_scalar <= 1.0


def test_cbr1_negative_gamma_fails_closed() -> None:
    """Out-of-band NEGATIVE gamma (the documented relay hazard) fails closed.

    gamma is a spectral exponent only meaningful on gamma ≥ 0. A negative value
    must yield INVALID_PHYSICS_CONTRACT / NO_GO and force risk to the safe floor
    0.0 — never a non-zero risk handed to the risk layer.
    """
    verdict = validate_physics_contract(_base_signal(gamma=-0.5))
    assert verdict.status is PhysicsContractStatus.INVALID_PHYSICS_CONTRACT
    assert verdict.decision is BridgeDecision.NO_GO
    assert verdict.safe_risk_scalar == 0.0
    assert any("gamma" in r and "< 0" in r for r in verdict.reasons)


def test_cbr1_forman_above_one_with_valid_ollivier_is_valid() -> None:
    """augmented_forman_ricci > 1 is LEGITIMATE and must NOT invalidate.

    Forman curvature is unbounded above; the gate checks it for finiteness only.
    With R, gamma and Ollivier κ all in-band, a Forman value of 5.0 is VALID.
    """
    verdict = validate_physics_contract(
        _base_signal(augmented_forman_ricci=5.0, ricci_curvature=5.0, ollivier_kappa=0.3)
    )
    assert verdict.status is PhysicsContractStatus.VALID, verdict.reasons


def test_cbr1_forman_above_one_does_not_trip_rc1() -> None:
    """Direct proof: a Forman value > 1 is never reported as an INV-RC1 breach.

    Even a large Forman blend produces no INV-RC1 reason (that bound governs the
    Ollivier operator only); the only κ-bound check is against ollivier_kappa.
    """
    verdict = validate_physics_contract(
        _base_signal(augmented_forman_ricci=42.0, ricci_curvature=42.0, ollivier_kappa=0.9)
    )
    assert not any("INV-RC1" in r for r in verdict.reasons)
    assert verdict.status is PhysicsContractStatus.VALID


def test_cbr1_ollivier_above_one_fails_closed() -> None:
    """ollivier_kappa > 1 violates INV-RC1 ⇒ fail-closed (the κ-bound field).

    Distinct from the Forman case: the Ollivier operator IS κ-bounded, so a
    value above 1 + ε is a real violation and must fail closed.
    """
    verdict = validate_physics_contract(_base_signal(ollivier_kappa=1.5))
    assert verdict.status is PhysicsContractStatus.INVALID_PHYSICS_CONTRACT
    assert verdict.decision is BridgeDecision.NO_GO
    assert verdict.safe_risk_scalar == 0.0
    assert any("INV-RC1" in r for r in verdict.reasons)


def test_cbr1_out_of_band_R_fails_closed() -> None:
    """R outside [0,1] (INV-K1) fails the contract closed."""
    verdict = validate_physics_contract(_base_signal(order_parameter_R=1.5))
    assert verdict.status is PhysicsContractStatus.INVALID_PHYSICS_CONTRACT
    assert any("INV-K1" in r for r in verdict.reasons)


def test_cbr1_non_finite_gamma_fails_closed() -> None:
    """Non-finite gamma fails closed (T3 accepted domain)."""
    verdict = validate_physics_contract(_base_signal(gamma=float("nan")))
    assert verdict.status is PhysicsContractStatus.INVALID_PHYSICS_CONTRACT
    assert verdict.safe_risk_scalar == 0.0


def test_adapter_emits_split_ricci_fields() -> None:
    """The real adapter now emits the explicit Ollivier/Forman name split.

    augmented_forman_ricci (the blend) and ollivier_kappa (the κ-bound operator)
    are distinct fields; ricci_curvature is retained as the backward-compatible
    display alias of the Forman blend.
    """
    for sig in _adapter_signals():
        assert "augmented_forman_ricci" in sig
        assert "ollivier_kappa" in sig
        # Display alias equals the Forman blend (not the Ollivier field).
        assert sig["ricci_curvature"] == sig["augmented_forman_ricci"]
