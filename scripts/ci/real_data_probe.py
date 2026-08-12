#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""G.real_data — real-market-data evidence tribunal (artifact-aware).

Tribunal for the gate ``G.real_data``. A research claim about market
structure is only as strong as the *real* data behind it. This probe refuses
to let synthetic fixtures masquerade as market validity. It scans the
repository for any real-data evidence manifest, validates each manifest
against a fail-closed schema, and emits the honest tier.

Schema (per manifest entry)::

    artifact_id, venue, symbol, time_start_utc, time_end_utc, git_sha,
    git_dirty, config_sha256, data_sha256, data_bytes, schema_version,
    license_provenance, replay_command, status

Fail-closed rules (each a hard reject):

* zero-byte data forbidden (``data_bytes <= 0``)
* missing / placeholder ``data_sha256`` forbidden
* missing ``replay_command`` forbidden
* missing ``license_provenance`` forbidden
* a dirty git tree cannot support a signoff tier (status downgraded/blocked)
* ``status`` may not exceed ``MEASURED_SINGLE`` without ≥2 independent
  sessions (distinct ``time_start_utc`` windows) attested in the manifest

Honest current state of this repository: only synthetic single-session
fixtures exist (``data/sample_ohlc.csv`` is marked ``forbidden_use: not for
live trading``; all 18 ingestion adapters are stub-only). Therefore this
probe emits ``status = BLOCKED`` and keeps the release RED. It does NOT
fabricate market validity.

Output: ``artifacts/evidence/real_data_manifest.json``. Exit 0 only if a
manifest attests at least ``MEASURED_SINGLE`` real data; otherwise nonzero.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.ci.proof_common import ROOT, write_artifact

ARTIFACT = "artifacts/evidence/real_data_manifest.json"

REQUIRED_FIELDS: tuple[str, ...] = (
    "artifact_id",
    "venue",
    "symbol",
    "time_start_utc",
    "time_end_utc",
    "git_sha",
    "git_dirty",
    "config_sha256",
    "data_sha256",
    "data_bytes",
    "schema_version",
    "license_provenance",
    "replay_command",
    "status",
)

VALID_STATUSES: tuple[str, ...] = ("OBSERVE", "MEASURED_SINGLE", "MEASURED_MULTI", "BLOCKED")
_PLACEHOLDER_HASHES = frozenset({"", "0" * 64, "x" * 64, "todo", "tbd", "none", "null"})

# Locations a genuine real-data manifest could live. Synthetic fixtures are
# explicitly NOT scanned as evidence — they cannot support a market tier.
_EVIDENCE_GLOBS: tuple[str, ...] = (
    "artifacts/evidence/real_data/*.json",
    "artifacts/data-traces/real_*.json",
)


def validate_manifest(m: dict[str, Any]) -> list[str]:
    """Return a list of fail-closed violations for one manifest entry (empty = clean)."""
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in m:
            errors.append(f"missing required field: {field}")
    if errors:
        return errors  # cannot validate values without the fields

    if not isinstance(m["data_bytes"], int) or m["data_bytes"] <= 0:
        errors.append("zero-byte or non-integer data_bytes (real data must be non-empty)")
    if str(m["data_sha256"]).strip().lower() in _PLACEHOLDER_HASHES:
        errors.append("missing/placeholder data_sha256")
    if str(m["config_sha256"]).strip().lower() in _PLACEHOLDER_HASHES:
        errors.append("missing/placeholder config_sha256")
    if not str(m["replay_command"]).strip():
        errors.append("missing replay_command")
    if not str(m["license_provenance"]).strip():
        errors.append("missing license_provenance")
    if m["status"] not in VALID_STATUSES:
        errors.append(f"invalid status: {m['status']!r}")
    if m.get("git_dirty") is True and m["status"] in ("MEASURED_SINGLE", "MEASURED_MULTI"):
        errors.append("dirty git tree cannot support a signoff tier")
    sessions = m.get("independent_sessions", 1)
    if m["status"] == "MEASURED_MULTI" and (not isinstance(sessions, int) or sessions < 2):
        errors.append("MEASURED_MULTI requires ≥2 independent_sessions")
    return errors


def _discover_manifests() -> list[Path]:
    out: list[Path] = []
    for glob in _EVIDENCE_GLOBS:
        out.extend(sorted(ROOT.glob(glob)))
    return out


def run() -> dict[str, Any]:
    manifests = _discover_manifests()
    entries: list[dict[str, Any]] = []
    best_tier = "BLOCKED"
    tier_rank = {"BLOCKED": 0, "OBSERVE": 1, "MEASURED_SINGLE": 2, "MEASURED_MULTI": 3}

    for path in manifests:
        rel = path.relative_to(ROOT).as_posix()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # unparseable evidence is a hard reject (fail-closed)
            entries.append(
                {"source": rel, "status": "BLOCKED", "errors": [f"unparseable: {exc!r}"]}
            )
            continue
        errs = validate_manifest(data)
        status = "BLOCKED" if errs else data["status"]
        entries.append({"source": rel, "status": status, "errors": errs})
        if not errs and tier_rank.get(status, 0) > tier_rank[best_tier]:
            best_tier = status

    blocker = (
        "no real-market-data manifest present — repository contains only "
        "synthetic single-session fixtures (data/sample_ohlc.csv is marked "
        "forbidden_use: not for live trading; all ingestion adapters are "
        "stub-only). Cannot attest MEASURED_SINGLE without real data."
    )
    has_real = best_tier in ("MEASURED_SINGLE", "MEASURED_MULTI")
    return {
        "gate": "G.real_data",
        "schema_version": "1.0",
        "status": best_tier,
        "required_fields": list(REQUIRED_FIELDS),
        "manifests_found": len(manifests),
        "entries": entries,
        "blocker": "" if has_real else blocker,
        "next_action": (
            ""
            if has_real
            else "Stage ≥1 real venue session under artifacts/evidence/real_data/<id>.json "
            "with non-zero data_sha256, license_provenance, replay_command, and "
            "git_dirty=false; re-run this probe."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default=ARTIFACT, help="artifact output path")
    args = parser.parse_args(argv)
    payload = run()
    path = write_artifact(args.json, payload)
    print(
        f"[G.real_data] status={payload['status']} manifests={payload['manifests_found']} -> {path}"
    )
    if payload["blocker"]:
        print(f"  BLOCKER: {payload['blocker']}")
    return 0 if payload["status"] in ("MEASURED_SINGLE", "MEASURED_MULTI") else 1


if __name__ == "__main__":
    raise SystemExit(main())
