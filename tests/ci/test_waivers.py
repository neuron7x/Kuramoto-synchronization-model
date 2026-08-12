# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Falsification battery for the fail-closed waiver gate.

Every temporary deviation must carry a rationale, scope, compensating control,
owner, two-tier approval, and — non-negotiably — a dated expiry. These tests
pin the boundary the gate must hold:

  NEGATIVE controls (each MUST turn the gate RED / non-zero):
    1. an expired waiver;
    2. a waiver on a P0 item (P0 can NEVER be waived);
    3. a P1 waiver with a single approver;
    4. a waiver with no expiry.

  POSITIVE control (MUST be GREEN / exit 0):
    a valid, unexpired P1 waiver with two distinct approvers.

Determinism: the checker is always handed an explicit ``--now`` date, so no
test depends on the wall clock. Each waiver lives in its own tmp directory so
the controls are isolated.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_waivers.py"
_spec = importlib.util.spec_from_file_location("check_waivers", _MOD_PATH)
assert _spec and _spec.loader
_gate = importlib.util.module_from_spec(_spec)
# Register before exec: the module defines @dataclass with string annotations
# (from __future__ import annotations), whose resolution needs the module in
# sys.modules.
sys.modules["check_waivers"] = _gate
_spec.loader.exec_module(_gate)

NOW = "2026-07-19"


def _write_waiver(tmp_path: Path, body: str, name: str = "waiver.yaml") -> Path:
    d = tmp_path / "waivers"
    d.mkdir(exist_ok=True)
    (d / name).write_text(textwrap.dedent(body), encoding="utf-8")
    return d


def _run(waivers_dir: Path, now: str = NOW) -> int:
    return _gate.main(["--now", now, "--waivers-dir", str(waivers_dir)])


_VALID_P1 = """\
waiver:
  id: WVR-TEST-P1
  gate: check_example
  priority: P1
  rationale: transient upstream flake being fixed
  scope: only the p99 assertion on shared runner
  compensating_control: hard ceiling still fails closed
  owner: yaroslav.vasylenko
  approvers:
    - yaroslav.vasylenko
    - release-captain
  expiry: "2099-12-31"
  revalidation_command: python scripts/ci/check_example.py --now 2099-12-31
"""


# --------------------------------------------------------------------------- #
# POSITIVE control
# --------------------------------------------------------------------------- #
def test_valid_unexpired_p1_two_approvers_is_green(tmp_path: Path) -> None:
    d = _write_waiver(tmp_path, _VALID_P1)
    assert _run(d) == 0


# --------------------------------------------------------------------------- #
# NEGATIVE control 1 — expired waiver -> RED
# --------------------------------------------------------------------------- #
def test_expired_waiver_is_red(tmp_path: Path) -> None:
    body = _VALID_P1.replace('expiry: "2099-12-31"', 'expiry: "2026-07-18"')
    d = _write_waiver(tmp_path, body)
    assert _run(d, now="2026-07-19") != 0


# --------------------------------------------------------------------------- #
# NEGATIVE control 2 — P0 can NEVER be waived -> RED
# --------------------------------------------------------------------------- #
def test_p0_waiver_is_red(tmp_path: Path) -> None:
    body = _VALID_P1.replace("priority: P1", "priority: P0")
    d = _write_waiver(tmp_path, body)
    assert _run(d) != 0


# --------------------------------------------------------------------------- #
# NEGATIVE control 3 — P1 with a single approver -> RED
# --------------------------------------------------------------------------- #
def test_p1_single_approver_is_red(tmp_path: Path) -> None:
    body = """\
    waiver:
      id: WVR-TEST-P1-UNDER
      gate: check_example
      priority: P1
      rationale: transient upstream flake being fixed
      scope: only the p99 assertion on shared runner
      compensating_control: hard ceiling still fails closed
      owner: yaroslav.vasylenko
      approvers:
        - yaroslav.vasylenko
      expiry: "2099-12-31"
      revalidation_command: python scripts/ci/check_example.py --now 2099-12-31
    """
    d = _write_waiver(tmp_path, body)
    assert _run(d) != 0


# --------------------------------------------------------------------------- #
# NEGATIVE control 4 — missing expiry -> RED
# --------------------------------------------------------------------------- #
def test_missing_expiry_is_red(tmp_path: Path) -> None:
    body = """\
    waiver:
      id: WVR-TEST-NO-EXPIRY
      gate: check_example
      priority: P1
      rationale: transient upstream flake being fixed
      scope: only the p99 assertion on shared runner
      compensating_control: hard ceiling still fails closed
      owner: yaroslav.vasylenko
      approvers:
        - yaroslav.vasylenko
        - release-captain
      revalidation_command: python scripts/ci/check_example.py --now 2099-12-31
    """
    d = _write_waiver(tmp_path, body)
    assert _run(d) != 0


# --------------------------------------------------------------------------- #
# Extra fail-closed edges (not required, but cheap to pin)
# --------------------------------------------------------------------------- #
def test_missing_waivers_dir_is_fail_closed(tmp_path: Path) -> None:
    assert _run(tmp_path / "does-not-exist") == 2


def test_expiry_exactly_now_is_green(tmp_path: Path) -> None:
    body = _VALID_P1.replace('expiry: "2099-12-31"', 'expiry: "2026-07-19"')
    d = _write_waiver(tmp_path, body)
    assert _run(d, now="2026-07-19") == 0


def test_committed_example_waiver_is_valid() -> None:
    """The checked-in example waiver must itself pass as of a date within its window."""
    real_dir = Path(__file__).resolve().parents[2] / "governance" / "waivers"
    assert _gate.main(["--now", NOW, "--waivers-dir", str(real_dir)]) == 0
