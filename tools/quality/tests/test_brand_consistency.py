# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for :mod:`tools.quality.brand_consistency`.

The guard must be trustworthy — if it misses a legacy token we regress
silently, and if it over-matches it blocks every PR. These tests pin
every failure mode the scanner is expected to handle.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.quality.brand_consistency import (
    AllowlistEntry,
    Violation,
    load_allowlist,
    main,
    scan_repo,
)

# ---------------------------------------------------------------------------
# Fixtures — build a fake repo on tmp_path
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    """Synthetic repo layout exercising every match kind + skip rule."""
    # Clean file — must not trigger anything
    (tmp_path / "clean.py").write_text(
        "def hello() -> str:\n    return 'GeoSync rules'\n", encoding="utf-8"
    )

    # Content match on a Python file
    (tmp_path / "legacy_content.py").write_text(
        "# Legacy docstring\n'''Port of the old TradePulse engine.'''\n",
        encoding="utf-8",
    )

    # Content match on a Markdown file
    (tmp_path / "NOTES.md").write_text(
        "## Notes\n\nSee the original NeuroTrade Pro paper.\n",
        encoding="utf-8",
    )

    # Filename match
    (tmp_path / "legacy_trade_pulse_runner.py").write_text("x = 1\n", encoding="utf-8")

    # Directory name match
    (tmp_path / "hydrobrain_module").mkdir()
    (tmp_path / "hydrobrain_module" / "__init__.py").write_text("", encoding="utf-8")

    # Skipped directories — should not produce matches even though they
    # contain legacy tokens in names and content
    skip_dirs = [".git", ".venv", "node_modules", "__pycache__", "legacy"]
    for name in skip_dirs:
        d = tmp_path / name
        d.mkdir()
        (d / "TradePulseDaemon.py").write_text("tradepulse = True\n", encoding="utf-8")

    # Binary-looking file — should be skipped on content scan
    (tmp_path / "data.bin").write_bytes(b"\x00\x01\x02TradePulse\x03\x04")

    # Oversize file — should be skipped (write 1.5 MB of plain text)
    (tmp_path / "huge.txt").write_text("x" * (1_600_000), encoding="utf-8")

    # Substring matching catches NeuroProductivity — that is the expected
    # behaviour and is handled via the allowlist (tested separately).
    (tmp_path / "word_boundary.py").write_text(
        "# NeuroProductivity is a real word, allowlist it if it appears\n",
        encoding="utf-8",
    )

    # Case-insensitive hit
    (tmp_path / "mixed_case.py").write_text("# tradePULSE legacy\n", encoding="utf-8")

    return tmp_path


# ---------------------------------------------------------------------------
# Core scanner behaviour
# ---------------------------------------------------------------------------


class TestScanRepo:
    def test_content_match_detected(self, fake_repo: Path) -> None:
        report = scan_repo(fake_repo)
        paths = {v.path for v in report.violations if v.kind == "content"}
        assert "legacy_content.py" in paths
        assert "NOTES.md" in paths

    def test_filename_match_detected(self, fake_repo: Path) -> None:
        report = scan_repo(fake_repo)
        names = {v.path for v in report.violations if v.kind == "filename"}
        assert any("legacy_trade_pulse_runner" in n for n in names)

    def test_dirname_match_detected(self, fake_repo: Path) -> None:
        report = scan_repo(fake_repo)
        # The directory itself reports; files inside it also pick up the
        # directory prefix in their path but we care about the directory
        # kind entry.
        dir_hits = [v for v in report.violations if v.kind == "dirname"]
        assert any("hydrobrain_module" in v.path for v in dir_hits)

    def test_skip_dirs_respected(self, fake_repo: Path) -> None:
        report = scan_repo(fake_repo)
        for v in report.violations:
            assert not v.path.startswith(".git/")
            assert not v.path.startswith(".venv/")
            assert not v.path.startswith("node_modules/")
            assert not v.path.startswith("__pycache__/")
            assert not v.path.startswith("legacy/")

    def test_binary_file_not_scanned(self, fake_repo: Path) -> None:
        report = scan_repo(fake_repo)
        assert not any(v.path == "data.bin" for v in report.violations)

    def test_oversize_file_skipped(self, fake_repo: Path) -> None:
        report = scan_repo(fake_repo)
        # huge.txt contains no legacy tokens, but we assert the scanner
        # did not blow up on its 1.5 MB payload (it should be skipped
        # before read)
        assert not any(v.path == "huge.txt" for v in report.violations)

    def test_substring_matching_catches_compound_snake_case(self, fake_repo: Path) -> None:
        """``trade_pulse`` must match inside ``legacy_trade_pulse_runner``.

        Word-boundary regex would miss compound snake_case because
        underscore is a word character. Substring matching catches it,
        which is the correct behaviour for legacy token hunting.
        """
        report = scan_repo(fake_repo)
        assert any("legacy_trade_pulse_runner" in v.path for v in report.violations)

    def test_substring_matching_flags_neuroproductivity_false_positive(
        self, fake_repo: Path
    ) -> None:
        """Substring matching over-flags legitimate words; allowlist handles them.

        ``NeuroProductivity`` contains ``NeuroPro`` as a substring and is
        therefore reported. The intended workflow is to add an allowlist
        entry if the word is a genuine false positive.
        """
        report = scan_repo(fake_repo)
        assert any(v.path == "word_boundary.py" for v in report.violations)
        # Allowlist suppresses it:
        allow = [
            AllowlistEntry(
                path="word_boundary.py",
                token="NeuroPro",
                reason="NeuroProductivity is a real English word",
            )
        ]
        clean_report = scan_repo(fake_repo, allowlist=allow)
        assert not any(v.path == "word_boundary.py" for v in clean_report.violations)

    def test_case_insensitive_match(self, fake_repo: Path) -> None:
        report = scan_repo(fake_repo)
        assert any(v.path == "mixed_case.py" for v in report.violations)

    def test_report_is_sorted(self, fake_repo: Path) -> None:
        report = scan_repo(fake_repo)
        assert report.violations == sorted(report.violations)

    def test_report_clean_flag(self, tmp_path: Path) -> None:
        """Empty repo → clean report."""
        report = scan_repo(tmp_path)
        assert report.clean is True
        assert report.violations == []


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------


