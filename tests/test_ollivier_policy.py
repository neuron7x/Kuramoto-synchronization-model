# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Ollivier-κ runtime policy: typed status, pre-emptive deadline, circuit
breaker, thread-safe bounded-LRU cache, degraded mode.

Covers the operational hardening of the coherence-bridge hot path:
  * typed :class:`OllivierStatus` / :class:`OllivierResult` (no silent NaN),
  * deterministic max-edges budget + monotonic deadline checked BEFORE EACH EDGE
    (pre-emptive, not post-hoc),
  * per-instrument circuit breaker after consecutive timeouts,
  * thread-safe bounded-LRU cache (RLock + OrderedDict, no whole-cache clear),
  * degraded ⇒ ABSTAIN (field omitted) by default, NO_GO (NaN) only when required,
  * a p95 latency benchmark against the default budget.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Iterator

import numpy as np
import pytest

from coherence_bridge import geosync_adapter as ga
from coherence_bridge.geosync_adapter import (
    OllivierResult,
    OllivierStatus,
    _ollivier_worst_edge_kappa,
    ollivier_required,
    reset_ollivier_runtime_state,
)

_ENV_KEYS = (
    "COHERENCE_OLLIVIER_MAX_EDGES",
    "COHERENCE_OLLIVIER_MAX_MS",
    "COHERENCE_REQUIRE_OLLIVIER",
    "COHERENCE_OLLIVIER_MAX_CONSECUTIVE_TIMEOUTS",
    "COHERENCE_OLLIVIER_COOLDOWN_MS",
)


@pytest.fixture(autouse=True)
def _clean_env_and_state() -> Iterator[None]:
    saved = {k: os.environ.get(k) for k in _ENV_KEYS}
    for k in _ENV_KEYS:
        os.environ.pop(k, None)
    reset_ollivier_runtime_state()
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        reset_ollivier_runtime_state()


def _prices(seed: int = 7, n: int = 200) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return 1.10 * np.exp(np.cumsum(rng.standard_normal(n) * 1e-3))


def test_status_ok_on_normal_prices() -> None:
    r = _ollivier_worst_edge_kappa(_prices())
    assert r.status is OllivierStatus.OK
    assert np.isfinite(r.value)
    assert r.value <= 1.0 + 1e-9  # INV-RC1 upper bound
    assert r.edges_seen > 0
    assert r.elapsed_ms >= 0.0


def test_perf_budget_exceeded_is_typed_nan() -> None:
    os.environ["COHERENCE_OLLIVIER_MAX_EDGES"] = "1"
    r = _ollivier_worst_edge_kappa(_prices())
    assert r.status is OllivierStatus.PERF_BUDGET_EXCEEDED
    assert not np.isfinite(r.value)


def test_cache_returns_identical_value_and_marks_hit() -> None:
    p = _prices()
    first = _ollivier_worst_edge_kappa(p)
    assert first.cache_hit is False
    second = _ollivier_worst_edge_kappa(p)
    assert second.cache_hit is True
    assert (first.value, first.status) == (second.value, second.status)


def test_cache_honours_budget_change_not_stale() -> None:
    p = _prices()
    assert _ollivier_worst_edge_kappa(p).status is OllivierStatus.OK
    os.environ["COHERENCE_OLLIVIER_MAX_EDGES"] = "1"  # tighten budget
    assert _ollivier_worst_edge_kappa(p).status is OllivierStatus.PERF_BUDGET_EXCEEDED


def test_required_flag_parsing() -> None:
    assert ollivier_required() is False
    os.environ["COHERENCE_REQUIRE_OLLIVIER"] = "1"
    assert ollivier_required() is True
    os.environ["COHERENCE_REQUIRE_OLLIVIER"] = "true"
    assert ollivier_required() is True
    os.environ["COHERENCE_REQUIRE_OLLIVIER"] = "0"
    assert ollivier_required() is False


# --- Task 3: pre-emptive deadline + circuit breaker --------------------------


def test_deadline_preempts_solve_not_post_hoc() -> None:
    """A zero-ms budget pre-empts BEFORE doing the full solve (edges_seen small)."""
    os.environ["COHERENCE_OLLIVIER_MAX_MS"] = "0"
    r = _ollivier_worst_edge_kappa(_prices())
    assert r.status is OllivierStatus.TIMEOUT
    assert not np.isfinite(r.value)
    # Pre-empted at/near the first edge — NOT after solving the whole graph.
    assert r.edges_seen <= 1


def test_circuit_breaker_opens_after_consecutive_timeouts() -> None:
    os.environ["COHERENCE_OLLIVIER_MAX_MS"] = "0"  # every solve times out
    os.environ["COHERENCE_OLLIVIER_MAX_CONSECUTIVE_TIMEOUTS"] = "3"
    os.environ["COHERENCE_OLLIVIER_COOLDOWN_MS"] = "60000"
    # 3 distinct price arrays (cache misses) ⇒ 3 fresh timeouts on one instrument.
    for seed in (1, 2, 3):
        r = _ollivier_worst_edge_kappa(_prices(seed=seed), instrument="EURUSD")
        assert r.status is OllivierStatus.TIMEOUT
    # 4th call is short-circuited WITHOUT computing.
    r4 = _ollivier_worst_edge_kappa(_prices(seed=99), instrument="EURUSD")
    assert r4.status is OllivierStatus.CIRCUIT_OPEN
    assert r4.circuit_state == "open"
    # A different instrument is unaffected (per-instrument breaker).
    os.environ["COHERENCE_OLLIVIER_MAX_MS"] = "750"
    assert _ollivier_worst_edge_kappa(_prices(seed=5), instrument="GBPUSD").status is (
        OllivierStatus.OK
    )


