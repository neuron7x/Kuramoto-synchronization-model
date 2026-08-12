# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for the conventional changelog generator."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from tools.release.conventional_changelog import (
    CommitInfo,
    render_changelog,
    update_changelog,
)


def test_render_changelog_groups_by_category() -> None:
    commits = [
        CommitInfo(
            sha="a" * 40,
            type="feat",
            scope="ingest",
            subject="Add kafka source",
            breaking=False,
            notes=[],
        ),
        CommitInfo(
            sha="b" * 40,
            type="fix",
            scope=None,
            subject="Handle reconnects",
            breaking=False,
            notes=[],
        ),
        CommitInfo(
            sha="c" * 40,
            type="docs",
            scope=None,
            subject="Document release process",
            breaking=False,
            notes=[],
        ),
    ]
    notes = render_changelog("v1.2.3", commits, date=dt.date(2024, 1, 2))
    assert "## v1.2.3 - 2024-01-02" in notes
    assert "### 🚀 Features" in notes and "ingest: Add kafka source" in notes
    assert "### 🐛 Fixes" in notes and "Handle reconnects" in notes
    assert "### 📝 Documentation" in notes


def test_update_changelog_inserts_header(tmp_path: Path) -> None:
    entry = "## v0.1.0 - 2024-01-01\n\n### 🚀 Features\n- Initial release (abcdef0)\n"
    changelog = tmp_path / "CHANGELOG.md"
    update_changelog(changelog, entry)
    content = changelog.read_text(encoding="utf-8")
    assert content.startswith("# Changelog")
    assert entry.strip() in content

    # Ensure subsequent updates prepend new entries.
    next_entry = "## v0.2.0 - 2024-01-02\n\n### 🐛 Fixes\n- Patch bug (1234567)\n"
    update_changelog(changelog, next_entry)
    content = changelog.read_text(encoding="utf-8")
    lines = [line for line in content.splitlines() if line.strip()]
    assert lines[1].startswith("## v0.2.0")
