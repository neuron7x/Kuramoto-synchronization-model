# SPDX-License-Identifier: MIT
"""T17 (exact-zero companion) — INV-CB1 universal property + bit-pattern witness.

The companion file (`test_T17_cryptobiosis.py`) verifies INV-CB1 on
a single hand-driven path (ACTIVE → VITRIFYING → DORMANT) using
``result["multiplier"] == 0.0``. INV-CB1 is universal: **every**
state transition that lands in DORMANT must yield ``multiplier ==
0.0`` exactly — bitwise, not approximately.

This file closes the gap with three orthogonal probes:

1. **Hypothesis fuzz over distress sequences** — random T-trajectories
   that drive the controller through arbitrary state sequences. At
   every tick where ``state == DORMANT``, assert
   ``multiplier == 0.0`` and the IEEE-754 byte pattern is the
   canonical positive-zero (no negative zero, no denormal).
2. **Re-entry after rehydration** — drive into DORMANT, partially
   rehydrate, force back into DORMANT, assert exactness preserved.
3. **Bit-pattern witness** — pack the multiplier into 8 raw bytes
   and assert all are 0x00. This catches a subtle class of bug
   where ``-0.0`` or denormal-tiny values would compare equal to
   ``0.0`` under ``==`` but break downstream multiplication
   semantics on edge platforms.
"""

from __future__ import annotations

import struct

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.neuro.cryptobiosis import (
    CryptobiosisConfig,
    CryptobiosisController,
    CryptobiosisState,
)

_POSITIVE_ZERO_BYTES: bytes = struct.pack("<d", 0.0)


def _assert_exact_positive_zero(label: str, multiplier: float, **params: object) -> None:
    """Assert multiplier is bitwise +0.0, not just == 0.0.

    Catches: -0.0 (which compares == 0.0 but has different sign bit),
    denormals (compare > 0 but underflow), and platform-specific
    representations.
    """
    raw = struct.pack("<d", multiplier)
    assert raw == _POSITIVE_ZERO_BYTES, (
        f"INV-CB1 BIT-PATTERN VIOLATED on {label}: "
        f"multiplier={multiplier!r} packs to {raw.hex()}, "
        f"expected canonical +0.0 = {_POSITIVE_ZERO_BYTES.hex()}. "
        f"Observed at params={params}. "
        "Physical reasoning: -0.0 or denormal multipliers compare == "
        "0.0 in Python but produce different products in BLAS / GPU "
        "kernels. Safety mandates the IEEE canonical positive zero."
    )


# ---------------------------------------------------------------------------
# Hypothesis fuzz: every DORMANT tick has exact zero
# ---------------------------------------------------------------------------


@given(
    seed=st.integers(min_value=0, max_value=2**31 - 1),
    n_ticks=st.integers(min_value=10, max_value=200),
    high_distress_prob=st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
    ),
)
@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_inv_cb1_property_every_dormant_tick_exactly_zero(
    seed: int, n_ticks: int, high_distress_prob: float
) -> None:
    """INV-CB1: at every tick where state == DORMANT, multiplier == +0.0 exactly."""
    import numpy as np

    rng = np.random.default_rng(seed=seed)
    ctrl = CryptobiosisController()
    distresses = np.where(
        rng.uniform(0.0, 1.0, size=n_ticks) < high_distress_prob,
        rng.uniform(0.85, 1.0, size=n_ticks),  # high distress → DORMANT
        rng.uniform(0.0, 0.4, size=n_ticks),  # low distress → ACTIVE/REHYDRATING
    )
    for tick, T in enumerate(distresses.tolist()):
        result = ctrl.update(T=float(T))
        if ctrl.state == CryptobiosisState.DORMANT:
            assert result["multiplier"] == 0.0, (
                f"INV-CB1 VIOLATED at tick {tick}: state=DORMANT but "
                f"multiplier={result['multiplier']!r} ≠ 0.0; DORMANT must "
                f"yield exactly 0.0 (tun state has zero metabolism). "
                f"Observed at seed={seed}, n_ticks={n_ticks}, "
                f"high_distress_prob={high_distress_prob}, T={T}."
            )
            _assert_exact_positive_zero(
                "fuzz",
                result["multiplier"],
                tick=tick,
                seed=seed,
                T=T,
            )


# ---------------------------------------------------------------------------
# Re-entry: rehydrate then re-enter DORMANT
# ---------------------------------------------------------------------------


