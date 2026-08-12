# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Validate the executable falsification-contract catalog and emit evidence.

Fails closed (exit 1) if: the catalog is schema-invalid, any blocking law lacks a
collected positive witness or negative control, or — after emission — any
declared evidence artifact is missing. Emits one JSON evidence report per
distinct ``evidence_output`` into ``evidence/physics/``.

Usage:
    python tools/validate_physics_contracts.py [--repo-root .]

This operates only on physics_contracts/falsification_catalog.yaml. The canonical
112-invariant catalog.yaml is never read or mutated here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Resolve the repo root for artifact paths. The physics modules are imported
# from the installed canonical `core` package (pip install -e .) — no sys.path
# mutation (enforced by the import-architecture ratchet). Run with the package
# installed, or via `PYTHONPATH=. python tools/validate_physics_contracts.py`.
REPO_ROOT = Path(__file__).resolve().parents[1]


def emit_evidence(catalog: dict[str, Any], repo_root: Path) -> list[Path]:
    """Write one evidence JSON per distinct evidence_output; return written paths."""
    from core.physics.governance import check_negative_controls, check_witness_coverage

    grouped: dict[str, list[dict[str, Any]]] = {}
    for law in catalog["laws"]:
        grouped.setdefault(str(law["evidence_output"]), []).append(law)

    missing_pos = set(check_witness_coverage(catalog, repo_root))
    missing_neg = set(check_negative_controls(catalog, repo_root))

    written: list[Path] = []
    for evidence_rel, laws in grouped.items():
        report: dict[str, Any] = {
            "evidence_output": evidence_rel,
            "n_laws": len(laws),
            "laws": [
                {
                    "id": law["id"],
                    "domain": law["domain"],
                    "blocking": law["blocking"],
                    "positive_witness": law["positive_witness"],
                    "negative_control": law["negative_control"],
                    "positive_witness_collected": law["id"] not in missing_pos,
                    "negative_control_collected": law["id"] not in missing_neg,
                    "threshold": law["threshold"],
                }
                for law in laws
            ],
        }
        report["all_witnessed"] = all(
            entry["positive_witness_collected"] and entry["negative_control_collected"]
            for entry in report["laws"]
        )
        out_path = repo_root / evidence_rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(out_path)
    return written


def validate(repo_root: Path | None = None) -> dict[str, Any]:
    """Run the full validation+emission cycle; return a structured verdict."""
    from core.physics.governance import load_catalog, promotion_gate, validate_law_schema

    root = repo_root or REPO_ROOT
    catalog = load_catalog(root / "physics_contracts" / "falsification_catalog.yaml")

    schema_errors: list[str] = []
    for law in catalog["laws"]:
        for err in validate_law_schema(law):
            schema_errors.append(f"{law.get('id', '?')}: {err}")

    # Coverage gate BEFORE evidence exists (require_evidence=False), then emit.
    pre = promotion_gate(catalog, root, require_evidence=False)
    written = emit_evidence(catalog, root)
    post = promotion_gate(catalog, root, require_evidence=True)

    errors = schema_errors + [e for e in post["errors"] if e not in schema_errors]
    return {
        "status": "PASS" if not errors and pre["status"] == "PASS" else "FAIL",
        "n_laws": post["n_laws"],
        "n_blocking": post["n_blocking"],
        "evidence_written": [str(p.relative_to(root)) for p in written],
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)
    verdict = validate(Path(args.repo_root).resolve())
    print(json.dumps(verdict, indent=2, sort_keys=True))
    if verdict["status"] != "PASS":
        print(f"VALIDATION FAILED: {len(verdict['errors'])} error(s)", file=sys.stderr)
        return 1
    print(f"VALIDATION PASSED: {verdict['n_blocking']} blocking laws fully witnessed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
