from __future__ import annotations

from datetime import date
from pathlib import Path

from scripts.docs.check_freshness import build_report


def _write_doc(path: Path, front_matter: str, body: str = "") -> None:
    content = f"---\n{front_matter}\n---\n\n{body}"
    path.write_text(content, encoding="utf-8")


def test_build_report_flags_stale_and_metadata(tmp_path: Path) -> None:
    stale_doc = tmp_path / "stale.md"
    fresh_doc = tmp_path / "fresh.md"
    missing_doc = tmp_path / "missing.md"

    _write_doc(
        stale_doc,
        "owner: docs@tradepulse\nreview_cadence: monthly\nlast_reviewed: 2025-10-01",
    )
    _write_doc(
        fresh_doc,
        "owner: docs@tradepulse\nreview_cadence: quarterly\nlast_reviewed: 2025-12-01",
    )
    missing_doc.write_text("# Missing front matter", encoding="utf-8")

    report = build_report([tmp_path], excludes=(), today=date(2025, 12, 28))

    stale_paths = {status.path.name for status in report.stale_documents}
    assert stale_paths == {"stale.md"}
    assert report.total_documents == 3
    assert report.evaluated_documents == 2

    issue_paths = {status.path.name for status in report.metadata_issues}
    assert "missing.md" in issue_paths
