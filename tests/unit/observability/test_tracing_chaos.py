from __future__ import annotations

import contextlib

from observability import tracing


def test_chaos_span_enriches_attributes(monkeypatch):
    captured: dict[str, object] = {}

    def fake_pipeline(stage: str, **attrs):
        captured["stage"] = stage
        captured["attrs"] = attrs
        return contextlib.nullcontext("span")

    monkeypatch.setattr(tracing, "pipeline_span", fake_pipeline)

    with tracing.chaos_span("matching-engine", severity="high") as span:
        assert span == "span"

    assert captured["stage"] == "chaos.matching-engine"
    assert captured["attrs"] == {
        "chaos.experiment": "matching-engine",
        "severity": "high",
    }
