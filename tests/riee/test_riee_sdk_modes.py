from __future__ import annotations

from pathlib import Path

import pytest

from runtime.riee.engine import KernelPanic
from runtime.riee.sdk import riee_guard
from scripts.riee.operational_modes import supported_modes


def test_supported_modes_declared() -> None:
    modes = {m.name for m in supported_modes()}
    assert modes == {"cloud_native", "local_edge", "application_sdk"}


def test_sdk_passthrough_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RIEE_ENABLE", "0")

    @riee_guard()
    def f() -> float:
        return 1.1

    assert f() == 1.1


def test_sdk_panics_when_enabled_and_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("RIEE_ENABLE", "1")
    claims = tmp_path / "CLAIMS.md"
    claims.write_text("GAMMA-CLAIM: 1.0\n", encoding="utf-8")

    @riee_guard(claims_path=str(claims))
    def f() -> float:
        return 1.1

    try:
        f()
    except KernelPanic:
        pass
    else:
        raise AssertionError("KernelPanic expected when RIEE enabled")
