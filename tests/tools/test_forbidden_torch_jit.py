# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the forbidden torch JIT / deserialization gate.

Covers:
  * positive — every forbidden API form (direct, aliased import, from-import)
    is detected;
  * conditional — ``torch.load`` is permitted only with literal
    ``weights_only=True`` and forbidden otherwise;
  * negative — clean code (incl. comments/strings naming the symbols) passes;
  * allowlist — schema validation and exact path::line::api exemption;
  * repo-wide — the real repository scans to ZERO unreviewed findings.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.security import check_forbidden_torch_jit as gate

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Positive: forbidden calls are detected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, expected_api",
    [
        ("import torch\nm = torch.jit.script(f)\n", "torch.jit.script"),
        ("import torch\nm = torch.jit.trace(f, x)\n", "torch.jit.trace"),
        ("import torch\nm = torch.jit.load('a.pt')\n", "torch.jit.load"),
        ("import torch\nm = torch.load('a.pt')\n", "torch.load"),
        ("import torch\nm = torch.load('a.pt', weights_only=False)\n", "torch.load"),
    ],
)
def test_forbidden_direct_calls_detected(source: str, expected_api: str) -> None:
    findings = gate.scan_source(source, "fixture.py")
    assert [f.api for f in findings] == [expected_api]
    assert findings[0].line == 2


def test_aliased_jit_import_detected() -> None:
    source = "import torch.jit as J\nm = J.script(f)\n"
    findings = gate.scan_source(source, "fixture.py")
    assert [f.api for f in findings] == ["torch.jit.script"]


def test_from_import_load_alias_detected() -> None:
    source = "from torch import load as tl\nm = tl('a.pt')\n"
    findings = gate.scan_source(source, "fixture.py")
    assert [f.api for f in findings] == ["torch.load"]


def test_from_jit_import_script_alias_detected() -> None:
    source = "from torch.jit import script as compile_ts\nm = compile_ts(f)\n"
    findings = gate.scan_source(source, "fixture.py")
    assert [f.api for f in findings] == ["torch.jit.script"]


def test_non_literal_weights_only_is_unguarded() -> None:
    source = "import torch\nflag = True\nm = torch.load('a.pt', weights_only=flag)\n"
    findings = gate.scan_source(source, "fixture.py")
    assert [f.api for f in findings] == ["torch.load"]


# ---------------------------------------------------------------------------
# Negative: clean code passes
# ---------------------------------------------------------------------------


def test_guarded_load_is_clean() -> None:
    source = "import torch\nm = torch.load('a.pt', map_location='cpu', weights_only=True)\n"
    assert gate.scan_source(source, "fixture.py") == []


def test_comments_and_strings_are_not_flagged() -> None:
    source = (
        "import torch\n"
        "# torch.jit.script is forbidden here\n"
        "doc = 'do not call torch.load without weights_only'\n"
        "m = torch.load('a.pt', weights_only=True)\n"
    )
    assert gate.scan_source(source, "fixture.py") == []


def test_unrelated_load_call_not_flagged() -> None:
    source = "import json\nm = json.load(open('a.json'))\n"
    assert gate.scan_source(source, "fixture.py") == []


# ---------------------------------------------------------------------------
# Allowlist behaviour
# ---------------------------------------------------------------------------


def test_allowlist_exempts_exact_location(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    src = repo / "mod.py"
    src.write_text("import torch\nm = torch.load('a.pt')\n", encoding="utf-8")

    # No allowlist -> one unreviewed finding.
    unreviewed, allowed = gate.scan_repo(repo, [])
    assert len(unreviewed) == 1 and not allowed

    entry = gate.AllowlistEntry(
        path="mod.py", line=2, api="torch.load", reason="legacy guarded loader"
    )
    unreviewed, allowed = gate.scan_repo(repo, [entry])
    assert not unreviewed and len(allowed) == 1


def test_allowlist_rejects_empty_reason(tmp_path: Path) -> None:
    p = tmp_path / "al.json"
    p.write_text(
        json.dumps({"entries": [{"path": "m.py", "line": 1, "api": "torch.load", "reason": "  "}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="reason"):
        gate.load_allowlist(p)


def test_allowlist_rejects_missing_entries_key(tmp_path: Path) -> None:
    p = tmp_path / "al.json"
    p.write_text(json.dumps({"foo": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="entries"):
        gate.load_allowlist(p)


def test_repo_allowlist_loads_clean() -> None:
    entries = gate.load_allowlist(REPO_ROOT / gate.DEFAULT_ALLOWLIST_RELPATH)
    assert entries == []


# ---------------------------------------------------------------------------
# Repo-wide: zero unreviewed findings on current main
# ---------------------------------------------------------------------------


def test_repo_wide_scan_has_zero_unreviewed_findings() -> None:
    allowlist = gate.load_allowlist(REPO_ROOT / gate.DEFAULT_ALLOWLIST_RELPATH)
    unreviewed, _allowed = gate.scan_repo(REPO_ROOT, allowlist)
    assert unreviewed == [], "unreviewed forbidden torch usage:\n" + "\n".join(
        f.render() for f in unreviewed
    )


def test_cli_main_exits_zero_on_clean_repo() -> None:
    assert gate.main(["--root", str(REPO_ROOT)]) == 0
