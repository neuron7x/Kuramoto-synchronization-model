# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Generate Conventional Commit release notes for GeoSync."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import re
import subprocess
from pathlib import Path
from typing import Dict, Iterable, Sequence

CATEGORY_TITLES = {
    "feat": "🚀 Features",
    "fix": "🐛 Fixes",
    "perf": "⚡ Performance",
    "refactor": "🧹 Maintenance",
    "docs": "📝 Documentation",
    "test": "✅ Tests",
    "ci": "🤖 CI",
    "build": "📦 Build",
    "chore": "🧰 Chores",
    "other": "🔧 Other",
}

TYPE_TO_CATEGORY = {
    "feat": "feat",
    "feature": "feat",
    "fix": "fix",
    "bug": "fix",
    "hotfix": "fix",
    "perf": "perf",
    "refactor": "refactor",
    "style": "refactor",
    "docs": "docs",
    "doc": "docs",
    "test": "test",
    "tests": "test",
    "ci": "ci",
    "build": "build",
    "deps": "build",
    "chore": "chore",
    "revert": "chore",
}

COMMIT_PATTERN = re.compile(
    r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?: (?P<subject>.+)$"
)


@dataclasses.dataclass(slots=True)
class CommitInfo:
    sha: str
    type: str
    scope: str | None
    subject: str
    breaking: bool
    notes: list[str]

    @property
    def category(self) -> str:
        return TYPE_TO_CATEGORY.get(self.type.lower(), "other")

    @property
    def display_subject(self) -> str:
        if self.scope:
            return f"{self.scope}: {self.subject}"
        return self.subject


def run_git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def collect_commits(current: str, previous: str | None = None) -> list[CommitInfo]:
    if previous:
        rev_range = f"{previous}..{current}"
    else:
        rev_range = current
    shas = run_git("rev-list", "--reverse", rev_range).splitlines()
    commits: list[CommitInfo] = []
    for sha in shas:
        if not sha:
            continue
        raw = run_git("show", "-s", "--format=%s%n%b", sha)
        subject, _, body = raw.partition("\n")
        match = COMMIT_PATTERN.match(subject)
        if match:
            commit_type = match.group("type")
            scope = match.group("scope")
            breaking = bool(match.group("breaking"))
            message = match.group("subject").strip()
        else:
            commit_type = "other"
            scope = None
            breaking = False
            message = subject.strip()
        notes: list[str] = []
        for line in body.splitlines():
            cleaned = line.strip()
            if cleaned.lower().startswith("breaking change"):
                breaking = True
                _, _, note = cleaned.partition(":")
                if note:
                    notes.append(note.strip())
        commits.append(
            CommitInfo(
                sha=sha,
                type=commit_type,
                scope=scope,
                subject=message,
                breaking=breaking,
                notes=notes,
            )
        )
    return commits


def group_commits(commits: Iterable[CommitInfo]) -> Dict[str, list[CommitInfo]]:
    grouped: Dict[str, list[CommitInfo]] = {key: [] for key in CATEGORY_TITLES}
    for commit in commits:
        grouped.setdefault(commit.category, []).append(commit)
    return grouped


def render_section(title: str, commits: Sequence[CommitInfo]) -> str:
    if not commits:
        return ""
    lines = [f"### {title}"]
    for commit in commits:
        entry = f"- {commit.display_subject} ({commit.sha[:7]})"
        if commit.notes:
            note_text = "; ".join(commit.notes)
            entry += f" — BREAKING: {note_text}"
        lines.append(entry)
    return "\n".join(lines)


def render_changelog(version: str, commits: list[CommitInfo], date: dt.date | None = None) -> str:
    date = date or dt.date.today()
    header = f"## {version} - {date.isoformat()}"
    grouped = group_commits(commits)
    sections = []
    for key in CATEGORY_TITLES:
        section = render_section(CATEGORY_TITLES[key], grouped.get(key, []))
        if section:
            sections.append(section)
    if not sections:
        sections.append("### 🔧 Other\n- No Conventional Commits found in this range.")
    body = "\n\n".join(sections)
    return f"{header}\n\n{body}\n"


def update_changelog(path: Path, new_entry: str) -> None:
    new_entry = new_entry.strip() + "\n"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
    else:
        existing = "# Changelog\n\n"
    if not existing.startswith("# Changelog"):
        existing = "# Changelog\n\n" + existing
    if new_entry.strip() in existing:
        return
    header, _, rest = existing.partition("\n")
    rest = rest.lstrip("\n")
    combined = header + "\n\n" + new_entry + "\n" + rest
    path.write_text(combined, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a Conventional Commit changelog entry.")
    parser.add_argument("--current-tag", required=True, help="Tag that marks the release.")
    parser.add_argument("--previous-tag", help="Previous tag to diff against.")
    parser.add_argument(
        "--output", type=Path, required=True, help="Where to write the release notes."
    )
    parser.add_argument(
        "--changelog", type=Path, help="Optional path to update CHANGELOG.md in place."
    )
    args = parser.parse_args()

    commits = collect_commits(args.current_tag, args.previous_tag)
    notes = render_changelog(args.current_tag, commits)
    args.output.write_text(notes, encoding="utf-8")

    if args.changelog is not None:
        update_changelog(args.changelog, notes)


if __name__ == "__main__":
    main()
