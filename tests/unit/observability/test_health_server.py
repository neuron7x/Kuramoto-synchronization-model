# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import httpx

from observability.health import HealthServer


def test_health_endpoints_expose_liveness_and_readiness() -> None:
    with HealthServer(host="127.0.0.1", port=0) as server:
        port = server.port
        base_url = f"http://127.0.0.1:{port}"

        response = httpx.get(f"{base_url}/healthz", timeout=2.0)
        assert response.status_code == 200
        payload = response.json()
        assert payload["live"] is True
        assert payload["status"] == "ok"

        live_response = httpx.get(f"{base_url}/health/live", timeout=2.0)
        assert live_response.status_code == 200
        live_payload = live_response.json()
        assert live_payload["status"] == "live"

        ready_response = httpx.get(f"{base_url}/readyz", timeout=2.0)
        assert ready_response.status_code == 503

        server.update_component("postgres", healthy=True)
        server.set_ready(True)

        ready_response = httpx.get(f"{base_url}/readyz", timeout=2.0)
        assert ready_response.status_code == 200
        ready_payload = ready_response.json()
        assert ready_payload["components"]["postgres"]["healthy"] is True
        assert ready_payload["status"] == "ready"

        server.set_live(False)
        response = httpx.get(f"{base_url}/healthz", timeout=2.0)
        assert response.status_code == 503
        assert response.json()["status"] == "down"

        live_response = httpx.get(f"{base_url}/health/live", timeout=2.0)
        assert live_response.status_code == 503
        assert live_response.json()["status"] == "down"
