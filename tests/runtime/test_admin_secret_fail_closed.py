# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed guard for admin secrets in initialize_control_platform.

Regression for the CRITICAL: the production server path (server.run ->
initialize_control_platform) used to `os.environ.setdefault` the *public* pyotp
example TOTP seed `JBSWY3DPEHPK3PXP` unconditionally, so an operator who forgot
to configure GEOSYNC_TWO_FACTOR_SECRET got a forgeable admin second factor in
production. The guard must inject dev defaults ONLY in dev/test profiles and
fail closed otherwise.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Iterator
from typing import Any

import pytest

_PUBLIC_TOTP_SEED = "JBSWY3DPEHPK3PXP"  # pragma: allowlist secret  # public pyotp example seed
_SECRET_ENV = (
    "GEOSYNC_TWO_FACTOR_SECRET",
    "GEOSYNC_AUDIT_SECRET",
    "ADMIN_API_SETTINGS__two_factor_secret",
)


@pytest.fixture()
def clean_secret_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove every admin-secret and profile env var for a hermetic check."""
    for name in (*_SECRET_ENV, "GEOSYNC_PROFILE", "APP_ENV"):
        monkeypatch.delenv(name, raising=False)
    yield


def _init_module() -> Any:
    return importlib.import_module("application.runtime.init_control_platform")


@pytest.mark.parametrize("profile", ["prod", "production", "staging"])
def test_production_profile_fails_closed_without_secret(
    profile: str, clean_secret_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEOSYNC_PROFILE", profile)
    module = _init_module()

    with pytest.raises(RuntimeError, match="non-development profiles"):
        module.initialize_control_platform()

    # The public seed must NEVER be injected on a production profile.
    for name in _SECRET_ENV:
        assert os.environ.get(name) != _PUBLIC_TOTP_SEED, name
    assert "GEOSYNC_TWO_FACTOR_SECRET" not in os.environ


def test_unset_profile_is_production_safe_and_fails_closed(
    clean_secret_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An UNSET profile must behave like production: no public seed injected, and
    # fail closed when no real secret is configured. (Default deployments never
    # set a profile — defaulting to "dev" silently injected the public seed.)
    monkeypatch.delenv("GEOSYNC_PROFILE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    module = _init_module()

    with pytest.raises(RuntimeError, match="non-development profiles"):
        module.initialize_control_platform()

    for name in _SECRET_ENV:
        assert os.environ.get(name) != _PUBLIC_TOTP_SEED, name
    assert "GEOSYNC_TWO_FACTOR_SECRET" not in os.environ


def test_production_profile_with_real_secret_does_not_raise_on_guard(
    clean_secret_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A real operator-supplied secret must pass the guard (the public seed is
    # explicitly excluded by being operator-chosen, not the default fallback).
    monkeypatch.setenv("GEOSYNC_PROFILE", "production")
    real_secret = "ORSXG5BNMRSWG4TFOQ======"  # pragma: allowlist secret  # base32 test value
    monkeypatch.setenv("GEOSYNC_TWO_FACTOR_SECRET", real_secret)
    monkeypatch.setenv(
        "GEOSYNC_AUDIT_SECRET",
        "an-operator-audit-secret",  # pragma: allowlist secret  # test value
    )
    module = _init_module()

    # The guard itself must not raise; downstream init may fail for unrelated
    # reasons (config/controllers), so we only assert the guard does not inject
    # the public seed and does not raise the secret RuntimeError.
    try:
        module.initialize_control_platform()
    except RuntimeError as exc:  # pragma: no cover - defensive
        assert "non-development profiles" not in str(exc)
    except Exception:
        # Unrelated init failures (config/controllers) are irrelevant here; this
        # test only asserts the secret-guard behaviour checked below.
        pass

    assert os.environ["GEOSYNC_TWO_FACTOR_SECRET"] == real_secret


@pytest.mark.parametrize("profile", ["dev", "test", "ci", "local", "development"])
def test_dev_profiles_get_benign_defaults(
    profile: str, clean_secret_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEOSYNC_PROFILE", profile)
    module = _init_module()

    # The guard branch runs without raising and seeds the dev defaults. We invoke
    # only the guard logic by catching any later init error.
    try:
        module.initialize_control_platform()
    except RuntimeError as exc:  # pragma: no cover - defensive
        assert "non-development profiles" not in str(exc)
    except Exception:
        # Unrelated init failures (config/controllers) are irrelevant here; this
        # test only asserts the dev-default seeding checked below.
        pass

    assert os.environ.get("GEOSYNC_TWO_FACTOR_SECRET") == _PUBLIC_TOTP_SEED
