"""T8 · operational_incidents.csv is append-only with fixed schema."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SHADOW = REPO / "results" / "cross_asset_kuramoto" / "shadow_validation"
INCIDENTS = SHADOW / "operational_incidents.csv"
RUNNER_SCRIPT = REPO / "scripts" / "run_cross_asset_kuramoto_shadow.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("shadow_runner", RUNNER_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_incident_schema_matches_contract() -> None:
    mod = _load_runner()
    expected = set(mod.INCIDENT_COLUMNS)
    if not INCIDENTS.exists():
        pytest.skip("no incidents logged yet")
    df = pd.read_csv(INCIDENTS)
    assert set(df.columns) == expected


def test_incident_append_only(tmp_path: Path, monkeypatch) -> None:
    """Appending an incident must never shrink the existing ledger."""
    mod = _load_runner()
    fake = tmp_path / "operational_incidents.csv"
    monkeypatch.setattr(mod, "INCIDENTS", fake)
    mod._append_incident(
        {
            "incident_ts": "2026-04-22T00:00:00Z",
            "incident_type": "test_event",
            "severity": "LOW",
            "affected_run_date": "2026-04-22",
            "description": "unit test 1",
            "resolved_yes_no": "yes",
            "resolution_ts": "2026-04-22T00:00:01Z",
            "changed_artifacts_yes_no": "no",
        }
    )
    a = pd.read_csv(fake)
    assert len(a) == 1
    mod._append_incident(
        {
            "incident_ts": "2026-04-22T00:00:02Z",
            "incident_type": "test_event",
            "severity": "LOW",
            "affected_run_date": "2026-04-22",
            "description": "unit test 2",
            "resolved_yes_no": "yes",
            "resolution_ts": "2026-04-22T00:00:03Z",
            "changed_artifacts_yes_no": "no",
        }
    )
    b = pd.read_csv(fake)
    assert len(b) == 2
    assert list(b["description"]) == ["unit test 1", "unit test 2"]


def test_renderer_runs_offline_and_without_input() -> None:
    """T9 · renderer produces SHADOW_SUMMARY.md and surfaces caveats."""
    import subprocess

    rc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "render_cross_asset_kuramoto_shadow_report.py")],
        cwd=str(REPO),
        capture_output=True,
        timeout=30,
    )
    assert rc.returncode == 0
    summary = SHADOW / "SHADOW_SUMMARY.md"
    text = summary.read_text()
    # T10: known caveats must be surfaced
    assert "OBS-1" in text
    assert "DP5" in text or "forward-fill" in text
    assert "DP3" in text or "snapshot" in text
    # No optimisation language
    for bad in ("optimize", "tune", "grid", "sweep", "edge", "alpha"):
        assert bad.lower() not in text.lower(), f"forbidden term {bad!r} in summary"
