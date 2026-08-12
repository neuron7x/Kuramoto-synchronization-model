# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""P-axis Phase 4 — PolicyRegistry + apply_policy_change hot-swap path.

Contract summary
----------------
PR-1  ``register(name, factory)`` rejects duplicate and empty names.
PR-2  ``resolve(name)`` calls the factory and returns a
      protocol-compliant policy; raises KeyError on miss.
PR-3  ``apply_policy_change`` looks up by name and swaps atomically;
      returns the previous policy.
PR-4  A resolve failure leaves the modulator untouched.
PR-5  A factory that returns something that is not ModulationPolicy
      triggers TypeError before the swap.
"""

from __future__ import annotations

import pytest

from cortex_service.app.config import RegimeSettings
from cortex_service.app.modulation.regime import (
    ExponentialDecayPolicy,
    ModulationPolicy,
    PolicyRegistry,
    RegimeModulator,
    apply_policy_change,
)


def _settings() -> RegimeSettings:
    return RegimeSettings(decay=0.3, min_valence=-1.0, max_valence=1.0, confidence_floor=0.1)


class _FlatPolicy:
    def __init__(self, valence: float, confidence: float) -> None:
        self.v = valence
        self.c = confidence

    def compute(self, previous, feedback, volatility):  # noqa: D401 - protocol impl
        return self.v, self.c


class TestRegistryBasics:
    def test_register_rejects_empty_name(self) -> None:
        reg = PolicyRegistry()
        with pytest.raises(ValueError, match="non-empty"):
            reg.register("", lambda: _FlatPolicy(0, 0))

    def test_register_rejects_duplicate_name(self) -> None:
        reg = PolicyRegistry()
        reg.register("A", lambda: _FlatPolicy(0, 0))
        with pytest.raises(ValueError, match="already registered"):
            reg.register("A", lambda: _FlatPolicy(1, 1))

    def test_resolve_unknown_raises_keyerror(self) -> None:
        reg = PolicyRegistry()
        with pytest.raises(KeyError, match="unknown policy"):
            reg.resolve("nope")

    def test_known_lists_registered_names(self) -> None:
        reg = PolicyRegistry()
        reg.register("B", lambda: _FlatPolicy(0, 0))
        reg.register("A", lambda: _FlatPolicy(0, 0))
        assert reg.known() == ("A", "B")

    def test_factory_must_produce_modulation_policy(self) -> None:
        reg = PolicyRegistry()
        # ``object()`` deliberately does not satisfy ModulationPolicy — we
        # want the registry to reject it on resolve rather than let a
        # non-policy land inside the modulator. ``type: ignore`` is the
        # correct surface: the bug we test is *runtime*, and mypy would
        # otherwise (correctly) stop the attack at compile time.
        reg.register("bad", lambda: object())  # type: ignore[arg-type,return-value]
        with pytest.raises(TypeError, match="ModulationPolicy"):
            reg.resolve("bad")


class TestApplyPolicyChange:
    def test_swap_via_registry_returns_previous(self) -> None:
        mod = RegimeModulator(_settings())
        registry = PolicyRegistry()
        registry.register("flat", lambda: _FlatPolicy(0.5, 0.5))
        previous = apply_policy_change(mod, registry, "flat")
        assert isinstance(previous, ExponentialDecayPolicy)
        assert isinstance(mod.policy, _FlatPolicy)

    def test_unknown_name_leaves_modulator_intact(self) -> None:
        mod = RegimeModulator(_settings())
        original = mod.policy
        registry = PolicyRegistry()
        with pytest.raises(KeyError):
            apply_policy_change(mod, registry, "missing")
        assert mod.policy is original

    def test_modulation_policy_protocol_runtime_check(self) -> None:
        mod = RegimeModulator(_settings())
        registry = PolicyRegistry()
        registry.register("flat", lambda: _FlatPolicy(0.5, 0.5))
        apply_policy_change(mod, registry, "flat")
        assert isinstance(mod.policy, ModulationPolicy)
