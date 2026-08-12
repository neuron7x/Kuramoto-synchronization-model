# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed regression for release_gate proof probes E/H/K/M.

Before the fix, ``_regenerate`` discarded the subprocess return code, so when a
generator crashed the probe silently read the STALE committed artifact and went
GREEN. Each test below drives ``_regenerate`` to a non-zero (crashed) return
while leaving a *passing* committed artifact in place. On the old code the probe
returns GREEN (fail-open); the fix must return RED refusing the stale artifact.
"""

from __future__ import annotations

from typing import Callable

import pytest

import scripts.ci.release_gate as rg

# (probe, module-that-crashes, passing-artifact-payload)
_CASES: list[tuple[Callable[[bool], tuple[str, str]], dict[str, object]]] = [
    (rg.probe_e_clean_clone, {"status": "PASS"}),
    (
        rg.probe_h_falsification,
        {"promotion_allowed": True, "controls": [{"verdict": "SURVIVED"}]},
    ),
    (
        rg.probe_k_execution,
        {"status": "PASS", "claim_boundary_enforced": True, "scope": "backtest"},
    ),
    (rg.probe_m_benchmarks, {"status": "PASS", "hardware_id": "x"}),
    # DEFECT 1: probe_g_real_data ignored the regen returncode and read the
    # (possibly stale) committed manifest -> GREEN on a crashed generator.
    (rg.probe_g_real_data, {"status": "MEASURED_SINGLE", "manifests_found": 1}),
]


@pytest.mark.parametrize("probe,passing_artifact", _CASES)
def test_probe_refuses_stale_artifact_when_regen_crashes(
    probe: Callable[[bool], tuple[str, str]],
    passing_artifact: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Generator "crashes" (non-zero) yet a committed passing artifact remains.
    monkeypatch.setattr(rg, "_regenerate", lambda *a, **k: 1)
    monkeypatch.setattr(rg, "_read_artifact", lambda rel: dict(passing_artifact))
    status, detail = probe(True)
    assert status == rg.RED, f"stale passing artifact must be refused, got {status}: {detail}"
    assert "stale artifact refused" in detail


@pytest.mark.parametrize("probe,passing_artifact", _CASES)
def test_probe_green_when_regen_succeeds(
    probe: Callable[[bool], tuple[str, str]],
    passing_artifact: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Generator succeeds (exit 0) -> the fresh passing artifact promotes GREEN.
    monkeypatch.setattr(rg, "_regenerate", lambda *a, **k: 0)
    monkeypatch.setattr(rg, "_read_artifact", lambda rel: dict(passing_artifact))
    status, _ = probe(True)
    assert status == rg.GREEN


def test_regenerate_returns_int() -> None:
    """The helper must surface the subprocess return code (not None)."""
    rc = rg._regenerate("scripts.ci.__nonexistent_module_xyz__")
    assert isinstance(rc, int)
    assert rc != 0
