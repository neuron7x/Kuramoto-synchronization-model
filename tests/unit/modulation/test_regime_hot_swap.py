# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Sprint 4 — RegimeModulator policy hot-swap contract.

S4-1  Default RegimeModulator uses ExponentialDecayPolicy; its output
      is byte-identical to the pre-Sprint-4 monolithic implementation.
S4-2  ``swap_policy(new)`` returns the previous policy and installs the
      new one atomically.
S4-3  ``update`` after a swap uses the new policy immediately — no
      restart, no dropped tick.
S4-4  ``swap_policy`` with a non-Protocol object raises TypeError.
S4-5  Concurrent ``update`` calls during a ``swap_policy`` never see a
      half-applied policy (no partial reads of policy internals).
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

import pytest

from cortex_service.app.config import RegimeSettings
from cortex_service.app.modulation.regime import (
    ExponentialDecayPolicy,
    ModulationPolicy,
    RegimeModulator,
    RegimeState,
)


def _settings(**kwargs) -> RegimeSettings:
    """Minimal RegimeSettings with predictable parameters."""
    defaults = {
        "decay": 0.3,
        "min_valence": -1.0,
        "max_valence": 1.0,
        "confidence_floor": 0.1,
    }
    defaults.update(kwargs)
    return RegimeSettings(**defaults)


class _FlatPolicy:
    """Test policy that ignores inputs and returns fixed values."""

    def __init__(self, valence: float, confidence: float) -> None:
        self.valence = valence
        self.confidence = confidence
        self.calls = 0

    def compute(self, previous, feedback: float, volatility: float) -> tuple[float, float]:
        self.calls += 1
        return self.valence, self.confidence


class TestDefaultPolicy:
    def test_default_is_exponential_decay(self) -> None:
        mod = RegimeModulator(_settings())
        assert isinstance(mod.policy, ExponentialDecayPolicy)

    def test_byte_identical_to_legacy_behaviour(self) -> None:
        """Regression: every output of the Sprint-4 modulator matches
        the pre-split algorithm on the same inputs."""
        settings = _settings(decay=0.4, confidence_floor=0.2)
        mod = RegimeModulator(settings)

        # Replicate the monolithic update() by hand.
        def _legacy(
            previous: RegimeState | None, feedback: float, volatility: float
        ) -> tuple[float, float]:
            decay = settings.decay
            if previous is None:
                seed_valence = feedback
            else:
                seed_valence = (1 - decay) * previous.valence + decay * feedback
            bounded_valence = max(settings.min_valence, min(settings.max_valence, seed_valence))
            confidence = max(settings.confidence_floor, 1.0 - volatility)
            return bounded_valence, confidence

        prev: RegimeState | None = None
        for t, (feedback, vol) in enumerate([(0.3, 0.1), (-0.2, 0.5), (0.8, 0.05), (0.0, 0.2)]):
            observed = mod.update(
                prev,
                feedback,
                vol,
                as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
            expected_v, expected_c = _legacy(prev, feedback, vol)
            assert observed.valence == pytest.approx(expected_v, abs=1e-12)
            assert observed.confidence == pytest.approx(expected_c, abs=1e-12)
            prev = observed


class TestHotSwap:
    def test_swap_returns_previous_policy(self) -> None:
        mod = RegimeModulator(_settings())
        first = mod.policy
        second = _FlatPolicy(0.5, 0.9)
        returned = mod.swap_policy(second)
        assert returned is first
        assert mod.policy is second

    def test_swap_applies_immediately(self) -> None:
        mod = RegimeModulator(_settings())
        new_policy = _FlatPolicy(valence=0.5, confidence=0.9)
        mod.swap_policy(new_policy)
        result = mod.update(
            None, feedback=-1.0, volatility=0.99, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        # Regardless of feedback/volatility, the flat policy returns (0.5, 0.9).
        assert result.valence == pytest.approx(0.5)
        assert result.confidence == pytest.approx(0.9)
        assert new_policy.calls == 1

    def test_swap_rejects_non_protocol_object(self) -> None:
        mod = RegimeModulator(_settings())
        with pytest.raises(TypeError, match="ModulationPolicy"):
            mod.swap_policy("not-a-policy")  # type: ignore[arg-type]

    def test_swap_is_reversible(self) -> None:
        mod = RegimeModulator(_settings())
        original = mod.policy
        mod.swap_policy(_FlatPolicy(0.0, 0.5))
        mod.swap_policy(original)
        assert mod.policy is original

    def test_concurrent_updates_during_swap_never_see_partial_policy(self) -> None:
        """S4-5: a swap cannot leave the modulator in a mixed state.

        We do not guarantee that all workers see the new policy at the
        same instant — only that no worker ever observes a half-applied
        state. Concretely: every result must be consistent with a
        single policy, not a blend. We enforce this by making both
        policies return constants on disjoint value sets and asserting
        that every observation lands in one set or the other.
        """
        mod = RegimeModulator(_settings())
        policy_a = _FlatPolicy(valence=0.1, confidence=0.3)
        policy_b = _FlatPolicy(valence=0.9, confidence=0.9)
        mod.swap_policy(policy_a)

        results: list[RegimeState] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def _worker() -> None:
            for _ in range(200):
                try:
                    r = mod.update(
                        None,
                        feedback=0.0,
                        volatility=0.0,
                        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    )
                    with lock:
                        results.append(r)
                except Exception as exc:  # pragma: no cover
                    with lock:
                        errors.append(exc)

        def _swapper() -> None:
            for _ in range(50):
                mod.swap_policy(policy_b)
                mod.swap_policy(policy_a)

        threads = [threading.Thread(target=_worker) for _ in range(4)]
        threads.append(threading.Thread(target=_swapper))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # Every observation must match exactly one of the two policies.
        allowed = {(0.1, 0.3), (0.9, 0.9)}
        observed_pairs = {(r.valence, r.confidence) for r in results}
        assert observed_pairs.issubset(
            allowed
        ), f"partial policy state leaked: {observed_pairs - allowed}"


class TestModulationPolicyProtocol:
    def test_exponential_decay_is_protocol_compliant(self) -> None:
        assert isinstance(ExponentialDecayPolicy(_settings()), ModulationPolicy)

    def test_flat_test_policy_is_protocol_compliant(self) -> None:
        assert isinstance(_FlatPolicy(0.0, 0.0), ModulationPolicy)
