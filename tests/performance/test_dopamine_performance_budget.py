from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def test_timing_report_has_measured_step(monkeypatch: Any, tmp_path: Path) -> None:
    from benchmarks import dopamine_benchmark

    report = tmp_path / "PERFORMANCE_REPORT.json"
    monkeypatch.setattr(dopamine_benchmark, "OUT", report)

    assert dopamine_benchmark.main() == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert 0.0 < payload["step_ms"] <= payload["budget_ms"]
    assert payload["iteration_count"] >= 1000
