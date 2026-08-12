#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Evidence-artifact provenance + freshness gate (P0-7 / Task 6).

A governance repo must PROVE its committed evidence artifacts were regenerated
from their sources, not hand-edited, and that EVERY evidence artifact carries a
determinism class (uniform trust, not mixed). Driven by
``artifacts/evidence_provenance.contract.json``:

  * every ``deterministic`` artifact is regenerated with its declared generator
    and asserted byte-identical to the committed file (CI ``git diff`` equivalent),
    with a matching ``artifacts/manifest.json`` (sha256 / generator / sources);
  * ``nondeterministic`` / ``external-data-bound`` / ``generated-but-excluded``
    artifacts require an ``exclusion_reason`` and are not byte-compared;
  * any ``*.json`` under a declared evidence surface that is NOT classified in
    the contract fails the gate (no silently-unclassified evidence).

Multi-output generators are handled by snapshotting ALL deterministic artifacts,
running each unique generator once, comparing, then restoring — so the working
tree is never left dirty.

Usage::

    python scripts/ci/check_artifact_freshness.py            # verify (fail-closed)
    python scripts/ci/check_artifact_freshness.py --write     # regenerate manifest

Exit codes: 0 fresh + fully classified; 1 stale / manifest drift / unclassified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "artifacts" / "evidence_provenance.contract.json"
MANIFEST = ROOT / "artifacts" / "manifest.json"


@dataclass(frozen=True)
class _ArtifactSpec:
    artifact: str
    generator: list[str]
    sources: list[str]
    determinism_class: str
    exclusion_reason: str = ""


def _load_contract() -> dict[str, object]:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def _all_specs() -> list[_ArtifactSpec]:
    contract = _load_contract()
    rows: list[_ArtifactSpec] = []
    for a in cast("list[dict[str, Any]]", contract["artifacts"]):
        rows.append(
            _ArtifactSpec(
                artifact=str(a["artifact"]),
                generator=[str(g) for g in a.get("generator", [])],
                sources=[str(s) for s in a.get("sources", [])],
                determinism_class=str(a["determinism_class"]),
                exclusion_reason=str(a.get("exclusion_reason", "")),
            )
        )
    return rows


def _deterministic_specs() -> list[_ArtifactSpec]:
    return [s for s in _all_specs() if s.determinism_class == "deterministic"]


# Public alias kept for tests / external callers.
DETERMINISTIC_ARTIFACTS = _deterministic_specs()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run_generator(generator: list[str]) -> None:
    full_env = {**os.environ, "PYTHONPATH": str(ROOT)}
    subprocess.run(
        [sys.executable, *generator],
        cwd=ROOT,
        env=full_env,
        check=True,
        capture_output=True,
    )


def _snapshot(specs: list[_ArtifactSpec]) -> dict[str, bytes]:
    return {
        s.artifact: (ROOT / s.artifact).read_bytes() for s in specs if (ROOT / s.artifact).is_file()
    }


def _regenerate_all(specs: list[_ArtifactSpec]) -> dict[str, str]:
    """Snapshot → run each unique generator once → return regenerated sha per
    artifact → restore the committed bytes (tree left clean)."""
    snapshot = _snapshot(specs)
    unique_gens = {tuple(s.generator) for s in specs if s.generator}
    regenerated: dict[str, str] = {}
    try:
        for gen in unique_gens:
            _run_generator(list(gen))
        for art in snapshot:
            regenerated[art] = _sha256((ROOT / art).read_bytes())
    finally:
        for art, committed in snapshot.items():
            (ROOT / art).write_bytes(committed)
    return regenerated


def regenerated_sha(entry: _ArtifactSpec) -> tuple[str, str]:
    """(committed_sha, regenerated_sha) for one artifact; tree restored."""
    committed = _sha256((ROOT / entry.artifact).read_bytes())
    regenerated = _regenerate_all(_deterministic_specs()).get(entry.artifact, "")
    return committed, regenerated


def build_manifest() -> dict[str, object]:
    rows = []
    for spec in _all_specs():
        path = ROOT / spec.artifact
        rows.append(
            {
                "artifact": spec.artifact,
                "determinism_class": spec.determinism_class,
                "generator_command": (
                    ("python " + " ".join(spec.generator)) if spec.generator else ""
                ),
                "sources": spec.sources,
                "exclusion_reason": spec.exclusion_reason,
                "artifact_sha256": _sha256(path.read_bytes()) if path.is_file() else None,
            }
        )
    return {
        "schema": "evidence_artifact_freshness@v1",
        "generated_at_policy": "deterministic; no wall-clock, no RNG",
        "artifacts": rows,
    }


def _unclassified(contract: dict[str, object]) -> list[str]:
    classified = {str(a["artifact"]) for a in cast("list[dict[str, Any]]", contract["artifacts"])}
    errors: list[str] = []
    for surface in cast("list[str]", contract.get("evidence_surfaces", [])):
        for path in (ROOT / str(surface)).rglob("*.json"):
            rel = path.relative_to(ROOT).as_posix()
            if rel not in classified:
                errors.append(f"unclassified evidence artifact (add to provenance contract): {rel}")
    return errors


def check() -> list[str]:
    errors: list[str] = []
    contract = _load_contract()
    errors.extend(_unclassified(contract))

    # Every non-deterministic class must justify why it is not byte-compared.
    for spec in _all_specs():
        if spec.determinism_class != "deterministic" and not spec.exclusion_reason.strip():
            errors.append(
                f"{spec.artifact}: determinism_class {spec.determinism_class!r} "
                "requires an exclusion_reason"
            )

    det = _deterministic_specs()
    for spec in det:
        # A deterministic artifact with no generator is never regenerated, so
        # the snapshot-vs-committed compare trivially passes and freshness is
        # falsely "proven". Freshness cannot be established without a generator.
        if not [g for g in spec.generator if g.strip()]:
            errors.append(
                f"deterministic artifact {spec.artifact} declares no generator; "
                "freshness cannot be proven"
            )
        if not (ROOT / spec.artifact).is_file():
            errors.append(f"missing deterministic artifact: {spec.artifact}")
    present = [s for s in det if (ROOT / s.artifact).is_file()]
    committed = {s.artifact: _sha256((ROOT / s.artifact).read_bytes()) for s in present}
    regenerated = _regenerate_all(present)
    for art, committed_sha in committed.items():
        if regenerated.get(art) != committed_sha:
            errors.append(
                f"STALE: {art} committed {committed_sha[:12]} != regenerated "
                f"{(regenerated.get(art) or '<none>')[:12]} "
                "(run `make regenerate-evidence`)"
            )

    if not MANIFEST.is_file():
        errors.append(f"missing {MANIFEST.relative_to(ROOT)} (run --write)")
    elif json.loads(MANIFEST.read_text(encoding="utf-8")) != build_manifest():
        rel = MANIFEST.relative_to(ROOT).as_posix()
        errors.append(f"{rel} drift — regenerate with --write")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="regenerate the manifest")
    args = parser.parse_args(argv)

    if args.write:
        MANIFEST.write_text(json.dumps(build_manifest(), indent=2) + "\n", encoding="utf-8")
        print(f"wrote {MANIFEST.relative_to(ROOT)}")
        return 0

    errors = check()
    if errors:
        print("ARTIFACT FRESHNESS/PROVENANCE FAIL:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    print(
        "ARTIFACT FRESHNESS: PASS — "
        f"{len(_deterministic_specs())} deterministic artifacts fresh, "
        "all evidence artifacts classified."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
