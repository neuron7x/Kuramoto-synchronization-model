# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import os
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from typing import Sequence

os.environ.setdefault("GEOSYNC_TWO_FACTOR_SECRET", "JBSWY3DPEHPK3PXP")
os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "audit-secret-placeholder-1234")

import pytest

from scripts.commands import bootstrap


def _create_fake_venv(venv_path: Path) -> None:
    python_path = bootstrap._venv_python_path(venv_path)
    python_path.parent.mkdir(parents=True, exist_ok=True)
    python_path.write_text("", encoding="utf-8")
    (venv_path / "pyvenv.cfg").write_text("home = python\n", encoding="utf-8")


def test_execute_installs_requested_tooling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    venv_path = tmp_path / ".venv"
    requirements = tmp_path / "requirements.lock"
    requirements.write_text("numpy==1.26.0\n", encoding="utf-8")
    dev_requirements = tmp_path / "requirements-dev.lock"
    dev_requirements.write_text("pre-commit==3.6.0\n", encoding="utf-8")

    frontend_path = tmp_path / "dashboard"
    frontend_path.mkdir()
    (frontend_path / "package.json").write_text("{\n}\n", encoding="utf-8")
    (frontend_path / "package-lock.json").write_text("{\n}\n", encoding="utf-8")

    executed: list[tuple[tuple[str, ...], Path | None]] = []

    def fake_run(
        command: Sequence[str], *, cwd: Path | None = None, **_: object
    ) -> SimpleNamespace:
        executed.append((tuple(command), cwd))
        if "venv" in command:
            _create_fake_venv(venv_path)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(bootstrap, "run_subprocess", fake_run)
    monkeypatch.setattr(
        bootstrap.shutil,
        "which",
        lambda tool: f"/usr/bin/{tool}" if tool == "npm" else None,
    )

    config = bootstrap.BootstrapConfig(
        python=Path(sys.executable),
        venv_path=venv_path,
        recreate_venv=False,
        upgrade_pip=True,
        install_python_dependencies=True,
        include_dev_dependencies=True,
        requirements=(requirements,),
        dev_requirements=(dev_requirements,),
        extras=("connectors", "gpu"),
        install_pre_commit=True,
        install_frontend=True,
        reinstall_frontend=True,
        frontend_path=frontend_path,
        run_readiness_checks=False,
        run_smoke_test=False,
    )

    bootstrap.execute(config)

    venv_python = bootstrap._venv_python_path(venv_path)
    expected_commands = [
        (str(Path(sys.executable)), "-m", "venv", str(venv_path)),
        (
            str(venv_python),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
            "setuptools",
            "wheel",
        ),
        (str(venv_python), "-m", "pip", "install", "-r", str(requirements)),
        (str(venv_python), "-m", "pip", "install", "-r", str(dev_requirements)),
        (str(venv_python), "-m", "pip", "install", ".[connectors,gpu]"),
        (str(venv_python), "-m", "pre_commit", "install", "--install-hooks"),
        (str(venv_python), "-m", "pre_commit", "install", "--hook-type", "commit-msg"),
    ]

    recorded_commands = [entry[0] for entry in executed[:-1]]
    assert recorded_commands == [tuple(cmd) for cmd in expected_commands]

    final_command, cwd = executed[-1]
    assert final_command == ("npm", "ci")
    assert cwd == frontend_path


def test_build_config_validates_missing_requirements(tmp_path: Path) -> None:
    args = Namespace(
        python=Path(sys.executable),
        venv_path=tmp_path / ".venv",
        recreate_venv=False,
        upgrade_pip=True,
        skip_python_deps=False,
        include_dev=False,
        requirements=[tmp_path / "missing.lock"],
        dev_requirements=None,
        extras=(),
        install_pre_commit=False,
        install_frontend=False,
        reinstall_frontend=False,
        frontend_path=tmp_path,
        run_readiness_checks=False,
        run_smoke_test=False,
    )

    with pytest.raises(bootstrap.CommandError):
        bootstrap._build_config(args)


def test_build_config_appends_default_requirements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    default_requirements = tmp_path / "requirements.lock"
    default_requirements.write_text("base==1.0\n", encoding="utf-8")
    extra_requirements = tmp_path / "local.lock"
    extra_requirements.write_text("extra==1.0\n", encoding="utf-8")

    monkeypatch.setattr(bootstrap, "DEFAULT_REQUIREMENTS", (default_requirements,))

    args = Namespace(
        python=Path(sys.executable),
        venv_path=tmp_path / ".venv",
        recreate_venv=False,
        upgrade_pip=True,
        skip_python_deps=False,
        include_dev=False,
        requirements=[extra_requirements],
        dev_requirements=None,
        extras=(),
        install_pre_commit=False,
        install_frontend=False,
        reinstall_frontend=False,
        frontend_path=tmp_path,
        run_readiness_checks=False,
        run_smoke_test=False,
    )

    config = bootstrap._build_config(args)

    assert config.requirements == (
        default_requirements.resolve(),
        extra_requirements.resolve(),
    )


def test_execute_skips_virtualenv_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    venv_path = tmp_path / ".venv"
    _create_fake_venv(venv_path)

    calls: list[Sequence[str]] = []

    def fake_run(command: Sequence[str], **_: object) -> SimpleNamespace:
        calls.append(tuple(command))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(bootstrap, "run_subprocess", fake_run)

    config = bootstrap.BootstrapConfig(
        python=Path(sys.executable),
        venv_path=venv_path,
        recreate_venv=False,
        upgrade_pip=True,
        install_python_dependencies=False,
        include_dev_dependencies=False,
        requirements=(),
        dev_requirements=(),
        extras=(),
        install_pre_commit=False,
        install_frontend=False,
        reinstall_frontend=False,
        frontend_path=tmp_path,
        run_readiness_checks=False,
        run_smoke_test=False,
    )

    bootstrap.execute(config)

    assert all("venv" not in command for command in calls)


def test_execute_runs_readiness_and_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    venv_path = tmp_path / ".venv"
    sample = tmp_path / "sample.csv"
    sample.write_text("timestamp,close\n2024-01-01,1\n", encoding="utf-8")

    _create_fake_venv(venv_path)

    executed: list[tuple[tuple[str, ...], Path | None]] = []

    def fake_run(
        command: Sequence[str], *, cwd: Path | None = None, **_: object
    ) -> SimpleNamespace:
        executed.append((tuple(command), cwd))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(bootstrap, "run_subprocess", fake_run)
    monkeypatch.chdir(tmp_path)

    venv_python = bootstrap._venv_python_path(venv_path)

    config = bootstrap.BootstrapConfig(
        python=Path(sys.executable),
        venv_path=venv_path,
        recreate_venv=False,
        upgrade_pip=False,
        install_python_dependencies=False,
        include_dev_dependencies=False,
        requirements=(),
        dev_requirements=(),
        extras=(),
        install_pre_commit=False,
        install_frontend=False,
        reinstall_frontend=False,
        frontend_path=tmp_path,
        run_readiness_checks=True,
        run_smoke_test=True,
    )

    bootstrap.execute(config)

    commands_only = [entry[0] for entry in executed]
    assert (str(venv_python), "-m", "pip", "check") in commands_only
    assert any("interfaces.cli" in cmd for cmd in commands_only)
