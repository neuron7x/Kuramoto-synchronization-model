# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for the documentation linting helper."""

from __future__ import annotations

from pathlib import Path

import tools.docs.lint_docs as lint_docs
from tools.docs.lint_docs import (
    DEFAULT_RULES,
    ForbiddenPhraseRule,
    HeadingFirstRule,
    LintIssue,
    lint_paths,
)


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_heading_rule_accepts_front_matter(tmp_path: Path) -> None:
    document = """---\nowner: docs\n---\n\n# Title\n\nBody\n"""
    path = _write(tmp_path, "doc.md", document)

    issues = list(HeadingFirstRule().check(path, document.splitlines()))

    assert issues == []


def test_heading_rule_flags_missing_h1(tmp_path: Path) -> None:
    document = "Intro without heading\n"
    path = _write(tmp_path, "missing.md", document)

    issues = list(HeadingFirstRule().check(path, document.splitlines()))

    assert len(issues) == 1
    assert issues[0].message == "first content line must be a level-1 heading"


def test_heading_rule_flags_empty_document(tmp_path: Path) -> None:
    document = ""
    path = _write(tmp_path, "empty.md", document)

    issues = list(HeadingFirstRule().check(path, document.splitlines()))

    assert len(issues) == 1
    assert issues[0].line == 1
    assert issues[0].message == "first content line must be a level-1 heading"


def test_heading_rule_accepts_html_comment(tmp_path: Path) -> None:
    document = "<!-- AUTO-GENERATED FILE. DO NOT EDIT. -->\n# Title\n\nBody\n"
    path = _write(tmp_path, "generated.md", document)

    issues = list(HeadingFirstRule().check(path, document.splitlines()))

    assert issues == []


def test_heading_rule_accepts_multiline_html_comment(tmp_path: Path) -> None:
    document = "<!--\nAUTO-GENERATED FILE.\nDO NOT EDIT.\n-->\n# Title\n\nBody\n"
    path = _write(tmp_path, "multiline.md", document)

    issues = list(HeadingFirstRule().check(path, document.splitlines()))

    assert issues == []


def test_heading_rule_with_comment_and_empty_lines(tmp_path: Path) -> None:
    document = "<!-- Comment -->\n\n\n# Title\n\nBody\n"
    path = _write(tmp_path, "spaces.md", document)

    issues = list(HeadingFirstRule().check(path, document.splitlines()))

    assert issues == []


def test_forbidden_phrase_detection(tmp_path: Path) -> None:
    document = "# Title\n\nThis contains a TODO item.\n"
    path = _write(tmp_path, "todo.md", document)

    issues = list(ForbiddenPhraseRule().check(path, document.splitlines()))

    assert len(issues) == 1
    assert "TODO" in issues[0].message


def test_forbidden_phrase_ignored_in_code(tmp_path: Path) -> None:
    document = (
        """# Title\n\n`reports/todo.md` should not alert.\n\n```python\n# TODO: sample\n```\n"""
    )
    path = _write(tmp_path, "code.md", document)

    issues = list(ForbiddenPhraseRule().check(path, document.splitlines()))

    assert issues == []


def test_lint_paths_aggregates_all_rules(tmp_path: Path) -> None:
    markdown = "# Title\t\nLine with trailing space \n"
    path = _write(tmp_path, "sample.md", markdown)

    results = lint_paths([tmp_path], rules=DEFAULT_RULES)

    assert {issue.rule for issue in results} == {"no-tabs", "trailing-whitespace"}
    assert all(issue.path == path for issue in results)


def test_format_outputs_relative_path(tmp_path: Path) -> None:
    path = _write(tmp_path, "doc.md", "# Title\n")
    issue = LintIssue(path=path, line=2, message="msg", rule="rule")

    formatted = issue.format(root=tmp_path)

    assert formatted.startswith("doc.md:")
    assert formatted.endswith("[rule]")


def test_lint_paths_skips_non_markdown(tmp_path: Path) -> None:
    _write(tmp_path, "document.txt", "plain text\n")
    _write(tmp_path, "document.md", "# Heading\n")

    issues = lint_paths([tmp_path])

    assert issues == []


def test_lint_paths_skips_node_modules_directory(tmp_path: Path) -> None:
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()

    _write(node_modules, "ignored.md", "# Title\t\nTrailing whitespace \n")

    issues = lint_paths([tmp_path])

    assert issues == []


def test_cli_allows_missing_paths(monkeypatch, capsys, tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"

    exit_code = lint_docs.main(["--allow-missing", str(missing)])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "No valid documentation paths supplied" in captured.out
