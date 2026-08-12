# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tamper-evidence: the provenance manifest must match the committed artifacts.

Lightweight (hashlib + json, no heavy import) so it collects in the minimal
repo-integrity env. It recomputes the sha256 of every pinned artifact and the
provenance_root; any edit to an artifact without regenerating the manifest breaks
these — that is the content-addressed "signature".
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "artifacts" / "provenance" / "inference_provenance.json"
SCHEMA = ROOT / "audit" / "schema" / "inference_provenance.schema.json"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_validates_against_schema() -> None:
    manifest = _manifest()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert manifest["schema"] == schema["$id"]
    assert manifest["verdict"] == "PASS"
    try:
        import jsonschema
    except ImportError:
        return
    jsonschema.validate(manifest, schema)


def test_every_pinned_hash_matches_the_committed_artifact() -> None:
    for record in _manifest()["artifacts"]:
        path = ROOT / record["path"]
        assert path.is_file(), f"provenance references missing artifact: {record['path']}"
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == record["sha256"], f"tamper detected: {record['path']}"


def test_provenance_root_matches_the_chained_hashes() -> None:
    manifest = _manifest()
    records = sorted(manifest["artifacts"], key=lambda r: r["path"])
    chain = "\n".join(f"{r['path']}\t{r['sha256']}" for r in records)
    recomputed = hashlib.sha256(chain.encode("utf-8")).hexdigest()
    assert recomputed == manifest["provenance_root"]
