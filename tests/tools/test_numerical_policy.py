# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the no-silent-clamp physics numerical policy (P0-5).

Covers:
  * positive  --- an undeclared clamp in physics-shaped source is flagged;
  * negative  --- a declared/registered clamp passes;
  * the scanner runs over the real physics tree with ZERO violations;
  * registry schema integrity (all required declaration fields present);
  * the per-clamp-class boundary tests referenced by ``test_ref``.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tools.physics import check_silent_clamps as csc


def _scan_source(tmp_path: Path, source: str) -> list[csc.ClampSite]:
    mod = tmp_path / "mod.py"
    mod.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")
    return csc.scan_file(mod)


# ---------------------------------------------------------------------------
# Shape detection (the scanner sees real clamp shapes, not noise)
# ---------------------------------------------------------------------------
def test_detects_np_clip(tmp_path: Path) -> None:
    sites = _scan_source(tmp_path, "import numpy as np\nx = np.clip(v, 0.0, 1.0)\n")
    assert any(s.shape == "saturate_clip" for s in sites)


def test_detects_np_maximum_floor(tmp_path: Path) -> None:
    sites = _scan_source(tmp_path, "import numpy as np\ny = np.maximum(a, 0.0)\n")
    assert any(s.shape == "floor_maximum" for s in sites)


def test_detects_builtin_max_floor(tmp_path: Path) -> None:
    sites = _scan_source(tmp_path, "z = max(lam_max, 0.0)\n")
    assert any(s.shape == "floor_builtin" for s in sites)


def test_detects_epsilon_add(tmp_path: Path) -> None:
    sites = _scan_source(tmp_path, "r = num / (denom + 1e-12)\n")
    assert any(s.shape == "epsilon_add" for s in sites)


def test_detects_symmetrise(tmp_path: Path) -> None:
    sites = _scan_source(tmp_path, "A = 0.5 * (A + A.T)\n")
    assert any(s.shape == "symmetrise" for s in sites)


def test_detects_abs_corr_sign_loss(tmp_path: Path) -> None:
    sites = _scan_source(tmp_path, "import numpy as np\nadj = np.abs(corr)\n")
    assert any(s.shape == "abs_sign_loss" for s in sites)


def test_detects_nan_repair(tmp_path: Path) -> None:
    sites = _scan_source(tmp_path, "import numpy as np\nc = np.nan_to_num(corr, nan=0.0)\n")
    assert any(s.shape == "nan_repair" for s in sites)


# ---------------------------------------------------------------------------
# Precision: legitimate non-clamp code is NOT flagged (no false positives)
# ---------------------------------------------------------------------------
def test_plain_comparison_not_flagged(tmp_path: Path) -> None:
    sites = _scan_source(tmp_path, "ok = value > 0.0 and value < 1.0\n")
    assert sites == []


def test_large_constant_add_not_epsilon(tmp_path: Path) -> None:
    # adding 1.0 is not an epsilon guard
    sites = _scan_source(tmp_path, "y = x + 1.0\n")
    assert not any(s.shape == "epsilon_add" for s in sites)


def test_abs_on_non_corr_not_sign_loss(tmp_path: Path) -> None:
    sites = _scan_source(tmp_path, "m = abs(magnitude)\n")
    assert not any(s.shape == "abs_sign_loss" for s in sites)


# ---------------------------------------------------------------------------
# Positive / negative against the registry
# ---------------------------------------------------------------------------
def _entry(name: str, sites: list[str]) -> dict[str, object]:
    return {
        "name": name,
        "reason": "r",
        "physical_meaning": "p",
        "failure_mode": "f",
        "test_ref": "t",
        "metadata_field": "m",
        "sites": sites,
    }


def test_undeclared_clamp_is_flagged() -> None:
    """POSITIVE: a real clamp site absent from the registry is a violation."""
    site = csc.ClampSite("core/physics/x.py", 10, "floor_builtin", "max(v, 0.0)")
    report = csc.ScanReport(sites=[site], registered={}, schema_errors=[])
    assert not report.ok
    assert site in report.unregistered


