import os

import pytest

os.environ.setdefault("TRADEPULSE_AUDIT_SECRET", "contract-test-secret")
os.environ.setdefault("TRADEPULSE_OAUTH2_ISSUER", "https://openapi.test")
os.environ.setdefault("TRADEPULSE_OAUTH2_AUDIENCE", "tradepulse-api")
os.environ.setdefault("TRADEPULSE_OAUTH2_JWKS_URI", "https://openapi.test/jwks")
os.environ.setdefault("TRADEPULSE_RBAC_AUDIT_SECRET", "contract-rbac-secret")

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
    assert runtime_schema == load_expected_openapi_schema()


@pytest.mark.usefixtures("security_context")
def test_openapi_declares_expected_version() -> None:
    app = create_app()
    schema = app.openapi()
    assert schema.get("info", {}).get("version") == EXPECTED_OPENAPI_VERSION
