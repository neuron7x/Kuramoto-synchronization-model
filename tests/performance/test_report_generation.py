"""Tests for performance report generation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestReportGeneration:
    """Test performance report generation functions."""
    
    def test_format_metric(self):
        """Test metric formatting."""
        from scripts.performance.generate_performance_report import format_metric
        
        assert format_metric(150.5) == "150.5ms"
        assert format_metric(99.99) == "99.99ms"
        assert format_metric(10.123) == "10.12ms"
        assert format_metric(1.234) == "1.234ms"
        assert format_metric(150.5, "s") == "150.5s"
    
    def test_generate_summary_table(self):
        """Test summary table generation."""
        from scripts.performance.generate_performance_report import generate_summary_table
        
        results = {
            "order_router": {
                "metrics": {
                    "p50_ms": 85.0,
                    "p95_ms": 120.0,
                    "p99_ms": 150.0,
                },
                "budgets": {
                    "p50_ms": 100.0,
                    "p95_ms": 150.0,
                    "p99_ms": 200.0,
                },
                "passed": True,
            }
        }
        
        table = generate_summary_table(results)
        
        assert len(table) > 0
        assert any("order_router" in line for line in table)
        assert any("✅ PASS" in line for line in table)
    
    def test_generate_violations_section_with_violations(self):
        """Test violations section with violations."""
        from scripts.performance.generate_performance_report import generate_violations_section
        
        results = {
            "order_router": {
                "passed": False,
                "violations": [
                    "p50: 95.2ms exceeds budget 85.0ms",
                    "Stability: CoV 0.245 exceeds threshold 0.150",
                ],
            }
        }
        
        section = generate_violations_section(results)
        
        assert len(section) > 0
        assert any("Performance Budget Violations" in line for line in section)
        assert any("p50: 95.2ms exceeds budget" in line for line in section)
    
    def test_generate_violations_section_without_violations(self):
        """Test violations section without violations."""
        from scripts.performance.generate_performance_report import generate_violations_section
        
        results = {
            "order_router": {
                "passed": True,
                "violations": [],
            }
        }
        
        section = generate_violations_section(results)
        
        assert len(section) == 0
    
    def test_generate_stability_section(self):
        """Test stability section generation."""
        from scripts.performance.generate_performance_report import generate_stability_section
        
        results = {
            "order_router": {
                "metrics": {
                    "mean_ms": 85.5,
                    "std_ms": 10.2,
                    "min_ms": 70.0,
                    "max_ms": 110.0,
                    "samples": 100,
                },
            }
        }
        
        section = generate_stability_section(results)
        
        assert len(section) > 0
        assert any("Stability Metrics" in line for line in section)
        assert any("order_router" in line for line in section)
    
    def test_generate_performance_report(self, tmp_path: Path):
        """Test full report generation."""
        from scripts.performance.generate_performance_report import generate_performance_report
        
        # Create test benchmark results
        benchmark_results = tmp_path / "results.json"
        benchmark_results.write_text(json.dumps({
            "order_router": {
                "component": "order_router",
                "metrics": {
                    "p50_ms": 85.0,
                    "p95_ms": 120.0,
                    "p99_ms": 150.0,
                    "mean_ms": 88.0,
                    "std_ms": 10.0,
                    "min_ms": 70.0,
                    "max_ms": 130.0,
                    "samples": 100,
                },
                "budgets": {
                    "p50_ms": 100.0,
                    "p95_ms": 150.0,
                    "p99_ms": 200.0,
                },
                "passed": True,
                "violations": [],
            }
        }))
        
        output_path = tmp_path / "report.md"
        
        report = generate_performance_report(
            benchmark_results,
            output_path,
        )
        
        assert len(report) > 0
        assert "Performance Benchmark Report" in report
        assert "order_router" in report
        assert output_path.exists()
        
        # Check file content
        content = output_path.read_text()
        assert "Performance Benchmark Report" in content
    
    def test_generate_trend_section_no_file(self):
        """Test trend section when no trend report exists."""
        from scripts.performance.generate_performance_report import generate_trend_section
        
        section = generate_trend_section(Path("/nonexistent/file.md"))
        
        assert len(section) == 0
    
    def test_generate_artifacts_section(self, tmp_path: Path):
        """Test artifacts section generation."""
        from scripts.performance.generate_performance_report import generate_artifacts_section
        
        # Create test flamegraph
        flamegraph_dir = tmp_path / "flamegraphs"
        flamegraph_dir.mkdir()
        (flamegraph_dir / "order_router_flamegraph.svg").write_text("<svg></svg>")
        
        section = generate_artifacts_section(
            flamegraph_dir,
            "https://example.com/artifacts"
        )
        
        assert len(section) > 0
        assert any("Artifacts" in line for line in section)
        assert any("order_router" in line for line in section)


class TestFlamegraphGeneration:
    """Test flamegraph generation functions."""
    
    def test_generate_all_flamegraphs_with_invalid_components(self, tmp_path: Path):
        """Test that invalid components are handled gracefully."""
        from scripts.performance.generate_flamegraphs import generate_all_flamegraphs
        
        # This should not raise an error even with invalid components
        flamegraphs = generate_all_flamegraphs(
            tmp_path,
            components=["nonexistent_component"],
            duration=1,
        )
        
        # Should return empty list or handle gracefully
        assert isinstance(flamegraphs, list)
