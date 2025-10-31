from __future__ import annotations

from pathlib import Path

from scripts import benchmark_bonds


def test_run_benchmark_generates_metrics(monkeypatch):
    monkeypatch.setattr(benchmark_bonds.time, "sleep", lambda _x: None)
    metrics = benchmark_bonds.run_benchmark(iterations=5)

    assert metrics["samples"] > 0
    assert "dFdt_mean" in metrics


def test_main_creates_report(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(benchmark_bonds.time, "sleep", lambda _x: None)
    report = tmp_path / "monotonic.json"

    benchmark_bonds.main(
        ["--iterations", "5", "--target-dF", "1e-6", "--report", str(report)]
    )

    assert report.exists()
    data = report.read_text()
    assert "dFdt_mean" in data
