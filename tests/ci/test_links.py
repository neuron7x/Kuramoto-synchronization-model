# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contract tests for the Markdown link-integrity gate (scripts/ci/check_links.py).

POSITIVE : the real repository passes — zero broken internal links -> exit 0.
NEGATIVE : a fixture tree with a broken relative link, and one with an
           un-allowlisted outside-root link, are both flagged (exit 1); and an
           allowlisted outside-root link passes.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "ci" / "check_links.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_links", CHECKER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


check_links = _load_checker()


# --------------------------------------------------------------------------
# POSITIVE — the real repo is clean.
# --------------------------------------------------------------------------

def test_repo_has_zero_broken_internal_links() -> None:
    report = check_links.scan(REPO_ROOT)
    assert report["internal_broken_total"] == 0, report["broken"]
    assert report["outside_root_unallowed_total"] == 0, report["outside_root_unallowed"]


def test_repo_checker_exit_code_zero() -> None:
    rc = check_links.main(["--root", str(REPO_ROOT), "--quiet"])
    assert rc == 0


# --------------------------------------------------------------------------
# NEGATIVE — fixtures that must be flagged.
# --------------------------------------------------------------------------

def test_broken_relative_link_is_flagged(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text("See [x](./nope.md) for details.\n", encoding="utf-8")
    report = check_links.scan(tmp_path)
    assert report["internal_broken_total"] == 1
    assert report["broken"][0]["target"] == "./nope.md"
    rc = check_links.main(["--root", str(tmp_path), "--quiet"])
    assert rc == 1


def test_outside_root_link_not_allowlisted_is_flagged(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text("Leak [y](../../etc/passwd) here.\n", encoding="utf-8")
    report = check_links.scan(tmp_path)
    assert report["internal_broken_total"] == 0
    assert report["outside_root_unallowed_total"] == 1
    assert report["outside_root_unallowed"][0]["target"] == "../../etc/passwd"
    rc = check_links.main(["--root", str(tmp_path), "--quiet"])
    assert rc == 1


def test_outside_root_link_allowlisted_passes(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text("Allowed [y](../../etc/passwd) here.\n", encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "link_allowlist.json").write_text(
        json.dumps(
            {
                "outside_root_allowlist": [
                    {"file": "doc.md", "target": "../../etc/passwd", "reason": "test fixture"}
                ]
            }
        ),
        encoding="utf-8",
    )
    report = check_links.scan(tmp_path)
    assert report["outside_root_unallowed_total"] == 0
    assert report["counts"]["outside_root_allowlisted"] == 1
    rc = check_links.main(["--root", str(tmp_path), "--quiet"])
    assert rc == 0


def test_external_and_anchor_links_are_not_broken(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text(
        "[a](https://example.com) [b](#section) [c](mailto:x@y.z)\n", encoding="utf-8"
    )
    report = check_links.scan(tmp_path)
    assert report["internal_broken_total"] == 0
    assert report["counts"]["external"] == 2
    assert report["counts"]["anchor"] == 1


def test_code_fence_links_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text(
        "```\n[x](./nope.md)\n```\nreal `[y](./also-nope.md)` inline-code\n", encoding="utf-8"
    )
    report = check_links.scan(tmp_path)
    assert report["internal_broken_total"] == 0
