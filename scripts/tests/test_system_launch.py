import os
from pathlib import Path

import pytest

os.environ.setdefault("TRADEPULSE_ADMIN__TWO_FACTOR_SECRET", "test-secret")
os.environ.setdefault("TWO_FACTOR_SECRET", "test-secret")
os.environ.setdefault("AUDIT_SECRET", "test-audit-secret")

from scripts.commands import system
from scripts.commands.base import CommandError


def test_validate_environment_reads_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / "compose.env"
    env_file.write_text(
        "\n".join(
            (
                "TRADEPULSE_AUDIT_SECRET=audit",
                "TRADEPULSE_RBAC_AUDIT_SECRET=rbac",
                "EXTRA_FLAG=true",
            )
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("OS_LEVEL", "available")

    variables = system.validate_environment(env_file, system.REQUIRED_ENV_VARS)

    assert variables["TRADEPULSE_AUDIT_SECRET"] == "audit"
    assert variables["TRADEPULSE_RBAC_AUDIT_SECRET"] == "rbac"
    assert variables["OS_LEVEL"] == "available"


def test_validate_environment_raises_for_missing_required(tmp_path: Path) -> None:
    env_file = tmp_path / "compose.env"
    env_file.write_text("TRADEPULSE_AUDIT_SECRET=only-one\n", encoding="utf-8")

    with pytest.raises(CommandError):
        system.validate_environment(env_file, system.REQUIRED_ENV_VARS)


def test_wait_for_healthy_services_eventually_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status_sequence = [
        [system.ServiceStatus(name="tradepulse", state="running", health="starting")],
        [
            system.ServiceStatus(name="tradepulse", state="running", health="healthy"),
            system.ServiceStatus(name="prometheus", state="running", health=None),
        ],
    ]

    def fake_fetch(_: Path, __: object) -> list[system.ServiceStatus]:
        return status_sequence.pop(0)

    monkeypatch.setattr(system, "compose_services_status", fake_fetch)
    monkeypatch.setattr(system.time, "sleep", lambda _: None)

    statuses = system.wait_for_healthy_services(
        Path("docker-compose.yml"),
        profiles=None,
        required_services=None,
        timeout=1.0,
        interval=0.0,
        status_fetcher=fake_fetch,
    )

    assert [status.name for status in statuses] == ["tradepulse", "prometheus"]


def test_wait_for_healthy_services_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(_: Path, __: object) -> list[system.ServiceStatus]:
        return [
            system.ServiceStatus(name="tradepulse", state="running", health="starting")
        ]

    monkeypatch.setattr(system.time, "sleep", lambda _: None)

    with pytest.raises(CommandError) as excinfo:
        system.wait_for_healthy_services(
            Path("docker-compose.yml"),
            profiles=None,
            required_services=None,
            timeout=0.05,
            interval=0.0,
            status_fetcher=fake_fetch,
        )

    assert "tradepulse=starting" in str(excinfo.value)


def test_wait_for_healthy_services_detects_missing_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_fetch(_: Path, __: object) -> list[system.ServiceStatus]:
        return [system.ServiceStatus(name="prometheus", state="running", health=None)]

    monkeypatch.setattr(system.time, "sleep", lambda _: None)

    with pytest.raises(CommandError) as excinfo:
        system.wait_for_healthy_services(
            Path("docker-compose.yml"),
            profiles=None,
            required_services=("tradepulse",),
            timeout=0.05,
            interval=0.0,
            status_fetcher=fake_fetch,
        )

    assert "tradepulse" in str(excinfo.value)
