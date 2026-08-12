# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Server-compute latency budget gate (IERD-Q6 Phase-4 ENTRY).

IERD-PAI-FPS-UX-001 §5 + ADR 0020 require the server-compute layer of
the four-layer latency budget to be measurable and gated:

    server_compute  p95 < 100 ms simple
    interactive     p95 < 200 ms

This test runs in-process against the FastAPI app produced by
`application.api.service.create_app()` via Starlette's TestClient. It
warms the route table (FastAPI lazily compiles route matchers on first
request), then collects N samples per endpoint and asserts the empirical
p95 against the budget.

The gate exercises only the **server_compute** layer of the four-layer
budget (client_render, network_TTFB, db_io are remote-driven and tracked
under the same claim). Phase-4 EXIT lands the remaining three layers
plus a Grafana dashboard binding.

Tracks claim `e2e-latency-budget-compliance` in `docs/CLAIMS.yaml`.
"""

from __future__ import annotations

import importlib
import os
import statistics
from collections.abc import Iterator
from time import perf_counter
from typing import TYPE_CHECKING, Final

import pytest
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from fastapi import FastAPI

# Env-var injection deferred to a module-scoped fixture (see
# ``_isolated_env`` below) so this module no longer mutates ``os.environ``
# at import time. Previously the unconditional
# ``os.environ["GEOSYNC_DISABLE_METRICS"] = "1"`` left state behind for
# downstream tests in the same pytest session, in violation of the
# IERD test-isolation discipline this very module's claim asserts.

# Sample count and warmup count are independent of the budget — they
# control statistical resolution of the p95 estimator. With N=200 and a
# unimodal latency distribution, a single outlier moves the empirical
# p95 by at most ~5 ms; that is the resolution we need to defend against
# regression while staying inside a 60-second CI wall-clock.
N_SAMPLES: Final[int] = int(os.environ.get("GEOSYNC_LATENCY_SAMPLES", "200"))
N_WARMUP: Final[int] = int(os.environ.get("GEOSYNC_LATENCY_WARMUP", "20"))

# Layer budgets per IERD §5. Override via env for shadow runs.
SIMPLE_P95_MS: Final[float] = float(os.environ.get("GEOSYNC_BUDGET_SIMPLE_P95_MS", "100.0"))
INTERACTIVE_P95_MS: Final[float] = float(
    os.environ.get("GEOSYNC_BUDGET_INTERACTIVE_P95_MS", "200.0")
)


_REQUIRED_ENV: Final[dict[str, str]] = {
    "GEOSYNC_AUDIT_SECRET": "latency-budget-test-secret",  # pragma: allowlist secret
    "GEOSYNC_OAUTH2_ISSUER": "https://latency.test",
    "GEOSYNC_OAUTH2_AUDIENCE": "geosync-api",
    "GEOSYNC_OAUTH2_JWKS_URI": "https://latency.test/jwks",
    "GEOSYNC_RBAC_AUDIT_SECRET": "latency-budget-rbac-secret",  # pragma: allowlist secret
    # Isolated CollectorRegistry — the ~440 GET requests this suite
    # fires must not pollute the global Prometheus REGISTRY read by
    # ``tests/observability/test_metrics_expectations.py``.
    "GEOSYNC_DISABLE_METRICS": "1",
}


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    """Build the canonical app inside an isolated env-var window.

    The previous implementation set ``os.environ`` at module import
    time, leaving every required key in place for the rest of the
    pytest session. This fixture takes a snapshot, applies overrides,
    builds the app, yields the TestClient, and restores the snapshot
    on teardown — the env mutation is bounded to the lifetime of this
    module's test cases.
    """
    saved: dict[str, str | None] = {key: os.environ.get(key) for key in _REQUIRED_ENV}
    os.environ.update(_REQUIRED_ENV)
    try:
        # Late import so settings (Pydantic, env-driven) resolve under
        # the overrides above, not under whatever leaked from upstream.
        service_module = importlib.import_module("application.api.service")
        app: "FastAPI" = service_module.create_app()
        yield TestClient(app)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _measure_p95_ms(client: TestClient, path: str) -> tuple[float, float, float]:
    """Issue N_WARMUP + N_SAMPLES requests; return (p50, p95, p99) in milliseconds.

    A 200-status assertion guards against silent fall-through to error paths
    that would skew the timing distribution downward.
    """
    for _ in range(N_WARMUP):
        r = client.get(path)
        assert r.status_code == 200, f"warmup non-200 on {path}: {r.status_code}"

    samples_ms: list[float] = []
    for _ in range(N_SAMPLES):
        t0 = perf_counter()
        r = client.get(path)
        elapsed_ms = (perf_counter() - t0) * 1000.0
        assert r.status_code == 200, f"non-200 on {path}: {r.status_code}"
        samples_ms.append(elapsed_ms)

    samples_ms.sort()
    p50 = float(statistics.median(samples_ms))
    # statistics.quantiles with n=100 + index 94 → 95th percentile by linear interpolation.
    p95 = float(statistics.quantiles(samples_ms, n=100, method="inclusive")[94])
    p99 = float(statistics.quantiles(samples_ms, n=100, method="inclusive")[98])
    return p50, p95, p99


@pytest.mark.parametrize(
    ("path", "budget_ms", "tier_label"),
    [
        ("/health", INTERACTIVE_P95_MS, "interactive"),
        ("/metrics", SIMPLE_P95_MS, "simple"),
    ],
)
def test_endpoint_p95_within_budget(
    client: TestClient,
    path: str,
    budget_ms: float,
    tier_label: str,
) -> None:
    """p95(server_compute) on `path` is below the IERD §5 budget for `tier_label`."""
    p50, p95, p99 = _measure_p95_ms(client, path)
    print(  # surfaced via pytest -s / Step Summary
        f"\n[latency] {path:24s} tier={tier_label:11s} "
        f"p50={p50:6.2f}ms p95={p95:6.2f}ms p99={p99:6.2f}ms "
        f"budget={budget_ms:.0f}ms n={N_SAMPLES}"
    )
    assert p95 < budget_ms, (
        f"IERD-Q6 §5 budget violated on {path} ({tier_label} tier): "
        f"observed p95={p95:.2f}ms exceeds {budget_ms:.0f}ms (n={N_SAMPLES}, "
        f"p50={p50:.2f}ms, p99={p99:.2f}ms). Either the server_compute layer "
        f"regressed or the route became dependency-heavy; check Prometheus "
        f"http_request_duration_seconds histogram for the same endpoint."
    )
