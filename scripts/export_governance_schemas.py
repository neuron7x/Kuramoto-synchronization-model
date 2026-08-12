#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Export typed governance models as JSON Schema documents.

Produces canonical JSON Schema 2020-12 artefacts for the two governance
schemas published by the typed Pydantic v2 layer
(``application.governance``):

    docs/schemas/governance/claim_ledger.schema.json
    docs/schemas/governance/commit_acceptor.schema.json

External consumers (IDE plugins, OpenAPI tooling, third-party auditors)
can pin against these JSON Schemas without re-parsing the YAML or
importing Pydantic. Drift between the typed model and the published
schema is caught by the CI gate ``governance-schema-export-sync``,
which re-runs this script and fails if the on-disk artefact differs
from the freshly-generated output.

Run locally before PR:

    python scripts/export_governance_schemas.py [--check]

Without ``--check`` the script writes the schemas. With ``--check`` it
compares the generated output against on-disk and exits non-zero on
divergence — used by CI.

Exit codes:

    0  — schemas written (or, with --check, on-disk matches generated)
    1  — drift detected (only in --check mode)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from application.governance import ClaimLedger, CommitAcceptor

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "docs" / "schemas" / "governance"

CLAIM_LEDGER_PATH = OUTPUT_DIR / "claim_ledger.schema.json"
COMMIT_ACCEPTOR_PATH = OUTPUT_DIR / "commit_acceptor.schema.json"


def _generate() -> dict[Path, dict[str, Any]]:
    """Return the canonical {output_path: schema_dict} mapping."""
    return {
        CLAIM_LEDGER_PATH: ClaimLedger.model_json_schema(),
        COMMIT_ACCEPTOR_PATH: CommitAcceptor.model_json_schema(),
    }


def _serialise(schema: dict[str, Any]) -> str:
    """Deterministic serialisation: sort keys, ensure trailing newline.

    ``sort_keys=True`` makes the output reproducible across Pydantic
    versions; ``indent=2`` keeps the artefact reviewable; the trailing
    newline keeps `git diff` clean.
    """
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def _write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def export(*, check: bool) -> int:
    """Generate (or verify) the JSON Schema export.

    Returns 0 on success, 1 on detected drift in ``--check`` mode.
    """
    drift_paths: list[Path] = []
    for path, schema in _generate().items():
        generated = _serialise(schema)
        if check:
            if not path.exists():
                drift_paths.append(path)
                continue
            current = path.read_text(encoding="utf-8")
            if current != generated:
                drift_paths.append(path)
        else:
            _write(path, generated)

    if check:
        if drift_paths:
            print("governance schemas drift detected:", file=sys.stderr)
            for path in drift_paths:
                rel = path.relative_to(ROOT)
                print(
                    f"  {rel} differs from `python {Path(__file__).relative_to(ROOT)}` output",
                    file=sys.stderr,
                )
            print(
                "Run `python scripts/export_governance_schemas.py` to regenerate.",
                file=sys.stderr,
            )
            return 1
        print(f"PASS: {len(_generate())} governance schema(s) match the typed model.")
    else:
        for path in _generate():
            rel = path.relative_to(ROOT)
            print(f"wrote {rel}")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the on-disk schema artefact differs from the generated output.",
    )
    args = parser.parse_args(argv)
    return export(check=args.check)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