def test_circuit_resets_on_success() -> None:
    os.environ["COHERENCE_OLLIVIER_MAX_MS"] = "0"
    os.environ["COHERENCE_OLLIVIER_MAX_CONSECUTIVE_TIMEOUTS"] = "3"
    for seed in (1, 2):  # two timeouts (below threshold)
        assert _ollivier_worst_edge_kappa(_prices(seed=seed), instrument="USDJPY").status is (
            OllivierStatus.TIMEOUT
        )
    os.environ["COHERENCE_OLLIVIER_MAX_MS"] = "750"  # a success resets the counter
    assert _ollivier_worst_edge_kappa(_prices(seed=3), instrument="USDJPY").status is (
        OllivierStatus.OK
    )


# --- Task 4: thread-safe bounded-LRU cache -----------------------------------


def test_cache_is_bounded_lru() -> None:
    """More distinct inputs than the cap ⇒ cache stays bounded (LRU eviction)."""
    for seed in range(ga._OLLIVIER_CACHE_MAX + 25):
        _ollivier_worst_edge_kappa(_prices(seed=seed))
    assert len(ga._OLLIVIER_CACHE) <= ga._OLLIVIER_CACHE_MAX


def test_concurrent_calls_are_thread_safe_and_consistent() -> None:
    """32 threads × same input ⇒ identical verdicts, no exceptions, bounded cache."""
    p = _prices(seed=11)
    results: list[OllivierResult] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            for _ in range(50):
                r = _ollivier_worst_edge_kappa(p, instrument="EURUSD")
                with lock:
                    results.append(r)
        except BaseException as exc:  # surface any thread fault into the test
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(32)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    statuses = {r.status for r in results}
    values = {round(r.value, 9) for r in results}
    assert statuses == {OllivierStatus.OK}
    assert len(values) == 1  # deterministic across all threads
    assert len(ga._OLLIVIER_CACHE) <= ga._OLLIVIER_CACHE_MAX


def test_benchmark_p95_within_default_budget() -> None:
    """p95 single-graph compute latency stays within the default budget."""
    samples_ms: list[float] = []
    for seed in range(12):
        reset_ollivier_runtime_state()
        t0 = time.perf_counter()
        r = _ollivier_worst_edge_kappa(_prices(seed=seed))
        samples_ms.append((time.perf_counter() - t0) * 1000.0)
        assert r.status is OllivierStatus.OK
    samples_ms.sort()
    p95 = samples_ms[int(0.95 * (len(samples_ms) - 1))]
    assert p95 <= ga._OLLIVIER_MAX_MS_DEFAULT, f"p95={p95:.1f}ms over budget"


# --- adapter-level degraded behaviour (ABSTAIN vs NO_GO) ----------------------


def _adapter_signal_under_env() -> dict[str, object]:
    import pandas as pd

    from coherence_bridge.geosync_adapter import GeoSyncAdapter

    rng = np.random.default_rng(7)
    n = 200
    close = 1.10 * np.exp(np.cumsum(rng.standard_normal(n) * 1e-3))
    df = pd.DataFrame(
        {
            "open": np.concatenate([[close[0]], close[:-1]]),
            "high": close * 1.0005,
            "low": close * 0.9995,
            "close": close,
            "volume": rng.integers(100, 1000, n).astype(float),
        },
        index=pd.date_range("2024-01-01", periods=n, freq="min"),
    )
    adapter = GeoSyncAdapter()
    inst = adapter.instruments[0]
    adapter.update_market_data(inst, df)
    sig = adapter.get_signal(inst)
    assert sig is not None
    return sig


@pytest.mark.integration
def test_adapter_degraded_non_required_abstains() -> None:
    """Degraded κ + not-required ⇒ ollivier_kappa OMITTED (ABSTAIN), status set."""
    os.environ["COHERENCE_OLLIVIER_MAX_EDGES"] = "1"  # force degraded
    sig = _adapter_signal_under_env()
    assert sig["ollivier_status"] == OllivierStatus.PERF_BUDGET_EXCEEDED.value
    assert "ollivier_kappa" not in sig  # ABSTAIN, not a fabricated value
    assert "ollivier_circuit_state" in sig  # telemetry present


@pytest.mark.integration
def test_adapter_degraded_required_refuses() -> None:
    """Degraded κ + required ⇒ ollivier_kappa = NaN (downstream contract NO_GO)."""
    os.environ["COHERENCE_OLLIVIER_MAX_EDGES"] = "1"
    os.environ["COHERENCE_REQUIRE_OLLIVIER"] = "1"
    sig = _adapter_signal_under_env()
    assert sig["ollivier_status"] == OllivierStatus.PERF_BUDGET_EXCEEDED.value
    assert "ollivier_kappa" in sig
    kappa = sig["ollivier_kappa"]
    assert isinstance(kappa, float)
    assert not np.isfinite(kappa)
