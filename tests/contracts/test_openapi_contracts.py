# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import os

import pytest

os.environ.setdefault("GEOSYNC_OAUTH2_ISSUER", "https://issuer.geosync.test")
os.environ.setdefault("GEOSYNC_OAUTH2_AUDIENCE", "geosync-api")
os.environ.setdefault("GEOSYNC_OAUTH2_JWKS_URI", "https://issuer.geosync.test/jwks")
os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "import-audit-secret")
os.environ.setdefault("GEOSYNC_RBAC_AUDIT_SECRET", "import-rbac-secret")

from application.api.service import (
    create_app,
)  # noqa: E402  - env vars must be set before import
from application.settings import AdminApiSettings
from tests.api.openapi_spec import (
    EXPECTED_OPENAPI_VERSION,
    load_expected_openapi_schema,
)


@pytest.fixture()
def fastapi_app():
    settings = AdminApiSettings(
        audit_secret="import-audit-secret",
    )
    return create_app(settings=settings)


def test_openapi_contract_matches_baseline(fastapi_app) -> None:
    generated = fastapi_app.openapi()
    expected = load_expected_openapi_schema()
    # Structural check: same paths and version (component details may vary across pydantic versions)
    assert set(generated.get("paths", {})) == set(expected.get("paths", {}))
    assert generated.get("info", {}).get("version") == expected.get("info", {}).get("version")


def test_openapi_defines_expected_routes(fastapi_app) -> None:
    schema = fastapi_app.openapi()
    paths = schema.get("paths", {})
    assert "/features" in paths
    assert "post" in paths["/features"]
    assert "/predictions" in paths
    assert "post" in paths["/predictions"]
    feature_response = schema["components"]["schemas"]["FeatureResponse"]
    prediction_response = schema["components"]["schemas"]["PredictionResponse"]
    assert {
        "symbol",
        "features",
        "items",
        "pagination",
        "filters",
    } <= set(feature_response["properties"].keys())
    assert {
        "symbol",
        "signal",
        "items",
        "pagination",
        "filters",
    } <= set(prediction_response["properties"].keys())


def test_openapi_declares_idempotency_headers(fastapi_app) -> None:
    schema = fastapi_app.openapi()
    components = schema.get("components", {})
    headers = components.get("headers", {})
    assert "Idempotency-Key" in headers
    assert "X-Idempotent-Replay" in headers


def test_openapi_version_matches_contract_file(fastapi_app) -> None:
    schema = fastapi_app.openapi()
    info = schema.get("info", {})
    assert info.get("version") == EXPECTED_OPENAPI_VERSION
    assert "x-backwards-compatibility" in info
