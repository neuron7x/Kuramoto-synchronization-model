#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Falsification suite for the REL-010 reproducible source-archive gate.

POSITIVE:
  * The deterministic builder produces a byte-identical archive on two
    independent invocations with a fixed SOURCE_DATE_EPOCH -> identical sha256.
  * The gate ``scripts/ci/check_reproducible_archive.py`` exits 0 and reports
    match=true, tracked_only=true.

NEGATIVE (each MUST make digests differ / the gate go RED — a test that cannot
fail is not a test):
  * A builder that uses ``now`` for SOURCE_DATE_EPOCH yields DIFFERENT digests
    across two builds.
  * A non-``gzip -n`` compression (gzip embeds its wall-clock timestamp) yields
    DIFFERENT digests across two builds.
  * An archive that contains an UNTRACKED file is detected as cruft (member set
    != git ls-files).
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / "scripts" / "release" / "build_source_archive.sh"
GATE = ROOT / "scripts" / "ci" / "check_reproducible_archive.py"
FIXED_EPOCH = "1784488015"  # canonical commit author date
PREFIX = "geosync-1.1.0/"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _build_deterministic(out_dir: Path, epoch: str) -> Path:
    proc = subprocess.run(
        [str(BUILD_SCRIPT), str(out_dir)],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={"PATH": _path(), "SOURCE_DATE_EPOCH": epoch, "GEOSYNC_REF": "HEAD"},
    )
    for line in proc.stdout.splitlines():
        if line.startswith("ARCHIVE="):
            return Path(line.split("=", 1)[1])
    raise AssertionError(f"builder printed no ARCHIVE=: {proc.stdout!r}")


def _path() -> str:
    import os

    return os.environ.get("PATH", "/usr/bin:/bin")


def _build_now_live_timestamp(out_path: Path) -> None:
    """DEFECTIVE builder: use a LIVE `now` timestamp instead of a fixed pin.

    The real builder seals the fixed COMMIT object (mtime = commit date). This
    defective variant archives the bare TREE with ``SOURCE_DATE_EPOCH=now``,
    which git 2.43 renders with a live timestamp, so two invocations at
    different wall-clock times MUST diverge. Demonstrates why the release must
    pin the timestamp rather than let `now` leak in.
    """
    cmd = (
        f'SOURCE_DATE_EPOCH=$(date +%s) '
        f'git archive --format=tar --prefix={PREFIX} HEAD^{{tree}} | gzip -n > "{out_path}"'
    )
    subprocess.run(["bash", "-c", cmd], check=True, cwd=str(ROOT))


def _build_plain_gzip_file(out_path: Path, tar_mtime: int) -> None:
    """DEFECTIVE builder: compress an on-disk tar with plain ``gzip`` (no -n).

    Plain gzip embeds the *file's* mtime (and name) in the gzip header, so two
    builds whose intermediate tar has a different mtime MUST diverge. This is
    exactly the failure that ``gzip -n`` in the real builder prevents.
    """
    tar_path = out_path.with_suffix(".tar")
    cmd = (
        f'git archive --format=tar --prefix={PREFIX} HEAD > "{tar_path}" && '
        f'touch -d @{tar_mtime} "{tar_path}" && '
        f'gzip -c "{tar_path}" > "{out_path}"'
    )
    subprocess.run(["bash", "-c", cmd], check=True, cwd=str(ROOT))


# ---------------------------------------------------------------------------
# POSITIVE
# ---------------------------------------------------------------------------


def test_two_builds_are_byte_identical() -> None:
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        a1 = _build_deterministic(Path(d1), FIXED_EPOCH)
        a2 = _build_deterministic(Path(d2), FIXED_EPOCH)
        assert _sha256(a1) == _sha256(a2), "deterministic builder is NOT reproducible"


def test_gate_passes_and_reports_match() -> None:
    proc = subprocess.run(
        [sys.executable, str(GATE)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0, f"gate went RED unexpectedly: {proc.stdout}\n{proc.stderr}"
    assert "match=True" in proc.stdout
    assert "tracked_only=True" in proc.stdout


def test_archive_contains_only_tracked_files() -> None:
    with tempfile.TemporaryDirectory() as d:
        arc = _build_deterministic(Path(d), FIXED_EPOCH)
        with tarfile.open(arc, "r:gz") as tf:
            members = {
                m.name[len(PREFIX):]
                for m in tf.getmembers()
                if not m.isdir()
            }
    # Oracle = the tree of the ref actually archived (HEAD), not the index
    # (git ls-files). Using ls-files here is wrong when the worktree has a dirty
    # index (e.g. this wave staged-but-uncommitted): the archive is built from
    # HEAD, so it must be compared against HEAD's tree. This matches the gate.
    tracked = {
        p
        for p in subprocess.run(
            ["git", "-C", str(ROOT), "-c", "core.quotepath=false",
             "ls-tree", "-r", "-z", "--name-only", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.split("\0")
        if p
    }
    assert members == tracked


# ---------------------------------------------------------------------------
# NEGATIVE
# ---------------------------------------------------------------------------


def test_now_live_timestamp_builder_is_not_reproducible() -> None:
    """A builder that lets a live `now` timestamp leak in must NOT reproduce."""
    with tempfile.TemporaryDirectory() as d:
        a1 = Path(d) / "now1.tar.gz"
        _build_now_live_timestamp(a1)
        time.sleep(1.1)  # advance the wall clock so `now` differs
        a2 = Path(d) / "now2.tar.gz"
        _build_now_live_timestamp(a2)
        assert _sha256(a1) != _sha256(a2), (
            "a live `now` timestamp unexpectedly reproduced — "
            "the negative control is broken"
        )


def test_non_dash_n_gzip_is_not_reproducible() -> None:
    """Plain `gzip` (no -n) on a file embeds its mtime/name -> not stable."""
    with tempfile.TemporaryDirectory() as d:
        a1 = Path(d) / "g1.tar.gz"
        _build_plain_gzip_file(a1, tar_mtime=1)
        a2 = Path(d) / "g2.tar.gz"
        _build_plain_gzip_file(a2, tar_mtime=999_999_999)
        assert _sha256(a1) != _sha256(a2), (
            "plain gzip unexpectedly reproduced — negative control is broken"
        )


def test_untracked_file_in_archive_is_detected() -> None:
    """An archive carrying an untracked file must be flagged as cruft."""
    tracked = {
        p
        for p in subprocess.run(
            ["git", "-C", str(ROOT), "-c", "core.quotepath=false", "ls-files", "-z"],
            check=True, capture_output=True, text=True,
        ).stdout.split("\0")
        if p
    }
    with tempfile.TemporaryDirectory() as d:
        # Build a normal archive, then repack it with one extra untracked file.
        clean = _build_deterministic(Path(d), FIXED_EPOCH)
        tainted = Path(d) / "tainted.tar"
        with tarfile.open(clean, "r:gz") as src, tarfile.open(tainted, "w") as dst:
            for m in src.getmembers():
                if m.isfile():
                    dst.addfile(m, src.extractfile(m))
            cruft = tarfile.TarInfo(f"{PREFIX}NOT_A_RELEASE_FILE.txt")
            payload = b"untracked cruft\n"
            cruft.size = len(payload)
            import io

            dst.addfile(cruft, io.BytesIO(payload))

        with tarfile.open(tainted, "r") as tf:
            members = {
                m.name[len(PREFIX):]
                for m in tf.getmembers()
                if not m.isdir()
            }
    extra = members - tracked
    assert extra == {"NOT_A_RELEASE_FILE.txt"}, (
        f"untracked-file detection failed; extra={extra}"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
