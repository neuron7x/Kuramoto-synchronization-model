# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Closure tests for the DAT-002 data-lineage gate.

Stdlib-only. Loads the gate by path (tests/ci/pytest.ini keeps these helper
tests independent of the heavy repo-level conftest) and drives it over isolated
fixture manifests + lineage graphs so both polarities are deterministic
regardless of what real lineage sits in the repo.

Polarity:
  POSITIVE — a valid raw -> validated -> derived chain whose result traces back
             to a raw DAT-001 digest, with a registered transform reproduced on
             rerun -> exit 0 (GREEN).
  NEGATIVE — a derived node with a dangling parent digest -> RED;
             a raw node that claims inputs -> RED;
             a cycle in the lineage graph -> RED.

Plus a determinism assertion: rerunning the registered transform on the same
raw bytes yields the same output digest (same content-address), and the shipped
repo lineage is GREEN and traces to a raw digest.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_GATE_PATH = _ROOT / "scripts" / "ci" / "check_data_lineage.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("check_data_lineage", _GATE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GATE = _load_gate()

VERSION = "data_lineage.v1"
_RAW_PAYLOAD = b"ts,close\n1,100.0\n2,101.0\n3,102.5\n"
_RAW_REL = "data/fix/toy_raw.csv"


def _seed_manifest(root: Path, digest: str) -> None:
    """Write a minimal DAT-001-shaped manifest + its on-disk raw file."""
    (root / _RAW_REL).parent.mkdir(parents=True, exist_ok=True)
    (root / _RAW_REL).write_bytes(_RAW_PAYLOAD)
    mdir = root / "data" / "manifests"
    mdir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "id": "toy-raw-v1",
        "checksum": {"algorithm": "sha256", "value": digest},
        "evidence_class": "SIMULATION",
        "files": [{"path": _RAW_REL, "checksum_sha256": hashlib.sha256(_RAW_PAYLOAD).hexdigest(),
                   "bytes": len(_RAW_PAYLOAD)}],
    }
    (mdir / "toy-raw-v1.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _write_node(lineage_dir: Path, node: dict) -> None:
    lineage_dir.mkdir(parents=True, exist_ok=True)
    (lineage_dir / f"{node['node_id']}.json").write_text(
        json.dumps(node, indent=2), encoding="utf-8"
    )


def _build_valid_graph(root: Path) -> tuple[Path, dict, dict, dict]:
    """Materialise a raw -> validated -> derived chain. Returns (lineage_dir, nodes...)."""
    raw_digest = "a" * 64  # arbitrary but stable; the manifest declares the same value
    _seed_manifest(root, raw_digest)
    lineage_dir = root / "data" / "lineage"

    raw = {
        "lineage_version": VERSION,
        "node_id": "raw.toy-raw-v1",
        "tier": "raw",
        "manifest_ref": "toy-raw-v1",
        "content_address": raw_digest,
        "inputs": [],
        "transform": None,
    }
    validated = {
        "lineage_version": VERSION,
        "node_id": "validated.toy",
        "tier": "validated",
        "inputs": [raw_digest],
        "transform": {"id": "validate.schema_and_checksum.v1", "params": {"checks": ["digest"]}},
        "validation": {"verdict": "accepted", "reason": "digest ok"},
    }
    validated["content_address"] = GATE.content_address(validated)

    output_sha256 = GATE._t_canonical_line_digest(_RAW_PAYLOAD)
    derived = {
        "lineage_version": VERSION,
        "node_id": "derived.toy.canon",
        "tier": "derived",
        "inputs": [validated["content_address"]],
        "transform": {
            "id": "transform.canonical_line_digest.v1",
            "params": {"encoding": "utf-8"},
            "output_sha256": output_sha256,
        },
    }
    derived["content_address"] = GATE.content_address(derived)

    for node in (raw, validated, derived):
        _write_node(lineage_dir, node)

    graph = {
        "lineage_version": VERSION,
        "results": [{"node_id": derived["node_id"],
                     "content_address": derived["content_address"],
                     "raw_root_digest": raw_digest}],
    }
    (lineage_dir / "graph.json").write_text(json.dumps(graph, indent=2), encoding="utf-8")
    return lineage_dir, raw, validated, derived


def _run(root: Path) -> int:
    return GATE.main([
        "--lineage-dir", str(root / "data" / "lineage"),
        "--manifest-dir", str(root / "data" / "manifests"),
        "--root", str(root),
    ])


# --------------------------------------------------------------------------- #
# POSITIVE
# --------------------------------------------------------------------------- #
def test_positive_raw_validated_derived_chain_resolves_to_raw(tmp_path: Path) -> None:
    """A valid raw->validated->derived chain tracing to a raw digest -> exit 0."""
    _build_valid_graph(tmp_path)
    assert _run(tmp_path) == 0


def test_positive_transform_is_deterministic_on_rerun() -> None:
    """Same inputs+transform reproduce the same content-address (determinism)."""
    first = GATE._t_canonical_line_digest(_RAW_PAYLOAD)
    second = GATE._t_canonical_line_digest(_RAW_PAYLOAD)
    assert first == second
    node = {
        "tier": "derived",
        "inputs": ["b" * 64],
        "transform": {"id": "transform.canonical_line_digest.v1", "output_sha256": first},
    }
    assert GATE.content_address(node) == GATE.content_address(dict(node))


# --------------------------------------------------------------------------- #
# NEGATIVE
# --------------------------------------------------------------------------- #
def test_negative_dangling_parent_is_red(tmp_path: Path) -> None:
    """A derived node whose parent digest resolves to nothing -> RED."""
    lineage_dir, _raw, _validated, derived = _build_valid_graph(tmp_path)
    derived["inputs"] = ["f" * 64]  # dangling: no node, no manifest has this digest
    derived["content_address"] = GATE.content_address(derived)
    _write_node(lineage_dir, derived)
    graph = json.loads((lineage_dir / "graph.json").read_text())
    graph["results"][0]["content_address"] = derived["content_address"]
    (lineage_dir / "graph.json").write_text(json.dumps(graph, indent=2), encoding="utf-8")
    assert _run(tmp_path) == 1


def test_negative_raw_node_with_inputs_is_red(tmp_path: Path) -> None:
    """A raw node that claims inputs violates immutability of the root -> RED."""
    lineage_dir, raw, _validated, _derived = _build_valid_graph(tmp_path)
    raw["inputs"] = ["c" * 64]
    _write_node(lineage_dir, raw)
    assert _run(tmp_path) == 1


def test_negative_cycle_is_red(tmp_path: Path, capsys) -> None:
    """A cycle in the lineage graph -> RED (and the cycle is reported)."""
    raw_digest = "a" * 64
    _seed_manifest(tmp_path, raw_digest)
    lineage_dir = tmp_path / "data" / "lineage"
    # Two nodes referencing each other's declared address form a cycle.
    addr_a, addr_b = "1" * 64, "2" * 64
    node_a = {"lineage_version": VERSION, "node_id": "d.a", "tier": "derived",
              "content_address": addr_a, "inputs": [addr_b],
              "transform": {"id": "t", "output_sha256": "x"}}
    node_b = {"lineage_version": VERSION, "node_id": "d.b", "tier": "derived",
              "content_address": addr_b, "inputs": [addr_a],
              "transform": {"id": "t", "output_sha256": "y"}}
    _write_node(lineage_dir, node_a)
    _write_node(lineage_dir, node_b)
    graph = {"lineage_version": VERSION,
             "results": [{"node_id": "d.a", "content_address": addr_a}]}
    (lineage_dir / "graph.json").write_text(json.dumps(graph, indent=2), encoding="utf-8")
    rc = _run(tmp_path)
    out = capsys.readouterr()
    assert rc == 1
    assert "CYCLE" in (out.out + out.err)


def test_negative_missing_lineage_dir_is_config_error(tmp_path: Path) -> None:
    """A missing lineage directory is a misconfiguration -> exit 2."""
    (tmp_path / "data" / "manifests").mkdir(parents=True, exist_ok=True)
    rc = GATE.main([
        "--lineage-dir", str(tmp_path / "data" / "lineage"),
        "--manifest-dir", str(tmp_path / "data" / "manifests"),
        "--root", str(tmp_path),
    ])
    assert rc == 2


def test_negative_tampered_content_address_is_red(tmp_path: Path) -> None:
    """A derived node not honestly content-addressed -> RED."""
    lineage_dir, _raw, _validated, derived = _build_valid_graph(tmp_path)
    derived["content_address"] = "0" * 64  # not hash(inputs+transform)
    _write_node(lineage_dir, derived)
    assert _run(tmp_path) == 1


# --------------------------------------------------------------------------- #
# Shipped repo lineage: GREEN and traces to a raw DAT-001 digest.
# --------------------------------------------------------------------------- #
def test_repo_lineage_is_green_and_traces_to_raw() -> None:
    rc = GATE.main([])  # defaults resolve to the shipped data/lineage + data/manifests
    assert rc == 0


def test_repo_result_traces_to_a_manifest_digest() -> None:
    lineage_dir = _ROOT / "data" / "lineage"
    graph = json.loads((lineage_dir / "graph.json").read_text(encoding="utf-8"))
    manifest_digests = set(
        GATE.load_manifest_digests(_ROOT / "data" / "manifests").values()
    )
    assert graph["results"], "repo lineage declares no result"
    for res in graph["results"]:
        assert res["raw_root_digest"] in manifest_digests