class TestAllowlist:
    def test_empty_allowlist_when_file_missing(self, tmp_path: Path) -> None:
        assert load_allowlist(tmp_path / "missing.toml") == []

    def test_parses_valid_allowlist(self, tmp_path: Path) -> None:
        path = tmp_path / "allow.toml"
        path.write_text(
            '[[allow]]\npath = "X.md"\ntoken = "TradePulse"\nreason = "historical"\n',
            encoding="utf-8",
        )
        entries = load_allowlist(path)
        assert entries == [AllowlistEntry(path="X.md", token="TradePulse", reason="historical")]

    def test_rejects_missing_fields(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.toml"
        path.write_text('[[allow]]\npath = "X.md"\n', encoding="utf-8")
        with pytest.raises(ValueError, match="missing fields"):
            load_allowlist(path)

    def test_rejects_wrong_type(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.toml"
        path.write_text("allow = 'not-an-array'\n", encoding="utf-8")
        with pytest.raises(ValueError, match="must be an array"):
            load_allowlist(path)

    def test_allowlist_suppresses_matching_violation(self, tmp_path: Path) -> None:
        (tmp_path / "FOO.md").write_text("legacy: TradePulse\n", encoding="utf-8")
        allow = [AllowlistEntry(path="FOO.md", token="TradePulse", reason="test")]
        report = scan_repo(tmp_path, allowlist=allow)
        assert report.clean
        assert report.allowlist_hits == 1

    def test_allowlist_does_not_leak_across_paths(self, tmp_path: Path) -> None:
        (tmp_path / "A.md").write_text("TradePulse\n", encoding="utf-8")
        (tmp_path / "B.md").write_text("TradePulse\n", encoding="utf-8")
        allow = [AllowlistEntry(path="A.md", token="TradePulse", reason="test")]
        report = scan_repo(tmp_path, allowlist=allow)
        # A is suppressed; B is still a violation
        assert len(report.violations) == 1
        assert report.violations[0].path == "B.md"
        assert report.allowlist_hits == 1


# ---------------------------------------------------------------------------
# Violation dataclass invariants
# ---------------------------------------------------------------------------


class TestViolation:
    def test_total_ordering(self) -> None:
        a = Violation(path="a.py", line=1, column=1, token="t", kind="content")
        b = Violation(path="a.py", line=2, column=1, token="t", kind="content")
        c = Violation(path="b.py", line=1, column=1, token="t", kind="content")
        assert a < b < c

    def test_frozen(self) -> None:
        v = Violation(path="a.py", line=1, column=1, token="t", kind="content")
        with pytest.raises(AttributeError):
            v.path = "b.py"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_exit_zero_on_clean_repo(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main(["--root", str(tmp_path)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "clean" in out

    def test_exit_one_on_violation(
        self, fake_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main(["--root", str(fake_repo)])
        out = capsys.readouterr().out
        assert rc == 1
        assert "violation" in out

    def test_json_output_is_stable(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "hit.md").write_text("TradePulse here\n", encoding="utf-8")
        rc = main(["--root", str(tmp_path), "--json"])
        out = capsys.readouterr().out
        assert rc == 1
        payload = json.loads(out)
        assert payload["clean"] is False
        assert payload["violations"][0]["path"] == "hit.md"
        assert payload["violations"][0]["token"] == "TradePulse"
        assert payload["scanned_files"] == 1

    def test_exit_two_on_bad_allowlist(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        bad = tmp_path / "bad.toml"
        bad.write_text('[[allow]]\npath = "X"\n', encoding="utf-8")
        rc = main(["--root", str(tmp_path), "--allowlist", str(bad)])
        assert rc == 2


# ---------------------------------------------------------------------------
# End-to-end: the real repo must be clean
# ---------------------------------------------------------------------------


class TestRepoClean:
    def test_current_repo_has_no_legacy_brand_tokens(self) -> None:
        """The GeoSync repo root must be clean under the default allowlist.

        This is the canary test that proves the rename + docstring
        cleanup landed before the brand-consistency guard was enabled
        in CI.
        """
        # Discover repo root by walking up from this test file until we
        # see a .git directory.
        candidate = Path(__file__).resolve()
        for parent in candidate.parents:
            if (parent / ".git").is_dir():
                repo_root = parent
                break
        else:  # pragma: no cover — test layout changed
            pytest.skip("repo root not found (tests run outside git worktree)")

        allowlist = load_allowlist(repo_root / "configs" / "quality" / "brand_allowlist.toml")
        report = scan_repo(repo_root, allowlist=allowlist)
        if not report.clean:
            details = "\n".join(
                f"  {v.path}:{v.line}:{v.column} [{v.kind}] {v.token!r} — {v.context}"
                for v in report.violations[:20]
            )
            pytest.fail(f"Repo has {len(report.violations)} legacy brand token(s):\n{details}")
