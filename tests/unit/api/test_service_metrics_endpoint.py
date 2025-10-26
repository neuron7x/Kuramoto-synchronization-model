from fastapi.testclient import TestClient


def test_metrics_endpoint_exposes_prometheus_payload(monkeypatch):
    monkeypatch.setenv("TRADEPULSE_AUDIT_SECRET", "0123456789abcdef")
    monkeypatch.setenv(
        "TRADEPULSE_RBAC_AUDIT_SECRET",
        "fedcba9876543210fedcba9876543210",
    )

    from application.api.service import create_app

    app = create_app()
    client = TestClient(app)

    health_response = client.get("/health")
    assert health_response.status_code == 200

    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200
    body = metrics_response.text

    assert "tradepulse_health_check_status" in body
    assert "process_cpu_seconds_total" in body
    assert metrics_response.headers["content-type"].startswith("text/plain")