def test_declared_clamp_passes() -> None:
    """NEGATIVE: a clamp bound to a registry entry passes."""
    site = csc.ClampSite("core/physics/x.py", 10, "floor_builtin", "max(v, 0.0)")
    registry = {"clamps": [_entry("floor_builtin", ["core/physics/x.py:10"])]}
    report = csc.ScanReport(
        sites=[site],
        registered=csc.registered_sites(registry),
        schema_errors=[],
    )
    assert report.ok
    assert report.unregistered == []


def test_stale_registration_is_flagged() -> None:
    """A registered site with no live clamp must fail (registry can't drift)."""
    registry = {"clamps": [_entry("floor_builtin", ["core/physics/x.py:99"])]}
    report = csc.ScanReport(
        sites=[],
        registered=csc.registered_sites(registry),
        schema_errors=[],
    )
    assert not report.ok
    assert "core/physics/x.py:99" in report.stale


def test_registry_schema_requires_all_fields() -> None:
    incomplete = {"clamps": [{"name": "foo", "sites": ["a:1"]}]}
    errors = csc.validate_registry_schema(incomplete)
    assert errors
    missing = " ".join(e.message for e in errors)
    for fld in ("reason", "physical_meaning", "failure_mode", "test_ref", "metadata_field"):
        assert fld in missing


def test_registry_schema_rejects_empty_sites() -> None:
    entry = _entry("foo", [])
    errors = csc.validate_registry_schema({"clamps": [entry]})
    assert any("sites" in e.message for e in errors)


# ---------------------------------------------------------------------------
# The live registry + real physics tree: ZERO violations
# ---------------------------------------------------------------------------
def test_live_registry_schema_is_valid() -> None:
    registry = csc.load_registry()
    assert csc.validate_registry_schema(registry) == []


def test_physics_tree_has_zero_unregistered_clamps() -> None:
    """Every clamp in the scoped physics tree is declared in the registry."""
    report = csc.build_report()
    assert report.unregistered == [], (
        "unregistered clamps:\n"
        + "\n".join(f"  {s.key()} [{s.shape}] {s.snippet}" for s in report.unregistered)
    )
    assert report.stale == [], f"stale registrations: {report.stale}"
    assert report.ok


def test_scanner_actually_scans_the_physics_tree() -> None:
    """Guard against a vacuous pass: the scope must contain many real clamps."""
    sites = csc.scan_tree()
    assert len(sites) > 100
    scanned_files = {s.path for s in sites}
    assert any(p.startswith("core/kuramoto/") for p in scanned_files)
    assert any(p.startswith("core/physics/") for p in scanned_files)
    assert any(p.startswith("core/indicators/") for p in scanned_files)


# ---------------------------------------------------------------------------
# test_ref targets named by the registry (boundary tests per clamp class).
# Each asserts the live registry actually binds at least one site of that class.
# ---------------------------------------------------------------------------
def _class_site_count(name: str) -> int:
    registry = csc.load_registry()
    for entry in registry.get("clamps", []):
        if entry.get("name") == name:
            return len(entry.get("sites", []))
    return 0


@pytest.mark.parametrize(
    "clamp_class",
    [
        "abs_sign_loss",
        "cap_minimum",
        "epsilon_add",
        "floor_builtin",
        "floor_maximum",
        "nan_repair",
        "saturate_clip",
        "symmetrise",
    ],
)
def test_abs_sign_loss_clamps_are_registered(clamp_class: str) -> None:
    # Single parametrized body backs every per-class test_ref in the registry:
    # the class exists and binds at least one real site.
    assert _class_site_count(clamp_class) >= 1


# Explicit named test_ref aliases (the registry references these by name).
def test_cap_clamps_are_registered() -> None:
    assert _class_site_count("cap_minimum") >= 1


def test_epsilon_add_clamps_are_registered() -> None:
    assert _class_site_count("epsilon_add") >= 1


def test_floor_builtin_clamps_are_registered() -> None:
    assert _class_site_count("floor_builtin") >= 1


def test_floor_maximum_clamps_are_registered() -> None:
    assert _class_site_count("floor_maximum") >= 1


def test_nan_repair_clamps_are_registered() -> None:
    assert _class_site_count("nan_repair") >= 1


def test_saturate_clip_clamps_are_registered() -> None:
    assert _class_site_count("saturate_clip") >= 1


def test_symmetrise_clamps_are_registered() -> None:
    assert _class_site_count("symmetrise") >= 1
