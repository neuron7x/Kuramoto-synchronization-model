# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Negative-evidence preservation gate — behavioural tests.

Self-falsification proof for ``scripts/ci/check_tombstone_preservation.py``:
the gate must (1) pass on the real RIP/TOMBSTONES.md as shipped, (2) fail
when a tombstone references a deleted negative artifact, (3) fail when a
tombstone loses its 40-hex SHA anchor, (4) fail when a tombstone carries no
locatable artifact path, and (5) fail on an empty / structurally-broken
ledger.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "ci" / "check_tombstone_preservation.py"

_FULL_SHA = "9c8f539679a08e68c64cbc421907433a78e36b7a"  # pragma: allowlist secret (public git sha, not a credential)


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("check_tombstone_preservation", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_tombstone_preservation"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cc() -> Any:
    return _load_module()


def _entry(name: str, sha: str, artifact_rel: str) -> str:
    return (
        f"## {name} — synthetic dead hypothesis\n\n"
        f"- **NAME** · {name}\n"
        f"- **LINEAGE / PR** · PR #999 — `synthetic`\n"
        f"- **SHA** · `{sha}`\n"
        f"- **ARTIFACT** · `{artifact_rel}`\n"
        f"- **SUCCESS SCORE** · успіх: 0\n"
    )


# ---------------------------------------------------------------------------
# Live ledger — must pass on main
# ---------------------------------------------------------------------------


def test_live_tombstones_pass(cc: Any) -> None:
    """The shipped RIP/TOMBSTONES.md must keep every negative artifact
    preserved and every entry sha-anchored (exit 0)."""
    assert cc.main([]) == 0


def test_live_ledger_has_entries(cc: Any) -> None:
    text = (ROOT / "RIP" / "TOMBSTONES.md").read_text(encoding="utf-8")
    tombstones = cc._parse_tombstones(text)
    assert len(tombstones) >= 1
    assert all(t.has_sha for t in tombstones), "a live tombstone lost its SHA anchor"


# ---------------------------------------------------------------------------
# Synthetic ledgers — every fail-closed branch
# ---------------------------------------------------------------------------


def test_missing_artifact_fails(cc: Any, tmp_path: Path) -> None:
    """A tombstone pointing at a deleted artifact is a silent retraction."""
    led = tmp_path / "TOMB.md"
    led.write_text(_entry("X-1", _FULL_SHA, "research/gone/RESULTS.md"), encoding="utf-8")
    rc = cc.main(["--tombstones", str(led), "--root", str(tmp_path)])
    assert rc == 1


def test_present_artifact_passes(cc: Any, tmp_path: Path) -> None:
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "RESULTS.md").write_text("negative", encoding="utf-8")
    led = tmp_path / "TOMB.md"
    led.write_text(_entry("X-1", _FULL_SHA, "research/RESULTS.md"), encoding="utf-8")
    rc = cc.main(["--tombstones", str(led), "--root", str(tmp_path)])
    assert rc == 0


def test_missing_sha_anchor_fails(cc: Any, tmp_path: Path) -> None:
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "RESULTS.md").write_text("negative", encoding="utf-8")
    led = tmp_path / "TOMB.md"
    led.write_text(_entry("X-1", "9c8f5396", "research/RESULTS.md"), encoding="utf-8")  # short sha
    rc = cc.main(["--tombstones", str(led), "--root", str(tmp_path)])
    assert rc == 1


def test_no_artifact_path_fails(cc: Any, tmp_path: Path) -> None:
    led = tmp_path / "TOMB.md"
    led.write_text(
        f"## X-1 — synthetic\n\n- **NAME** · X-1\n- **SHA** · `{_FULL_SHA}`\n"
        f"- **ARTIFACT** · (none recorded)\n",
        encoding="utf-8",
    )
    rc = cc.main(["--tombstones", str(led), "--root", str(tmp_path)])
    assert rc == 1


def test_empty_ledger_fails(cc: Any, tmp_path: Path) -> None:
    led = tmp_path / "TOMB.md"
    led.write_text("# TOMBSTONES\n\nNo entries yet.\n", encoding="utf-8")
    rc = cc.main(["--tombstones", str(led), "--root", str(tmp_path)])
    assert rc == 1
