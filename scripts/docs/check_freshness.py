"""Check documentation freshness based on YAML front matter metadata."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import yaml

CADENCE_DAYS = {
    "monthly": 30,
    "quarterly": 90,
    "semiannual": 182,
    "annual": 365,
    "annually": 365,
    "per-release": None,
    "as-needed": None,
}

DEFAULT_EXCLUDES = (
    ".git",
    "node_modules",
    "dist",
    "build",
    "docs/assets",
)

DEFAULT_PATHS = ("docs", "README.md", "DOCUMENTATION_SUMMARY.md")


class FreshnessError(Exception):
    """Raised when front matter cannot be parsed."""


@dataclass(frozen=True)
class DocumentStatus:
    path: Path
    owner: str | None
    review_cadence: str | None
    last_reviewed: date | None
    cadence_days: int | None
    errors: tuple[str, ...]

    def is_stale(self, today: date) -> bool:
        if self.cadence_days is None or self.last_reviewed is None:
            return False
        return today > self.last_reviewed + timedelta(days=self.cadence_days)

    def days_overdue(self, today: date) -> int | None:
        if self.cadence_days is None or self.last_reviewed is None:
            return None
        due = self.last_reviewed + timedelta(days=self.cadence_days)
        if today <= due:
            return 0
        return (today - due).days

    def due_date(self) -> date | None:
        if self.cadence_days is None or self.last_reviewed is None:
            return None
        return self.last_reviewed + timedelta(days=self.cadence_days)


@dataclass(frozen=True)
class FreshnessReport:
    total_documents: int
    evaluated_documents: int
    stale_documents: tuple[DocumentStatus, ...]
    metadata_issues: tuple[DocumentStatus, ...]


def _split_front_matter(text: str) -> Mapping[str, object]:
    lines = text.splitlines()
    if not lines:
        return {}
    if lines[0].strip() != "---":
        return {}
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            yaml_text = "\n".join(lines[1:idx])
            try:
                data = yaml.safe_load(yaml_text) or {}
            except yaml.YAMLError as exc:
                raise FreshnessError("invalid YAML front matter") from exc
            if not isinstance(data, Mapping):
                raise FreshnessError("front matter must be a mapping")
            return data
    raise FreshnessError("unterminated YAML front matter")


def _normalise_owner(raw: object) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        value = raw.strip()
        return value or None
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        owners = [str(item).strip() for item in raw if str(item).strip()]
        if owners:
            return ", ".join(owners)
        return None
    return None


def _parse_review_cadence(raw: object) -> tuple[str | None, int | None, str | None]:
    if raw is None:
        return None, None, "missing review_cadence"
    if not isinstance(raw, str):
        return None, None, "review_cadence must be a string"
    value = raw.strip().lower()
    if not value:
        return None, None, "review_cadence must be non-empty"
    if value not in CADENCE_DAYS:
        return value, None, f"unsupported review_cadence '{value}'"
    return value, CADENCE_DAYS[value], None


def _parse_last_reviewed(raw: object) -> tuple[date | None, str | None]:
    if raw is None:
        return None, "missing last_reviewed"
    if isinstance(raw, datetime):
        return raw.date(), None
    if isinstance(raw, date):
        return raw, None
    if not isinstance(raw, str):
        return None, "last_reviewed must be YYYY-MM-DD"
    value = raw.strip()
    if not value:
        return None, "last_reviewed must be non-empty"
    try:
        return datetime.strptime(value, "%Y-%m-%d").date(), None
    except ValueError:
        return None, "last_reviewed must be YYYY-MM-DD"


def _document_status(path: Path) -> DocumentStatus:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    front_matter = _split_front_matter(text)

    if not front_matter:
        errors.append("missing YAML front matter")
        return DocumentStatus(path, None, None, None, None, tuple(errors))

    owner = _normalise_owner(front_matter.get("owner"))
    if owner is None:
        errors.append("missing owner")

    review_cadence, cadence_days, cadence_error = _parse_review_cadence(
        front_matter.get("review_cadence")
    )
    if cadence_error:
        errors.append(cadence_error)

    last_reviewed, last_error = _parse_last_reviewed(front_matter.get("last_reviewed"))
    if last_error:
        errors.append(last_error)

    return DocumentStatus(
        path=path,
        owner=owner,
        review_cadence=review_cadence,
        last_reviewed=last_reviewed,
        cadence_days=cadence_days,
        errors=tuple(errors),
    )


def _iter_markdown_files(paths: Sequence[Path], excludes: Sequence[str]) -> Iterable[Path]:
    exclude_patterns = {pattern.strip() for pattern in excludes if pattern.strip()}
    for path in paths:
        if not path.exists():
            continue
        if path.is_file():
            if path.suffix.lower() in {".md", ".markdown", ".mdx"}:
                if _is_excluded(path, exclude_patterns):
                    continue
                yield path
            continue
        for file_path in path.rglob("*"):
            if file_path.is_dir():
                continue
            if file_path.suffix.lower() not in {".md", ".markdown", ".mdx"}:
                continue
            if _is_excluded(file_path, exclude_patterns):
                continue
            yield file_path


def _is_excluded(path: Path, exclude_patterns: set[str]) -> bool:
    path_str = path.as_posix()
    for pattern in exclude_patterns:
        if path_str == pattern:
            return True
        if path_str.startswith(pattern.rstrip("/") + "/"):
            return True
    return False


def build_report(paths: Sequence[Path], excludes: Sequence[str], today: date) -> FreshnessReport:
    statuses = [_document_status(path) for path in _iter_markdown_files(paths, excludes)]
    stale = [status for status in statuses if status.is_stale(today)]
    metadata_issues = [status for status in statuses if status.errors]
    evaluated = [status for status in statuses if status.cadence_days is not None]
    return FreshnessReport(
        total_documents=len(statuses),
        evaluated_documents=len(evaluated),
        stale_documents=tuple(sorted(stale, key=lambda status: status.path.as_posix())),
        metadata_issues=tuple(sorted(metadata_issues, key=lambda status: status.path.as_posix())),
    )


def _markdown_report(report: FreshnessReport, today: date) -> str:
    lines = [
        "# Documentation Freshness Report",
        "",
        f"Generated: {today.isoformat()}",
        "",
        "## Summary",
        "",
        f"- Total documents scanned: {report.total_documents}",
        f"- Documents evaluated for freshness: {report.evaluated_documents}",
        f"- Stale documents: {len(report.stale_documents)}",
        f"- Documents with metadata issues: {len(report.metadata_issues)}",
        "",
        "## Stale Documents",
        "",
    ]

    if report.stale_documents:
        lines.extend(
            [
                "| Document | Owner | Review cadence | Last reviewed | Due | Days overdue |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for status in report.stale_documents:
            due_date = status.due_date()
            overdue = status.days_overdue(today)
            lines.append(
                "| {path} | {owner} | {cadence} | {last} | {due} | {overdue} |".format(
                    path=status.path.as_posix(),
                    owner=status.owner or "—",
                    cadence=status.review_cadence or "—",
                    last=status.last_reviewed.isoformat() if status.last_reviewed else "—",
                    due=due_date.isoformat() if due_date else "—",
                    overdue=str(overdue) if overdue is not None else "—",
                )
            )
    else:
        lines.append("✅ No stale documents detected.")

    lines.extend(["", "## Metadata Issues", ""])

    if report.metadata_issues:
        lines.extend(["| Document | Issues |", "| --- | --- |"])
        for status in report.metadata_issues:
            issues = "; ".join(status.errors) if status.errors else "—"
            lines.append(f"| {status.path.as_posix()} | {issues} |")
    else:
        lines.append("✅ No metadata issues detected.")

    return "\n".join(lines) + "\n"


def _json_report(report: FreshnessReport, today: date) -> str:
    payload = {
        "generated": today.isoformat(),
        "total_documents": report.total_documents,
        "evaluated_documents": report.evaluated_documents,
        "stale_documents": [
            {
                "path": status.path.as_posix(),
                "owner": status.owner,
                "review_cadence": status.review_cadence,
                "last_reviewed": status.last_reviewed.isoformat()
                if status.last_reviewed
                else None,
                "due": status.due_date().isoformat() if status.due_date() else None,
                "days_overdue": status.days_overdue(today),
            }
            for status in report.stale_documents
        ],
        "metadata_issues": [
            {"path": status.path.as_posix(), "issues": status.errors}
            for status in report.metadata_issues
        ],
    }
    return json.dumps(payload, indent=2) + "\n"


def _render_report(report: FreshnessReport, today: date, fmt: str) -> str:
    if fmt == "json":
        return _json_report(report, today)
    return _markdown_report(report, today)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--paths",
        nargs="+",
        default=list(DEFAULT_PATHS),
        help="Files or directories to scan.",
    )
    parser.add_argument(
        "--exclude",
        nargs="+",
        default=list(DEFAULT_EXCLUDES),
        help="Path prefixes to exclude from scanning.",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Report output format.",
    )
    parser.add_argument(
        "--output",
        help="Write report to a file path instead of stdout.",
    )
    parser.add_argument(
        "--today",
        help="Override today's date (YYYY-MM-DD). Useful for tests.",
    )
    parser.add_argument(
        "--fail-on-stale",
        action="store_true",
        help="Exit non-zero if stale documents are found.",
    )
    parser.add_argument(
        "--fail-on-metadata",
        action="store_true",
        help="Exit non-zero if metadata issues are found.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    today = date.today()
    if args.today:
        today = datetime.strptime(args.today, "%Y-%m-%d").date()

    paths = [Path(path) for path in args.paths]
    report = build_report(paths, args.exclude, today)
    output = _render_report(report, today, args.format)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output, end="")

    if args.fail_on_stale and report.stale_documents:
        return 2
    if args.fail_on_metadata and report.metadata_issues:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
