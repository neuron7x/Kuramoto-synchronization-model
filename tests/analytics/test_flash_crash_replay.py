from __future__ import annotations

from pathlib import Path

import numpy as np

from analytics.staging.flash_crash_replay import (
    generate_staging_report,
    simulate_flash_crash_replay,
    write_staging_metrics,
)


def test_flash_crash_replay_generates_toxic_flow_and_stable_rl() -> None:
    result = simulate_flash_crash_replay(steps=48, seed=5)

    assert len(result.metrics.vpin_series) >= 48
    assert float(np.max(result.metrics.vpin_series[-24:])) > 0.8
    assert result.metrics.rl_action_change_rate <= 0.5
    assert result.metrics.monotonic_violations == 0
    assert result.metrics.link_activator_fallback_stable is True


def test_flash_crash_report_outputs(tmp_path: Path) -> None:
    result = simulate_flash_crash_replay(steps=24, seed=11)

    metrics_path = tmp_path / "staging_report.json"
    write_staging_metrics(result, metrics_path)
    payload = metrics_path.read_text(encoding="utf-8")
    assert "flash_crash_replay" in payload
    assert "vpin_max" in payload

    report_path = tmp_path / "STAGING_REPORT.md"
    generate_staging_report(result, report_path)
    content = report_path.read_text(encoding="utf-8")
    assert "48h Staging Report" in content
    assert "Synthetic Tail Metrics" in content
    assert "thermo_audit.jsonl" in content
