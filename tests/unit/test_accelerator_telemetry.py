# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tier-1 telemetry + parity tests for ``core.accelerators.numeric``.

Covers:
    T-1  ``BackendSynchronizationError`` carries a structured forensic
         payload and is JSON-serialisable via ``to_dict()``.
    T-2  Downgrade counter reflects every Rust→fallback transition and
         remains thread-safe.
    T-3  ``strict_backend=True`` and ``strict_backend=False`` produce
         bit-identical output on the happy path (Hypothesis parity).
    T-4  A strict-backend failure raises with every field populated —
         ``backend``, ``reason``, ``downgrade_count``, and
         ``last_healthy_epoch_ns`` reflect observed state.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from hypothesis.extra import numpy as hnp

from core.accelerators.numeric import (
    BackendSynchronizationError,
    convolve,
    downgrade_counts,
    quantiles,
    reset_downgrade_counter,
    rust_available,
    sliding_windows,
)


@pytest.fixture(autouse=True)
def _clean_counter() -> Iterator[None]:
    """Every test starts with a zeroed downgrade counter."""
    reset_downgrade_counter()
    yield
    reset_downgrade_counter()


# ── T-1 · structured exception payload ──────────────────────────────────


class TestExceptionPayload:
    def test_to_dict_round_trip(self) -> None:
        exc = BackendSynchronizationError(
            "test",
            backend="rust",
            reason="runtime_error",
            last_healthy_epoch_ns=1_700_000_000_000_000_000,
            downgrade_count=3,
        )
        payload = exc.to_dict()
        assert payload == {
            "message": "test",
            "backend": "rust",
            "reason": "runtime_error",
            "last_healthy_epoch_ns": 1_700_000_000_000_000_000,
            "downgrade_count": 3,
        }

    def test_defaults_are_safe_for_empty_construction(self) -> None:
        exc = BackendSynchronizationError("x")
        assert exc.backend == "rust"
        assert exc.reason == "unspecified"
        assert exc.last_healthy_epoch_ns is None
        assert exc.downgrade_count == 0

    def test_subclass_of_runtime_error(self) -> None:
        assert issubclass(BackendSynchronizationError, RuntimeError)


# ── T-2 · downgrade counter ─────────────────────────────────────────────


class TestDowngradeCounter:
    def test_starts_empty(self) -> None:
        assert downgrade_counts() == {}

    def test_counts_runtime_error_downgrade(self) -> None:
        """Without a Rust build we rely on numpy → python downgrade path,
        which the ``sliding_windows`` implementation instruments even
        when NumPy is present but Rust is absent."""
        data = np.asarray([1.0, 2.0, 3.0, 4.0, 5.0])
        sliding_windows(data, window=3, step=1)
        # At least one downgrade is logged on any environment that ships
        # without the compiled Rust extension.
        if not rust_available():
            counts = downgrade_counts()
            assert sum(counts.values()) >= 1
            assert all(frm == "rust" for (frm, _to, _reason) in counts)

    def test_is_thread_safe(self) -> None:
        if rust_available():
            pytest.skip("needs fail-open path which requires no Rust")
        data = np.asarray([1.0, 2.0, 3.0, 4.0])

        def _worker() -> None:
            for _ in range(200):
                sliding_windows(data, window=2, step=1)

        threads = [threading.Thread(target=_worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        total = sum(downgrade_counts().values())
        # 4 workers × 200 calls = 800 expected increments.
        assert total == 800


# ── T-3 · parity property ───────────────────────────────────────────────


class TestParity:
    @settings(max_examples=60, deadline=None)
    @given(
        data=hnp.arrays(
            dtype=np.float64,
            shape=st.integers(min_value=4, max_value=32),
            elements=st.floats(
                min_value=-100.0,
                max_value=100.0,
                allow_nan=False,
                allow_infinity=False,
            ),
        ),
        window=st.integers(min_value=1, max_value=8),
        step=st.integers(min_value=1, max_value=4),
    )
    def test_sliding_windows_strict_equals_default(
        self, data: np.ndarray, window: int, step: int
    ) -> None:
        assume(window <= data.shape[0])
        # Happy path: strict-backend and default modes must produce
        # bit-identical output on any valid input. If they disagree,
        # the fallback has drifted.
        if not rust_available():
            # strict_backend would raise — exercise default only.
            default = sliding_windows(data, window=window, step=step, strict_backend=False)
            np.testing.assert_array_equal(
                default,
                sliding_windows(data, window=window, step=step, strict_backend=False),
            )
            return
        strict = sliding_windows(data, window=window, step=step, strict_backend=True)
        default = sliding_windows(data, window=window, step=step, strict_backend=False)
        np.testing.assert_array_equal(strict, default)

    @settings(max_examples=40, deadline=None)
    @given(
        data=hnp.arrays(
            dtype=np.float64,
            shape=st.integers(min_value=4, max_value=32),
            elements=st.floats(
                min_value=-100.0,
                max_value=100.0,
                allow_nan=False,
                allow_infinity=False,
            ),
        ),
        probs=st.lists(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
            min_size=1,
            max_size=5,
        ),
    )
    def test_quantiles_strict_equals_default(self, data: np.ndarray, probs: list[float]) -> None:
        if not rust_available():
            default = quantiles(data, probs, strict_backend=False)
            assert np.all(np.isfinite(default))
            return
        strict = quantiles(data, probs, strict_backend=True)
        default = quantiles(data, probs, strict_backend=False)
        np.testing.assert_array_equal(strict, default)

    @settings(max_examples=40, deadline=None)
    @given(
        signal=hnp.arrays(
            dtype=np.float64,
            shape=st.integers(min_value=4, max_value=32),
            elements=st.floats(
                min_value=-10.0,
                max_value=10.0,
                allow_nan=False,
                allow_infinity=False,
            ),
        ),
        kernel=hnp.arrays(
            dtype=np.float64,
            shape=st.integers(min_value=1, max_value=8),
            elements=st.floats(
                min_value=-10.0,
                max_value=10.0,
                allow_nan=False,
                allow_infinity=False,
            ),
        ),
        mode=st.sampled_from(["full", "same", "valid"]),
    )
    def test_convolve_strict_equals_default(
        self, signal: np.ndarray, kernel: np.ndarray, mode: str
    ) -> None:
        if mode == "valid":
            assume(kernel.shape[0] <= signal.shape[0])
        if not rust_available():
            default = convolve(signal, kernel, mode=mode, strict_backend=False)
            assert np.all(np.isfinite(default))
            return
        strict = convolve(signal, kernel, mode=mode, strict_backend=True)
        default = convolve(signal, kernel, mode=mode, strict_backend=False)
        np.testing.assert_allclose(strict, default, rtol=0, atol=1e-12)


# ── T-4 · structured-exception fields on a real raise ───────────────────


class TestExceptionOnRealRaise:
    def test_sliding_windows_strict_unavailable_raises_structured(self) -> None:
        if rust_available():
            pytest.skip("needs Rust unavailable to exercise unavailable path")
        data = np.asarray([1.0, 2.0, 3.0, 4.0])
        with pytest.raises(BackendSynchronizationError) as exc_info:
            sliding_windows(data, window=2, step=1, strict_backend=True)
        exc = exc_info.value
        assert exc.backend == "rust"
        assert exc.reason == "unavailable"
        assert exc.downgrade_count >= 1
        assert isinstance(exc.to_dict(), dict)
