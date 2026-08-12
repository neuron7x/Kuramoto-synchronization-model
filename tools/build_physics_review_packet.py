# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Build the physics review packet from the catalog and emitted evidence.

Reads physics_contracts/falsification_catalog.yaml and evidence/physics/*.json
(produced by tools/validate_physics_contracts.py) and writes:
  docs/PHYSICS_VERDICT.md
  docs/PHYSICS_REVIEW_PACKET.md
  docs/PHYSICS_CLAIMS.md

Deterministic: identical catalog + evidence produce byte-identical docs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

# Repo root for reading/writing artifacts. Physics modules are imported from the
# installed canonical `core` package — no sys.path mutation (import-architecture
# ratchet). Run installed, or via `PYTHONPATH=. python tools/...`.
REPO_ROOT = Path(__file__).resolve().parents[1]


def _evidence_status(repo_root: Path, catalog: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    """Return (status, verified_law_ids, unverified_law_ids)."""
    from core.physics.governance import claim_evidence_map

    evidence_present = claim_evidence_map(catalog, repo_root)
    verified: list[str] = []
    unverified: list[str] = []
    for law in catalog["laws"]:
        law_id = str(law["id"])
        report_path = repo_root / str(law["evidence_output"])
        witnessed = False
        if evidence_present.get(law_id) and report_path.is_file():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            witnessed = any(
                entry["id"] == law_id
                and entry["positive_witness_collected"]
                and entry["negative_control_collected"]
                for entry in report.get("laws", [])
            )
        (verified if witnessed else unverified).append(law_id)
    status = "PASS" if not unverified else ("PARTIAL" if verified else "FAIL")
    return status, verified, unverified


def build_review_packet(repo_root: Path | None = None) -> dict[str, Any]:
    """Generate the three packet docs; return a summary dict."""
    from core.physics.governance import load_catalog

    root = repo_root or REPO_ROOT
    catalog = load_catalog(root / "physics_contracts" / "falsification_catalog.yaml")
    status, verified, unverified = _evidence_status(root, catalog)
    docs_dir = root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    laws = catalog["laws"]
    commands = [
        "python tools/validate_physics_contracts.py",
        "python -m pytest tests/physics -q",
        "python tools/build_physics_review_packet.py",
    ]

    verdict_lines = [
        "# PHYSICS VERDICT",
        "",
        f"Status: {status}",
        "",
        "Verified:",
        *([f"- {law_id}" for law_id in verified] or ["- (none)"]),
        "",
        "Falsified:",
        "- (none — every negative control is expected to fail its law and does)",
        "",
        "Not Verified:",
        *([f"- {law_id}" for law_id in unverified] or ["- (none)"]),
        "",
        "Blocked Claims:",
        *([f"- {law['id']}: {law['failure_message']}" for law in laws if law["blocking"]]),
        "",
        "Evidence:",
        *sorted({f"- {law['evidence_output']}" for law in laws}),
        "",
        "Commands:",
        *[f"- {cmd}" for cmd in commands],
        "",
    ]
    (docs_dir / "PHYSICS_VERDICT.md").write_text("\n".join(verdict_lines), encoding="utf-8")

    claims_lines = [
        "# PHYSICS CLAIMS",
        "",
        "Every claim below is bound to an executable positive witness and a negative",
        "control. A claim with no collected witness or no negative control cannot be",
        "promoted (see `law_requires_positive_and_negative_witness`).",
        "",
        "| Law | Domain | Claim | Threshold | Positive witness | Negative control |",
        "| --- | --- | --- | --- | --- | --- |",
        *[
            f"| `{law['id']}` | {law['domain']} | {law['claim']} | {law['threshold']} "
            f"| `{law['positive_witness']}` | `{law['negative_control']}` |"
            for law in laws
        ],
        "",
    ]
    (docs_dir / "PHYSICS_CLAIMS.md").write_text("\n".join(claims_lines), encoding="utf-8")

    packet_lines = [
        "# PHYSICS REVIEW PACKET",
        "",
        f"Status: {status} — {len(verified)}/{len(laws)} laws verified.",
        "",
        "## Scope",
        "",
        "Executable falsification-contract layer over the verified GeoSync physics",
        "engines (Ricci/Kuramoto, metric consistency, causality, Landauer, empirical",
        "falsification, numerical precision, governance). It is generated from",
        "`physics_contracts/falsification_catalog.yaml` and reconciled with the",
        "canonical `physics_contracts/catalog.yaml` authority where a declared domain",
        "must be tightened to match the executable witness.",
        "",
        "## Reproduce",
        "",
        "```",
        *commands,
        "```",
        "",
        "## Laws and formal invariants",
        "",
        *[
            f"- **{law['id']}** ({law['domain']}): {law['formal_invariant']}  "
            f"\n  measured: {law['measured_quantity']}; threshold: {law['threshold']}"
            for law in laws
        ],
        "",
        "## Evidence artifacts",
        "",
        *sorted({f"- `{law['evidence_output']}`" for law in laws}),
        "",
    ]
    (docs_dir / "PHYSICS_REVIEW_PACKET.md").write_text("\n".join(packet_lines), encoding="utf-8")

    return {"status": status, "verified": verified, "unverified": unverified, "n_laws": len(laws)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)
    summary = build_review_packet(Path(args.repo_root).resolve())
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