def test_inv_cb1_re_entry_after_rehydration_preserves_exact_zero() -> None:
    """INV-CB1 (with INV-CB8): re-entered DORMANT also yields exact +0.0.

    Drives the deterministic path DORMANT → REHYDRATING → DORMANT and
    asserts the multiplier is bitwise +0.0 on *both* DORMANT visits. The
    re-entry is forced by INV-CB8 (T ≥ entry during rehydration aborts
    straight back to DORMANT), so no probabilistic ``skip`` is needed: the
    state machine guarantees the transition for ``T < exit`` then
    ``T ≥ entry``.
    """
    cfg = CryptobiosisConfig()
    ctrl = CryptobiosisController(cfg)

    # First entry into DORMANT: ACTIVE → VITRIFYING → DORMANT (INV-CB2 O(1)).
    ctrl.update(T=0.95)  # VITRIFYING
    result = ctrl.update(T=0.95)  # DORMANT
    assert ctrl.state == CryptobiosisState.DORMANT, (
        f"INV-CB1 SETUP: expected DORMANT after VITRIFYING, "
        f"got {ctrl.state.value} at entry={cfg.entry_threshold} with T=0.95."
    )
    _assert_exact_positive_zero("first_dormant", result["multiplier"], entry=cfg.entry_threshold)

    # Begin rehydration: T < exit ⟹ DORMANT → REHYDRATING (INV-CB7 hysteresis).
    ctrl.update(T=0.0)
    assert ctrl.state == CryptobiosisState.REHYDRATING, (
        f"INV-CB1 SETUP: expected REHYDRATING after T < exit, "
        f"got {ctrl.state.value} at exit={cfg.exit_threshold} with T=0.0."
    )

    # Force re-entry deterministically: INV-CB8 aborts REHYDRATING → DORMANT
    # when T ≥ entry. One tick is sufficient; this is not probabilistic.
    result = ctrl.update(T=0.99)
    assert ctrl.state == CryptobiosisState.DORMANT, (
        f"INV-CB8 VIOLATED: with T=0.99 at entry={cfg.entry_threshold} during "
        f"REHYDRATING must abort to DORMANT, got {ctrl.state.value}. "
        "Physical reasoning: returning distress must re-enter the tun state, "
        "not continue ramping risk back up."
    )
    _assert_exact_positive_zero("re_entered_dormant", result["multiplier"], entry=cfg.entry_threshold)


# ---------------------------------------------------------------------------
# Direct multiplier-property exact-zero check
# ---------------------------------------------------------------------------


def test_inv_cb1_property_returns_canonical_positive_zero_when_dormant() -> None:
    """INV-CB1: both the property and update() dict return +0.0 in DORMANT.

    Universal probe: drives several DORMANT ticks and asserts the
    multiplier is canonical +0.0 via *both* surfaces (the
    :attr:`multiplier` property and the public ``update()`` payload)
    on every tick. Two independent surfaces times many ticks gives a
    property-style witness, not a single-point check.
    """
    ctrl = CryptobiosisController()
    ctrl.update(T=0.99)  # VITRIFYING
    ctrl.update(T=0.99)  # DORMANT
    assert ctrl.state == CryptobiosisState.DORMANT, (
        f"INV-CB1 SETUP: expected DORMANT, got {ctrl.state.value} "
        "with T=0.99 (high distress must reach the tun state)."
    )
    for tick in range(5):
        state_dict = ctrl.update(T=0.99)
        assert ctrl.state == CryptobiosisState.DORMANT, (
            f"INV-CB1 SETUP: tick {tick} left DORMANT unexpectedly "
            f"({ctrl.state.value}) with T=0.99 during sustained distress."
        )
        # Surface 1: the property accessor.
        _assert_exact_positive_zero("property_access_in_dormant", ctrl.multiplier, tick=tick)
        # Surface 2: the update() return payload.
        _assert_exact_positive_zero("update_dict_in_dormant", state_dict["multiplier"], tick=tick)


def test_inv_cb1_zero_is_immutable_under_repeated_dormant_updates() -> None:
    """INV-CB1: 20 repeated high-distress DORMANT updates keep multiplier +0.0."""
    ctrl = CryptobiosisController()
    ctrl.update(T=0.99)
    ctrl.update(T=0.99)
    assert ctrl.state == CryptobiosisState.DORMANT, (
        f"INV-CB1 SETUP: expected DORMANT, got {ctrl.state.value} with T=0.99."
    )
    for tick in range(20):
        result = ctrl.update(T=0.99)
        # The contract is conditional on DORMANT — only check there.
        assert ctrl.state == CryptobiosisState.DORMANT, (
            f"INV-CB1 SETUP: tick {tick} must remain DORMANT under sustained "
            f"distress, got {ctrl.state.value} with T=0.99."
        )
        # Bit-pattern check is strictly stronger than `== 0.0`: it rejects
        # -0.0 and denormals that would compare equal but break downstream
        # products. No magic-number threshold is used (exact +0.0 contract).
        _assert_exact_positive_zero(
            "repeated_dormant_update",
            result["multiplier"],
            tick=tick,
        )
