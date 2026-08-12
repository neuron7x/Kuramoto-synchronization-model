#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from tools.cns_program.cns_contract import MANIFEST_VERIFICATION_RESULT

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ManifestPayload = dict[str, object]


class SimpleManifestError(ValueError):
    """Raised when the CNS release manifest cannot be structurally verified."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json_object(path: Path) -> ManifestPayload:
    raw_data: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_data, dict):
        raise SimpleManifestError("manifest_not_object")
    return {str(key): value for key, value in raw_data.items()}


def verify(path: Path) -> ManifestPayload:
    errors: list[str] = []
    if not path.exists():
        errors.append(f"manifest_missing:{path}")
        return {
            "valid": False,
            "errors": errors,
            "checked_artifacts": 0,
            "total_artifacts": 0,
        }

    try:
        data = load_json_object(path)
    except SimpleManifestError as exc:
        errors.append(str(exc))
        data = {}

    raw_sha_map = data.get("sha256")
    if not isinstance(raw_sha_map, dict) or not raw_sha_map:
        errors.append("sha256_map_missing")
        sha_map: dict[str, object] = {}
    else:
        sha_map = {str(key): value for key, value in raw_sha_map.items()}

    checked = 0
    for raw_path, expected in sha_map.items():
        if not isinstance(expected, str) or not SHA256_RE.match(expected):
            errors.append(f"sha256_invalid:{raw_path}")
            continue
        target = Path(raw_path)
        if not target.exists():
            errors.append(f"artifact_missing:{raw_path}")
            continue
        actual = sha256_file(target)
        if actual != expected:
            errors.append(f"artifact_hash_mismatch:{raw_path}")
            continue
        checked += 1

    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "manifest": str(path),
        "valid": not errors,
        "errors": errors,
        "checked_artifacts": checked,
        "total_artifacts": len(sha_map),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="results/cns_release_manifest.json")
    args = parser.parse_args()
    payload = verify(Path(str(args.manifest)))
    MANIFEST_VERIFICATION_RESULT.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_VERIFICATION_RESULT.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload.get("valid") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
