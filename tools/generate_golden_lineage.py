#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reconstruct only the license-clean synthetic MACD DAT-002 lineage.

Never invent real-market data, issue a MEASURED claim or materialize a missing
proprietary source. The committed DAT-001 manifest and its on-disk CSV bytes
are the authoritative inputs. --check is read-only and fails on any drift.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/manifests/golden-macd-baseline-v1.json"
OUTPUT_DIR = ROOT / "data/lineage"
RAW_FILE = "data/golden/indicator_macd_baseline.csv"
VERSION = "data_lineage.v1"
SHA64 = re.compile(r"^[0-9a-f]{64}$")


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _node_address(node: dict[str, Any]) -> str:
    fields: dict[str, Any] = {}
    for key in ("tier", "inputs", "transform", "validation"):
        if key in node and node[key] is not None:
            fields[key] = sorted(node[key]) if key == "inputs" else node[key]
    return _hash(_canonical(fields))


def _canonical_line_digest(raw: bytes) -> str:
    lines = sorted(line.strip() for line in raw.decode("utf-8").splitlines() if line.strip())
    return _hash("\n".join(lines).encode("utf-8"))


def build() -> dict[str, dict[str, Any]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not (
        manifest.get("id") == "golden-macd-baseline-v1"
        and manifest.get("license") == "MIT"
        and manifest.get("license_verified") is True
        and manifest.get("evidence_class") == "SIMULATION"
        and manifest.get("source", {}).get("origin") == "repository_generated"
    ):
        raise ValueError("Missing MIT/synthetic provenance; refusing lineage generation")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != 1 or files[0].get("path") != RAW_FILE:
        raise ValueError("Expected exactly one canonical MACD source file")
    raw = (ROOT / RAW_FILE).read_bytes()
    if (
        _hash(raw) != files[0].get("checksum_sha256")
        or len(raw) != files[0].get("bytes")
        or len(raw) != manifest.get("bytes")
    ):
        raise ValueError("Raw source digest or length drifted from immutable DAT-001 manifest")
    root_digest = manifest.get("checksum", {}).get("value")
    if not isinstance(root_digest, str) or not SHA64.fullmatch(root_digest):
        raise ValueError("Dataset-level DAT-001 digest absent or invalid")

    raw_node: dict[str, Any] = {
        "lineage_version": VERSION,
        "node_id": "raw.golden-macd-baseline-v1",
        "tier": "raw",
        "manifest_ref": "golden-macd-baseline-v1",
        "content_address": root_digest,
        "inputs": [],
        "transform": None,
        "evidence_class": "SIMULATION",
    }
    validated_node: dict[str, Any] = {
        "lineage_version": VERSION,
        "node_id": "validated.golden-macd-baseline-v1",
        "tier": "validated",
        "inputs": [root_digest],
        "transform": {
            "id": "validate.schema_and_checksum.v1",
            "params": {"manifest_ref": "golden-macd-baseline-v1", "raw_file": RAW_FILE},
        },
        "validation": {"verdict": "accepted", "reason": "MIT CSV bytes match DAT-001"},
    }
    validated_node["content_address"] = _node_address(validated_node)

    derived_node: dict[str, Any] = {
        "lineage_version": VERSION,
        "node_id": "derived.golden-macd.canonical-line-digest.v1",
        "tier": "derived",
        "inputs": [validated_node["content_address"]],
        "transform": {
            "id": "transform.canonical_line_digest.v1",
            "params": {"encoding": "utf-8", "input_file": RAW_FILE},
            "output_sha256": _canonical_line_digest(raw),
        },
    }
    derived_node["content_address"] = _node_address(derived_node)

    graph: dict[str, Any] = {
        "lineage_version": VERSION,
        "evidence_class": "SIMULATION",
        "claim_boundary": "synthetic_regression_fixture_only_not_market_measurement",
        "results": [
            {
                "node_id": derived_node["node_id"],
                "content_address": derived_node["content_address"],
                "raw_root_digest": root_digest,
            }
        ],
    }
    return {
        "raw.golden-macd-baseline-v1.json": raw_node,
        "validated.golden-macd-baseline-v1.json": validated_node,
        "derived.golden-macd.canonical-line-digest.v1.json": derived_node,
        "graph.json": graph,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write canonical synthetic lineage")
    args = parser.parse_args()
    try:
        expected = {
            filename: json.dumps(payload, indent=2, sort_keys=True) + "\n"
            for filename, payload in build().items()
        }
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"DAT-002: cannot establish source provenance: {exc}")
        return 2

    if args.write:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        for filename, text in expected.items():
            (OUTPUT_DIR / filename).write_text(text, encoding="utf-8")
        print(f"DAT-002: wrote {len(expected)} synthetic lineage files")
        return 0

    actual_files = {p.name for p in OUTPUT_DIR.glob("*.json")}
    if actual_files != set(expected):
        print(
            f"DAT-002: file set mismatch, absent={set(expected)-actual_files}, extra={actual_files-set(expected)}"
        )
        return 1
    for filename, text in expected.items():
        if (OUTPUT_DIR / filename).read_text(encoding="utf-8") != text:
            print(f"DAT-002: stale/tampered {filename}")
            return 1
    print("DAT-002: PASS, MIT synthetic MACD lineage matches bytes and manifests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
