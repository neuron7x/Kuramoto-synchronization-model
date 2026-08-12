# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Verify readiness-register evidence integrity (fail-closed).

For every entry in ``governance/readiness_register.json`` that carries
``evidence_artifacts``, recompute each artifact's SHA-256 and confirm it matches
the digest pinned in the register, and that the file exists. Any drift, missing
file, or digest mismatch exits non-zero. This is the ``verification_command``
target referenced by the evidence records and is wired as a CI gate.

Run: ``python -m tools.readiness.verify_evidence`` (optional ``--entry ID``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REGISTER = Path("governance/readiness_register.json")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(entry_filter: str | None = None) -> list[str]:
    data: dict[str, Any] = json.loads(REGISTER.read_text(encoding="utf-8"))
    errors: list[str] = []
    checked = 0
    for entry in data.get("entries", []):
        entry_id = str(entry.get("id"))
        if entry_filter is not None and entry_id != entry_filter:
            continue
        for index, record in enumerate(entry.get("evidence_artifacts", []) or []):
            loc = f"{entry_id}.evidence_artifacts[{index}]"
            path = Path(str(record.get("path")))
            expected = str(record.get("sha256"))
            if not path.exists():
                errors.append(f"{loc}: missing artifact file {path}")
                continue
            actual = _sha256(path)
            if actual != expected:
                errors.append(
                    f"{loc}: sha256 drift for {path}: register={expected} actual={actual}"
                )
            else:
                checked += 1
    print(f"readiness evidence verified: {checked} artifact(s), {len(errors)} error(s)")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", default=None, help="verify only this readiness entry id")
    args = parser.parse_args()
    errors = verify(args.entry)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
