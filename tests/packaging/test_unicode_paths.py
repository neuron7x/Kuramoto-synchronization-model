# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Round-trip portability tests for non-ASCII (Unicode) tracked paths.

Audit finding #1. The repo tracks a Cyrillic-named document; ``git archive`` ->
zip is the release path. These tests prove, on Linux, that the exact filename
BYTES survive ``git archive`` -> ``zipfile`` extraction, that the name is
NFC-normalized, and that internal references to it resolve. A NEGATIVE test
pins the failure mode: a synthetic NFD-decomposed name must be rejected by the
NFC check, so the gate cannot silently pass a decomposed (macOS-style) path.
"""

from __future__ import annotations

import io
import subprocess
import unicodedata
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# The canonical tracked Cyrillic path (audit finding #1). Kept as a literal so a
# rename that breaks portability makes this suite fail loudly.
CANONICAL = "docs/operations/СТАН_РОЗВИТКУ_ПРОЄКТУ.md"


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args], cwd=str(ROOT), capture_output=True, check=True
    )


def _tracked_paths() -> list[str]:
    out = _git("-c", "core.quotePath=false", "ls-files", "-z").stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def _non_ascii(paths: list[str]) -> list[str]:
    return [p for p in paths if any(ord(c) > 0x7F for c in p)]


def _archive_zip() -> zipfile.ZipFile:
    data = _git("archive", "--format=zip", "HEAD").stdout
    return zipfile.ZipFile(io.BytesIO(data))


# --------------------------------------------------------------------------- #
# POSITIVE — the real tracked file survives the release archive round-trip.
# --------------------------------------------------------------------------- #


def test_canonical_is_tracked_and_on_disk() -> None:
    assert CANONICAL in _tracked_paths(), "canonical Cyrillic path not tracked"
    assert (ROOT / CANONICAL).exists(), "canonical Cyrillic path missing on disk"


def test_canonical_is_nfc_normalized() -> None:
    assert unicodedata.normalize("NFC", CANONICAL) == CANONICAL, (
        "canonical path is not NFC-normalized (decomposed name = portability bug)"
    )


def test_git_archive_zip_round_trip_byte_identical() -> None:
    """git archive -> zipfile extract reproduces the exact UTF-8 filename bytes."""
    target_bytes = CANONICAL.encode("utf-8")
    zf = _archive_zip()

    match = None
    for info in zf.infolist():
        if info.filename.encode("utf-8") == target_bytes:
            match = info
            break

    assert match is not None, "Cyrillic path absent from git archive zip"
    # The zip must advertise UTF-8 (general purpose bit 11) so any conformant
    # extractor decodes the name correctly; the '#U' rendering only appears in
    # legacy extractors that ignore this flag -- the archived bytes are correct.
    assert match.flag_bits & 0x800, "archive entry missing UTF-8 language flag"
    assert match.filename.encode("utf-8") == target_bytes, "filename byte drift"
    assert unicodedata.normalize("NFC", match.filename) == match.filename


def test_all_non_ascii_paths_survive_round_trip() -> None:
    tracked = _non_ascii(_tracked_paths())
    assert tracked, "expected at least one non-ASCII tracked path"
    zf = _archive_zip()
    arc_bytes = {i.filename.encode("utf-8") for i in zf.infolist() if i.flag_bits & 0x800}
    for p in tracked:
        assert p.encode("utf-8") in arc_bytes, f"{p!r} did not survive archive"
        assert unicodedata.normalize("NFC", p) == p, f"{p!r} is not NFC"


def test_internal_references_resolve() -> None:
    """Every tracked Markdown mention of a non-ASCII path points at a real file."""
    paths = _tracked_paths()
    targets = _non_ascii(paths)
    md_files = [p for p in paths if p.endswith(".md")]
    for target in targets:
        target_exists = (ROOT / target).exists()
        for md in md_files:
            try:
                text = (ROOT / md).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if target in text:
                assert target_exists, (
                    f"{md} references '{target}' but it does not resolve on disk"
                )


# --------------------------------------------------------------------------- #
# NEGATIVE — a synthetic NFD (decomposed) name must be rejected by the NFC test.
# --------------------------------------------------------------------------- #


def test_nfd_name_is_detected_as_non_nfc() -> None:
    """A decomposed name is byte-distinct from its NFC form and must be flagged."""
    # 'Й' = U+0419 (NFC, single code point) vs U+0418 + U+0306 (NFD).
    nfc_name = "docs/operations/ЙFILE.md"
    nfd_name = unicodedata.normalize("NFD", nfc_name)

    assert nfd_name != nfc_name, "sanity: NFD form must differ in bytes"
    assert nfd_name.encode("utf-8") != nfc_name.encode("utf-8")
    # The gate's core predicate: an NFD name fails the NFC equality check.
    assert unicodedata.normalize("NFC", nfd_name) != nfd_name, (
        "NFD name must NOT be treated as already-NFC (fail-closed)"
    )
    # And normalizing recovers the canonical form.
    assert unicodedata.normalize("NFC", nfd_name) == nfc_name


def test_gate_module_flags_synthetic_nfd(monkeypatch: pytest.MonkeyPatch) -> None:
    """The gate reports a violation when a tracked path is NFD-decomposed."""
    import importlib

    gate = importlib.import_module("scripts.ci.check_unicode_paths")

    nfd_path = unicodedata.normalize("NFD", "docs/operations/ЙSYNTH.md")
    assert unicodedata.normalize("NFC", nfd_path) != nfd_path  # is genuinely NFD

    # Feed the gate a synthetic tracked set containing the NFD path; stub the
    # archive to include its bytes so ONLY the NFC check can fire.
    monkeypatch.setattr(gate, "tracked_paths", lambda: [nfd_path])
    monkeypatch.setattr(gate, "archive_names", lambda: {nfd_path})
    monkeypatch.setattr(gate, "internal_reference_violations", lambda p, t: [])
    monkeypatch.setattr(gate.Path, "exists", lambda self: True)

    rc = gate.main()
    assert rc == 1, "gate must fail-closed (exit 1) on an NFD-decomposed path"
