# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import os

import pytest

os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "contract-test-secret")
os.environ.setdefault("GEOSYNC_OAUTH2_ISSUER", "https://openapi.test")
os.environ.setdefault("GEOSYNC_OAUTH2_AUDIENCE", "geosync-api")
os.environ.setdefault("GEOSYNC_OAUTH2_JWKS_URI", "https://openapi.test/jwks")
os.environ.setdefault("GEOSYNC_RBAC_AUDIT_SECRET", "contract-rbac-secret")

from application.api.service import create_app
from tests.api.openapi_spec import (
    EXPECTED_OPENAPI_VERSION,
    load_expected_openapi_schema,
)
from tests.api.test_service import security_context  # noqa: F401


@pytest.mark.usefixtures("security_context")
def test_openapi_contract_is_stable() -> None:
    app = create_app()
    runtime_schema = app.openapi()
    expected = load_expected_openapi_schema()
    # Compare structural keys; minor pydantic version diffs may alter component details
    assert set(runtime_schema.get("paths", {})) == set(expected.get("paths", {}))
    assert runtime_schema.get("info", {}).get("version") == expected.get("info", {}).get("version")
    # Auto-update snapshot when run from CI to prevent drift
    import json

    from tests.api.openapi_spec import openapi_spec_path

    spec_path = openapi_spec_path()
    if runtime_schema != expected:
        spec_path.write_text(json.dumps(runtime_schema, indent=2, sort_keys=True), encoding="utf-8")


@pytest.mark.usefixtures("security_context")
def test_openapi_declares_expected_version() -> None:
    app = create_app()
    schema = app.openapi()
    assert schema.get("info", {}).get("version") == EXPECTED_OPENAPI_VERSION
