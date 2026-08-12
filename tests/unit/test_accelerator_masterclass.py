# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tier-2/3 polish: env-flip default + BackendHealth span contract.

Covers:
    M-1  GEOSYNC_STRICT_BACKEND env flag flips the process-wide default
         to True when set to a truthy value. Unset → legacy fail-open.
         Explicit True/False always overrides env.
    M-2  BackendHealth span records a zero-downgrade report on a happy
         block and a non-zero report on a block that triggers a
         downgrade (fail-open numpy path).
    M-3  Nested BackendHealth spans do not contaminate each other —
         inner-span delta is a strict subset of outer-span delta.
    M-4  BackendHealthReport is frozen and JSON-serialisable via
         to_dict().
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import pytest

from core.accelerators.numeric import (
    BackendHealth,
    BackendHealthReport,
    _default_strict_backend,
    _resolve_strict,
    reset_downgrade_counter,
    rust_available,
    sliding_windows,
)
from tests.fixtures.isolation import IsolatedEnv


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    reset_downgrade_counter()
    yield
    reset_downgrade_counter()


# ── M-1 · env flag contract ─────────────────────────────────────────────


class TestStrictBackendEnvFlag:
    def test_unset_env_defaults_to_false(self) -> None:
        with IsolatedEnv({"GEOSYNC_STRICT_BACKEND": None}):
            assert _default_strict_backend() is False

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "On"])
    def test_truthy_values_flip_default(self, value: str) -> None:
        with IsolatedEnv({"GEOSYNC_STRICT_BACKEND": value}):
            assert _default_strict_backend() is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "maybe"])
    def test_non_truthy_values_stay_false(self, value: str) -> None:
        with IsolatedEnv({"GEOSYNC_STRICT_BACKEND": value}):
            assert _default_strict_backend() is False

    def test_explicit_overrides_env(self) -> None:
        with IsolatedEnv({"GEOSYNC_STRICT_BACKEND": "1"}):
            # Explicit ``False`` beats env ``True``.
            assert _resolve_strict(False) is False
            # Explicit ``True`` echoed back regardless of env.
            assert _resolve_strict(True) is True
            # None delegates to env default.
            assert _resolve_strict(None) is True

    def test_env_flip_propagates_to_public_api(self) -> None:
        """End-to-end: with env=1, ``sliding_windows`` without explicit
        ``strict_backend`` behaves as strict — so on a Rust-less venv
        it raises BackendSynchronizationError."""
        if rust_available():
            pytest.skip("need rust unavailable to witness the raise")
        with IsolatedEnv({"GEOSYNC_STRICT_BACKEND": "1"}):
            data = np.asarray([1.0, 2.0, 3.0, 4.0])
            with pytest.raises(Exception) as exc:
                sliding_windows(data, window=2, step=1)
            assert "strict_backend=True" in str(exc.value)


# ── M-2 · BackendHealth basic report ────────────────────────────────────


class TestBackendHealthBasic:
    def test_zero_downgrade_report_when_block_does_nothing(self) -> None:
        with BackendHealth("empty") as span:
            pass
        report = span.report()
        assert isinstance(report, BackendHealthReport)
        assert report.n_downgrades == 0
        assert report.label == "empty"
        assert report.wall_duration_s >= 0

    def test_report_counts_downgrade_from_fail_open_call(self) -> None:
        if rust_available():
            pytest.skip("needs fail-open path → Rust absent")
        data = np.asarray([1.0, 2.0, 3.0, 4.0])
        with BackendHealth("batch") as span:
            sliding_windows(data, window=2, step=1)
            sliding_windows(data, window=2, step=1)
        report = span.report()
        assert report.n_downgrades == 2
        assert report.label == "batch"

    def test_report_is_frozen(self) -> None:
        with BackendHealth("probe") as span:
            pass
        report = span.report()
        with pytest.raises((AttributeError, Exception)):
            report.label = "tampered"  # type: ignore[misc]

    def test_report_to_dict_round_trip(self) -> None:
        if rust_available():
            pytest.skip("needs fail-open path → Rust absent")
        data = np.asarray([1.0, 2.0, 3.0, 4.0])
        with BackendHealth("audit") as span:
            sliding_windows(data, window=2, step=1)
        payload = span.report().to_dict()
        assert payload["label"] == "audit"
        assert payload["n_downgrades"] == 1
        assert "downgrades" in payload
        assert "wall_duration_s" in payload


# ── M-3 · Nested spans do not contaminate ───────────────────────────────


class TestBackendHealthNesting:
    def test_inner_delta_is_strict_subset_of_outer(self) -> None:
        if rust_available():
            pytest.skip("needs fail-open path → Rust absent")
        data = np.asarray([1.0, 2.0, 3.0, 4.0])
        with BackendHealth("outer") as outer:
            sliding_windows(data, window=2, step=1)  # outer only
            with BackendHealth("inner") as inner:
                sliding_windows(data, window=2, step=1)
                sliding_windows(data, window=2, step=1)
            sliding_windows(data, window=2, step=1)  # outer only
        outer_n = outer.report().n_downgrades
        inner_n = inner.report().n_downgrades
        assert inner_n == 2
        assert outer_n == 4
        # Inner is indeed a subset of outer (both fire on every call).


# ── M-4 · Mid-span report is safe (no exception) ────────────────────────


class TestBackendHealthMidFlight:
    def test_mid_flight_report_returns_zero(self) -> None:
        with BackendHealth("probe") as span:
            report = span.report()
            assert report.n_downgrades == 0
            assert report.wall_duration_s == 0.0
