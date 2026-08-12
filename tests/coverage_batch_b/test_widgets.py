# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Behavioural coverage for analytics.code_health.widgets."""

from __future__ import annotations

from datetime import datetime, timezone

from analytics.code_health import widgets
from analytics.code_health.models import FileMetrics, RiskProfile


def _fm(path: str) -> FileMetrics:
    return FileMetrics(
        path=path,
        total_lines=100,
        avg_cyclomatic_complexity=7.5,
        max_cyclomatic_complexity=12,
        functions=[],
        coupling=4,
        fan_in=2,
        fan_out=3,
        change_frequency=5,
        interface_stability=0.6,
        churn=42,
        hot_spot_score=30.0,
        risk_profile=RiskProfile(risk_score=0.83),
    )


def test_render_widget_with_hotspots() -> None:
    ctx = {
        "generated_at": datetime(2026, 6, 1, 13, 45, tzinfo=timezone.utc),
        "hotspots": [_fm("core/engine.py")],
        "theme": "dark",
    }
    html = widgets.render_widget(ctx)
    assert 'data-theme="dark"' in html
    assert "core/engine.py" in html
    assert "Risk: 0.83" in html
    assert "Complexity: 7.50" in html
    assert "Churn: 42" in html
    assert "2026-06-01 13:45 UTC" in html


def test_render_widget_empty_hotspots_shows_placeholder() -> None:
    ctx = {
        "generated_at": datetime(2026, 1, 2, 0, 0, tzinfo=timezone.utc),
        "hotspots": [],
        "theme": "light",
    }
    html = widgets.render_widget(ctx)
    assert "No hotspots detected" in html
    assert 'data-theme="light"' in html


def test_render_widget_autoescapes_path() -> None:
    fm = _fm("<script>alert(1)</script>.py")
    ctx = {
        "generated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "hotspots": [fm],
        "theme": "light",
    }
    html = widgets.render_widget(ctx)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
