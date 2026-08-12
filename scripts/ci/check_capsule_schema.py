#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Validate every committed reproducible-capsule manifest against its schema.

A gate-friendly wrapper around schemas/reproducible_capsule.schema.json: it
discovers each capsule ``manifest.json`` under artifacts/reproducible_capsules/
and validates it, so a malformed capsule cannot be committed silently. Used by
the evidence-gate (layer 8) and the reproducible-capsule CI workflow.

Exit codes::

    0  — every capsule manifest is schema-valid
    1  — at least one manifest violates the schema
    2  — schema or capsule root missing
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "reproducible_capsule.schema.json"
CAPSULE_ROOT = ROOT / "artifacts" / "reproducible_capsules"


def main() -> int:
    if not SCHEMA_PATH.exists():
        print(f"schema not found: {SCHEMA_PATH}", file=sys.stderr)
        return 2
    if not CAPSULE_ROOT.exists():
        print(f"capsule root not found: {CAPSULE_ROOT}", file=sys.stderr)
        return 2

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)

    # A reproducible-capsule manifest is the direct child of a capsule directory
    # (artifacts/reproducible_capsules/<id>/manifest.json). The nested
    # bundle/manifest.json is the generator's own native manifest, not a capsule
    # envelope, and is intentionally not validated here.
    manifests = sorted(CAPSULE_ROOT.glob("*/manifest.json"))
    if not manifests:
        print(f"no capsule manifests found under {CAPSULE_ROOT}", file=sys.stderr)
        return 1

    failures = 0
    for manifest_path in manifests:
        rel = manifest_path.relative_to(ROOT).as_posix()
        try:
            doc = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"  - {rel}: invalid JSON ({exc})", file=sys.stderr)
            failures += 1
            continue
        errors = sorted(validator.iter_errors(doc), key=lambda e: e.path)
        if errors:
            failures += 1
            for err in errors:
                loc = "/".join(str(p) for p in err.path) or "<root>"
                print(f"  - {rel}: {loc}: {err.message}", file=sys.stderr)

    if failures:
        print(f"Capsule schema validation FAILED: {failures} manifest(s).", file=sys.stderr)
        return 1
    print(f"Capsule schema validation passed ({len(manifests)} manifest(s)).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
