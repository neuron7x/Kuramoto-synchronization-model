#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

REGISTER = Path("governance/readiness_register.json")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def add_error(errors: list[str], location: str, message: str) -> None:
    errors.append(f"{location}: {message}")


def require_text(errors: list[str], location: str, value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        add_error(errors, location, "must be a non-empty string")


def check_record(errors: list[str], location: str, record: Any) -> None:
    if not isinstance(record, dict):
        add_error(errors, location, "must be an object")
        return

    for key in ("kind", "path", "verification_command"):
        require_text(errors, f"{location}.{key}", record.get(key))

    digest = record.get("sha256")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        add_error(errors, f"{location}.sha256", "must be a lowercase SHA-256 hex digest")


def check_entry(errors: list[str], location: str, entry: Any, seen_ids: set[str]) -> None:
    if not isinstance(entry, dict):
        add_error(errors, location, "must be an object")
        return

    entry_id = entry.get("id")
    if not isinstance(entry_id, str) or not entry_id.strip():
        add_error(errors, f"{location}.id", "must be a non-empty string")
        entry_id = location
    elif entry_id in seen_ids:
        add_error(errors, f"{location}.id", f"duplicate id {entry_id}")
    else:
        seen_ids.add(entry_id)

    status = entry.get("status")
    if status not in {"open", "closed"}:
        add_error(errors, f"{entry_id}.status", "must be open or closed")

    summary = entry.get("summary")
    if not isinstance(summary, str) or len(summary.strip()) < 20:
        add_error(errors, f"{entry_id}.summary", "must be at least 20 non-space characters")

    required = entry.get("required_artifacts")
    if not isinstance(required, list) or not required:
        add_error(errors, f"{entry_id}.required_artifacts", "must be a non-empty list")
    elif any(not isinstance(item, str) or not item.strip() for item in required):
        add_error(errors, f"{entry_id}.required_artifacts", "items must be non-empty strings")

    records = entry.get("evidence_artifacts")
    if status == "closed" and not records:
        add_error(errors, f"{entry_id}.evidence_artifacts", "required when status is closed")
    if records is not None:
        if not isinstance(records, list):
            add_error(errors, f"{entry_id}.evidence_artifacts", "must be a list")
        else:
            for index, record in enumerate(records):
                check_record(errors, f"{entry_id}.evidence_artifacts[{index}]", record)


def check_register(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["register: must be a JSON object"]

    if data.get("schema_version") != "readiness.v1":
        add_error(errors, "schema_version", "must be readiness.v1")
    if data.get("system") != "GeoSync":
        add_error(errors, "system", "must be GeoSync")

    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        add_error(errors, "entries", "must be a non-empty list")
        return errors

    seen_ids: set[str] = set()
    for index, entry in enumerate(entries):
        check_entry(errors, f"entries[{index}]", entry, seen_ids)
    return errors


def main() -> int:
    errors = check_register(json.loads(REGISTER.read_text(encoding="utf-8")))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("readiness register ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
