from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HEX = set("0123456789abcdef")
NOTE = Path("docs/readiness_note.md")


def load_data() -> dict:
    return json.loads(Path("governance/readiness_register.json").read_text(encoding="utf-8"))


def test_readiness_register_is_structured() -> None:
    data = load_data()

    assert data["schema_version"] == "readiness.v1"
    assert data["system"] == "GeoSync"
    assert data["current_level"] == "L4-minus"
    assert data["target_direction"] == "L5-candidate"

    entries = data["entries"]
    assert len(entries) >= 5

    seen_ids: set[str] = set()
    for entry in entries:
        assert entry["id"] not in seen_ids
        seen_ids.add(entry["id"])
        assert entry["status"] in {"open", "closed"}
        assert isinstance(entry["summary"], str)
        assert len(entry["summary"]) >= 20
        assert isinstance(entry["required_artifacts"], list)
        assert entry["required_artifacts"]


def test_readiness_register_starts_without_promotion() -> None:
    data = load_data()

    assert data["current_level"] != data["target_direction"]
    assert any(entry["status"] == "open" for entry in data["entries"])


def test_evidence_artifact_records_are_structured_when_present() -> None:
    data = load_data()

    for entry in data["entries"]:
        records = entry.get("evidence_artifacts")
        if records is None:
            continue
        assert isinstance(records, list)
        assert records or entry["status"] == "open"
        for record in records:
            assert isinstance(record, dict)
            for key in ("kind", "path", "verification_command"):
                assert isinstance(record.get(key), str)
                assert record[key].strip()
            digest = record.get("sha256")
            assert isinstance(digest, str)
            assert len(digest) == 64
            assert digest == digest.lower()
            assert set(digest) <= HEX


def test_readiness_note_mentions_every_register_entry() -> None:
    data = load_data()
    note_text = NOTE.read_text(encoding="utf-8")

    for entry in data["entries"]:
        assert entry["id"] in note_text

    for phrase in ("Boundary", "Register", "Evidence", "Gate", "Review"):
        assert phrase in note_text


def test_readiness_checker_runs_under_optimized_python() -> None:
    result = subprocess.run(
        [sys.executable, "-O", "tools/check_readiness_register.py"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "readiness register ok" in result.stdout
