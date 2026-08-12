# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Assemble markdown reports from a collection of artifacts."""

from __future__ import annotations

from pathlib import Path

from core.config.cli_models import ReportConfig


def generate_markdown_report(cfg: ReportConfig) -> str:
    """Build a markdown report by concatenating artifact payloads."""
    sections: list[str] = []
    for artifact in cfg.inputs:
        path = Path(artifact)
        if not path.exists():
            raise FileNotFoundError(f"Report input {path} does not exist")
        payload = path.read_text(encoding="utf-8").strip()
        title = path.stem.replace("_", " ").title()
        sections.append(f"### {title}\n```\n{payload}\n```")
    return "\n\n".join(sections)
