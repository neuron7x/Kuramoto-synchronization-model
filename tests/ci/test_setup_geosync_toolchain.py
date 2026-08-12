# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Shared CI bootstrap toolchain must respect dependency security floors."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACTION = ROOT / ".github" / "actions" / "setup-geosync" / "action.yml"
CONSTRAINTS = ROOT / "constraints" / "security.txt"
REQ_DEV = ROOT / "requirements-dev.txt"
_VERSION = r"([0-9][0-9A-Za-z.+\-_!]*)"


def _version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", text)[:4])


def _action_text() -> str:
    return ACTION.read_text(encoding="utf-8")


def _action_exact_pin(name: str) -> str:
    text = _action_text()
    matches = re.findall(rf"\b{name}=={_VERSION}", text)
    assert matches, f"{ACTION}: missing exact bootstrap pin for {name}"
    assert len(set(matches)) == 1, f"{ACTION}: inconsistent {name} pins: {matches}"
    return matches[0]


def _constraint_floor(name: str) -> str:
    pattern = re.compile(
        rf"^\s*{re.escape(name)}\s*(?:==|>=)\s*{_VERSION}",
        re.I,
    )
    for raw in CONSTRAINTS.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        match = pattern.match(line)
        if match:
            return match.group(1)
    raise AssertionError(f"{CONSTRAINTS}: missing security floor for {name}")


def _dev_floor(name: str) -> str:
    pattern = re.compile(
        rf"^\s*{re.escape(name)}\s*>=\s*{_VERSION}",
        re.I,
    )
    for raw in REQ_DEV.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        match = pattern.match(line)
        if match:
            return match.group(1)
    raise AssertionError(f"{REQ_DEV}: missing dev floor for {name}")


def test_setup_geosync_bootstrap_matches_security_floors() -> None:
    for package in ("setuptools", "wheel"):
        action_pin = _action_exact_pin(package)
        security_floor = _constraint_floor(package)
        assert _version_tuple(action_pin) >= _version_tuple(security_floor), (
            f"{ACTION}: {package}=={action_pin} is below security floor "
            f"{security_floor} from {CONSTRAINTS}"
        )


def test_setup_geosync_pip_matches_dev_security_floor() -> None:
    action_pin = _action_exact_pin("pip")
    dev_floor = _dev_floor("pip")
    assert _version_tuple(action_pin) >= _version_tuple(dev_floor), (
        f"{ACTION}: pip=={action_pin} is below dev/security floor {dev_floor} "
        f"from {REQ_DEV}"
    )


def test_setup_geosync_reasserts_packaging_pins_after_lock_install() -> None:
    text = _action_text()
    dev_lock_install = text.index("requirements-dev.lock")
    for package in ("pip", "setuptools", "wheel"):
        pin = _action_exact_pin(package)
        reassert_index = text.rindex(f"{package}=={pin}")
        assert reassert_index > dev_lock_install, (
            f"{ACTION}: {package}=={pin} must be reasserted after lock install "
            "so transitive lock side effects cannot change the trusted toolchain"
        )
