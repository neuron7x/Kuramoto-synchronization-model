# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit coverage for report generation helpers."""

from __future__ import annotations

from pathlib import Path

from core.config.cli_models import ReportConfig
from core.reporting import (
    generate_markdown_report,
    render_markdown_to_html,
    render_markdown_to_pdf,
)


def test_generate_markdown_report_concatenates_inputs(tmp_path: Path) -> None:
    first = tmp_path / "backtest.json"
    second = tmp_path / "exec.json"
    first.write_text('{\n  "value": 1\n}', encoding="utf-8")
    second.write_text('{\n  "latest_signal": 1.0\n}', encoding="utf-8")

    cfg = ReportConfig(name="unit", inputs=[first, second], output_path=tmp_path / "report.md")
    report = generate_markdown_report(cfg)

    assert "### Backtest" in report
    assert "### Exec" in report
    assert '"value"' in report
    assert "latest_signal" in report


def test_renderers_produce_html_and_pdf(tmp_path: Path) -> None:
    html_path = tmp_path / "report.html"
    pdf_path = tmp_path / "report.pdf"

    markdown = "### Section\n``\nHello\n```"
    render_markdown_to_html(markdown, html_path)
    render_markdown_to_pdf(markdown, pdf_path)

    html_text = html_path.read_text(encoding="utf-8")
    assert html_text.startswith("<!doctype html>")
    assert "Hello" in html_text

    pdf_bytes = pdf_path.read_bytes()
    assert pdf_bytes.startswith(b"%PDF")
    assert pdf_bytes.rstrip().endswith(b"%%EOF")
