"""Tests for historical trend tracking."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.performance.track_historical_trends import (
    HistoricalDataPoint,
    PerformanceHistory,
    update_history,
    generate_trend_report,
)


class TestPerformanceHistory:
    """Test performance history management."""
    
    def test_init_creates_empty_history(self, tmp_path: Path):
        """Test initialization with no existing file."""
        history_file = tmp_path / "history.json"
        history = PerformanceHistory(history_file)
        
        assert history.data == []
    
    def test_load_existing_history(self, tmp_path: Path):
        """Test loading existing history file."""
        history_file = tmp_path / "history.json"
        
        existing_data = [
            {
                "timestamp": "2024-01-01T00:00:00Z",
                "commit_sha": "abc123",
                "branch": "main",
                "component": "test",
                "p50_ms": 50.0,
                "p95_ms": 80.0,
                "p99_ms": 100.0,
                "mean_ms": 52.0,
                "std_ms": 5.0,
            }
        ]
        
        with open(history_file, "w") as f:
            json.dump(existing_data, f)
        
        history = PerformanceHistory(history_file)
        
        assert len(history.data) == 1
        assert history.data[0]["component"] == "test"
    
    def test_add_benchmark(self, tmp_path: Path):
        """Test adding new benchmark result."""
        history_file = tmp_path / "history.json"
        history = PerformanceHistory(history_file)
        
        metrics = {
            "p50_ms": 55.0,
            "p95_ms": 85.0,
            "p99_ms": 105.0,
            "mean_ms": 57.0,
            "std_ms": 6.0,
        }
        
        history.add_benchmark(
            component="test_component",
            metrics=metrics,
            commit_sha="def456",
            branch="feature",
        )
        
        assert len(history.data) == 1
        assert history.data[0]["component"] == "test_component"
        assert history.data[0]["commit_sha"] == "def456"
        assert history.data[0]["p50_ms"] == 55.0
    
    def test_save_and_load(self, tmp_path: Path):
        """Test save and load round-trip."""
        history_file = tmp_path / "history.json"
        history = PerformanceHistory(history_file)
        
        history.add_benchmark(
            "test",
            {"p50_ms": 50.0, "p95_ms": 80.0, "p99_ms": 100.0, "mean_ms": 52.0, "std_ms": 5.0},
            "abc123",
            "main",
        )
        
        history.save()
        
        # Load in new instance
        history2 = PerformanceHistory(history_file)
        
        assert len(history2.data) == 1
        assert history2.data[0]["component"] == "test"
    
    def test_get_component_history(self, tmp_path: Path):
        """Test retrieving component-specific history."""
        history_file = tmp_path / "history.json"
        history = PerformanceHistory(history_file)
        
        # Add multiple components
        for i, component in enumerate(["comp1", "comp2", "comp1", "comp2"]):
            history.add_benchmark(
                component,
                {"p50_ms": float(i * 10), "p95_ms": 0, "p99_ms": 0, "mean_ms": 0, "std_ms": 0},
                f"sha{i}",
                "main",
            )
        
        comp1_history = history.get_component_history("comp1")
        
        # Should have 2 entries for comp1, most recent first
        assert len(comp1_history) == 2
        assert comp1_history[0].p50_ms == 20.0  # Most recent
        assert comp1_history[1].p50_ms == 0.0   # Older
    
    def test_get_component_history_limit(self, tmp_path: Path):
        """Test limiting history results."""
        history_file = tmp_path / "history.json"
        history = PerformanceHistory(history_file)
        
        # Add 10 entries
        for i in range(10):
            history.add_benchmark(
                "test",
                {"p50_ms": float(i), "p95_ms": 0, "p99_ms": 0, "mean_ms": 0, "std_ms": 0},
                f"sha{i}",
                "main",
            )
        
        limited = history.get_component_history("test", limit=5)
        
        assert len(limited) == 5
        # Should be most recent 5
        assert limited[0].p50_ms == 9.0


class TestTrendAnalysis:
    """Test trend analysis calculations."""
    
    def test_trend_stable(self, tmp_path: Path):
        """Test stable trend detection."""
        history_file = tmp_path / "history.json"
        history = PerformanceHistory(history_file)
        
        # Add stable data (around 50ms)
        for i in range(10):
            history.add_benchmark(
                "test",
                {"p50_ms": 50.0, "p95_ms": 80.0, "p99_ms": 100.0, "mean_ms": 52.0, "std_ms": 5.0},
                f"sha{i}",
                "main",
            )
        
        summary = history.get_trend_summary("test", lookback=10)
        
        assert summary["trend"] == "stable"
        assert abs(summary["slope_ms_per_commit"]) < 0.1
    
    def test_trend_degrading(self, tmp_path: Path):
        """Test degrading trend detection."""
        history_file = tmp_path / "history.json"
        history = PerformanceHistory(history_file)
        
        # Add degrading data (increasing p50)
        for i in range(10):
            history.add_benchmark(
                "test",
                {"p50_ms": 50.0 + i * 5.0, "p95_ms": 80.0, "p99_ms": 100.0, "mean_ms": 52.0, "std_ms": 5.0},
                f"sha{i}",
                "main",
            )
        
        summary = history.get_trend_summary("test", lookback=10)
        
        assert summary["trend"] == "degrading"
        assert summary["slope_ms_per_commit"] > 0.1
    
    def test_trend_improving(self, tmp_path: Path):
        """Test improving trend detection."""
        history_file = tmp_path / "history.json"
        history = PerformanceHistory(history_file)
        
        # Add improving data (decreasing p50)
        for i in range(10):
            history.add_benchmark(
                "test",
                {"p50_ms": 100.0 - i * 5.0, "p95_ms": 120.0, "p99_ms": 140.0, "mean_ms": 102.0, "std_ms": 8.0},
                f"sha{i}",
                "main",
            )
        
        summary = history.get_trend_summary("test", lookback=10)
        
        assert summary["trend"] == "improving"
        assert summary["slope_ms_per_commit"] < -0.1
    
    def test_trend_insufficient_data(self, tmp_path: Path):
        """Test trend with insufficient data."""
        history_file = tmp_path / "history.json"
        history = PerformanceHistory(history_file)
        
        # Add only 1 point
        history.add_benchmark(
            "test",
            {"p50_ms": 50.0, "p95_ms": 80.0, "p99_ms": 100.0, "mean_ms": 52.0, "std_ms": 5.0},
            "sha1",
            "main",
        )
        
        summary = history.get_trend_summary("test", lookback=10)
        
        assert summary["trend"] == "insufficient_data"


class TestUpdateHistory:
    """Test history update functionality."""
    
    def test_update_history(self, tmp_path: Path):
        """Test updating history from benchmark results."""
        history_file = tmp_path / "history.json"
        
        benchmark_results = {
            "order_router": {
                "metrics": {
                    "p50_ms": 85.0,
                    "p95_ms": 120.0,
                    "p99_ms": 150.0,
                    "mean_ms": 88.0,
                    "std_ms": 10.0,
                },
                "passed": True,
            },
            "link_activator": {
                "metrics": {
                    "p50_ms": 65.0,
                    "p95_ms": 90.0,
                    "p99_ms": 110.0,
                    "mean_ms": 67.0,
                    "std_ms": 8.0,
                },
                "passed": True,
            },
        }
        
        update_history(
            benchmark_results,
            history_file,
            commit_sha="test123",
            branch="main",
        )
        
        # Load and verify
        history = PerformanceHistory(history_file)
        
        assert len(history.data) == 2
        
        # Check both components were added
        components = {entry["component"] for entry in history.data}
        assert components == {"order_router", "link_activator"}


class TestTrendReport:
    """Test trend report generation."""
    
    def test_generate_trend_report(self, tmp_path: Path):
        """Test generating markdown trend report."""
        history_file = tmp_path / "history.json"
        history = PerformanceHistory(history_file)
        
        # Add some history
        for i in range(5):
            history.add_benchmark(
                "order_router",
                {"p50_ms": 85.0 + i, "p95_ms": 120.0, "p99_ms": 150.0, "mean_ms": 88.0, "std_ms": 10.0},
                f"sha{i}",
                "main",
            )
        
        history.save()
        
        output_file = tmp_path / "report.md"
        report = generate_trend_report(history_file, output_file, lookback=5)
        
        assert "Performance Trend Report" in report
        assert "order_router" in report
        assert output_file.exists()
        
        # Check file content
        content = output_file.read_text()
        assert "Performance Trend Report" in content
    
    def test_trend_report_with_insufficient_data(self, tmp_path: Path):
        """Test report generation with minimal data."""
        history_file = tmp_path / "history.json"
        history = PerformanceHistory(history_file)
        
        # Add only one data point
        history.add_benchmark(
            "test",
            {"p50_ms": 50.0, "p95_ms": 80.0, "p99_ms": 100.0, "mean_ms": 52.0, "std_ms": 5.0},
            "sha1",
            "main",
        )
        
        history.save()
        
        report = generate_trend_report(history_file, lookback=10)
        
        # Should still generate a report
        assert "Performance Trend Report" in report
        assert "insufficient_data" in report or "Data points: 1" in report
