# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Closure tests for the DAT-001 dataset-manifest gate.

Stdlib-only + jsonschema. Loads the gate by path (tests/ci/pytest.ini keeps
these helper tests independent of the heavy repo-level conftest) and drives it
over isolated fixture manifests so both polarities are deterministic regardless
of what real datasets sit in the repo.

Polarity:
  POSITIVE — a valid manifest whose checksum matches an on-disk file -> exit 0.
  NEGATIVE — missing license -> RED; checksum mismatch vs file -> RED;
             unknown evidence_class -> RED.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

_GATE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_dataset_manifests.py"
_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "dataset_manifest.schema.json"


def _load_gate():
    spec = importlib.util.spec_from_file_location("check_dataset_manifests", _GATE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GATE = _load_gate()


def _write_dataset_file(root: Path, rel: str, payload: bytes) -> tuple[str, int]:
    fpath = root / rel
    fpath.parent.mkdir(parents=True, exist_ok=True)
    fpath.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest(), len(payload)


def _valid_manifest(root: Path, rel: str = "data/fix/toy.csv") -> dict:
    payload = b"ts,price\n1,100.0\n2,101.0\n"
    sha, nbytes = _write_dataset_file(root, rel, payload)
    files = [{"path": rel, "checksum_sha256": sha, "bytes": nbytes}]
    return {
        "manifest_version": "dataset_manifest.v1",
        "id": "toy-fixture-v1",
        "source": {
            "vendor": "neuron7xLab-generator",
            "origin": "repository_generated",
            "uri": None,
            "retrieval_method": "unit-test fixture",
        },
        "retrieval_time": "SYNTHETIC_GENERATED",
        "query": "unit-test synthetic fixture",
        "license": "MIT",
        "license_verified": True,
        "checksum": {"algorithm": "sha256", "value": GATE.dataset_digest(files)},
        "bytes": nbytes,
        "schema": {"format": "csv", "columns": ["ts", "price"], "description": "toy fixture"},
        "coverage": {"rows": 2, "start": None, "end": None, "description": "2 rows"},
        "revision_status": "FROZEN",
        "access_restrictions": "none",
        "evidence_class": "SIMULATION",
        "files": files,
    }


def _emit(tmp_path: Path, manifest: dict) -> tuple[Path, Path]:
    """Return (manifest_dir, root); root == tmp_path so file paths resolve."""
    mdir = tmp_path / "manifests"
    mdir.mkdir(parents=True, exist_ok=True)
    (mdir / f"{manifest['id']}.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return mdir, tmp_path


def _run(tmp_path: Path, manifest: dict) -> int:
    mdir, root = _emit(tmp_path, manifest)
    return GATE.main(
        ["--manifest-dir", str(mdir), "--root", str(root), "--schema", str(_SCHEMA_PATH)]
    )


# --------------------------------------------------------------------------- #
# POSITIVE
# --------------------------------------------------------------------------- #
def test_positive_valid_manifest_matches_on_disk_file(tmp_path: Path) -> None:
    """A valid manifest whose checksum matches an on-disk file -> exit 0 (GREEN)."""
    manifest = _valid_manifest(tmp_path)
    assert _run(tmp_path, manifest) == 0


# --------------------------------------------------------------------------- #
# NEGATIVE
# --------------------------------------------------------------------------- #
def test_negative_missing_license_is_red(tmp_path: Path) -> None:
    """A manifest declaring UNKNOWN license -> RED (fail-closed)."""
    manifest = _valid_manifest(tmp_path)
    manifest["license"] = "UNKNOWN"
    assert _run(tmp_path, manifest) == 1


def test_negative_empty_license_is_red(tmp_path: Path) -> None:
    """Empty license string is schema-invalid (minLength) and -> RED."""
    manifest = _valid_manifest(tmp_path)
    manifest["license"] = ""
    assert _run(tmp_path, manifest) == 1


def test_negative_public_no_license_is_red(tmp_path: Path) -> None:
    """PUBLIC_NO_LICENSE grants nothing -> RED."""
    manifest = _valid_manifest(tmp_path)
    manifest["license"] = "PUBLIC_NO_LICENSE"
    assert _run(tmp_path, manifest) == 1


def test_negative_checksum_mismatch_vs_file_is_red(tmp_path: Path) -> None:
    """On-disk bytes differing from the recorded checksum -> RED (tamper)."""
    manifest = _valid_manifest(tmp_path)
    # Corrupt the on-disk file after the manifest was built.
    (tmp_path / manifest["files"][0]["path"]).write_bytes(b"tampered,payload\n9,9\n")
    assert _run(tmp_path, manifest) == 1


def test_negative_unknown_evidence_class_is_red(tmp_path: Path) -> None:
    """An evidence_class outside the closed vocabulary -> RED."""
    manifest = _valid_manifest(tmp_path)
    manifest["evidence_class"] = "REAL_MARKET"
    assert _run(tmp_path, manifest) == 1


def test_negative_dataset_digest_tampered_is_red(tmp_path: Path) -> None:
    """A hand-edited dataset-level checksum not matching files[] -> RED."""
    manifest = _valid_manifest(tmp_path)
    manifest["checksum"]["value"] = "0" * 64
    assert _run(tmp_path, manifest) == 1


def test_negative_missing_manifest_dir_is_config_error(tmp_path: Path) -> None:
    """A missing manifest directory is a misconfiguration -> exit 2."""
    rc = GATE.main(
        [
            "--manifest-dir", str(tmp_path / "does_not_exist"),
            "--root", str(tmp_path),
            "--schema", str(_SCHEMA_PATH),
        ]
    )
    assert rc == 2


# --------------------------------------------------------------------------- #
# The shipped real-repo manifests: schema-valid, and the unlicensed real-data
# manifests correctly trip the fail-closed gate (the DAT-001 governance alarm).
# --------------------------------------------------------------------------- #
def test_repo_manifests_are_schema_valid() -> None:
    import jsonschema

    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    mdir = Path(__file__).resolve().parents[2] / "data" / "manifests"
    manifests = sorted(mdir.glob("*.json"))
    assert manifests, "no committed dataset manifests found"
    for mpath in manifests:
        doc = json.loads(mpath.read_text(encoding="utf-8"))
        errors = list(validator.iter_errors(doc))
        assert not errors, f"{mpath.name}: {[e.message for e in errors]}"


def test_repo_real_data_manifests_are_flagged_and_red() -> None:
    """Every committed real-data (MEASURED) manifest must be flagged + unlicensed."""
    mdir = Path(__file__).resolve().parents[2] / "data" / "manifests"
    measured = []
    for mpath in sorted(mdir.glob("*.json")):
        doc = json.loads(mpath.read_text(encoding="utf-8"))
        if doc.get("evidence_class") == "MEASURED":
            measured.append(doc)
            assert "REAL_DATA_CONTRADICTS_SYNTHETIC_ONLY_BOUNDARY" in (doc.get("flags") or []), (
                f"{mpath.name}: real data must carry the boundary-violation flag"
            )
            assert str(doc["license"]).strip().lower() in GATE.UNLICENSED_TOKENS, (
                f"{mpath.name}: real data is not yet licensed-cleared (SEC-015)"
            )
    assert measured, "expected at least one MEASURED real-data manifest to exist"


@pytest.mark.parametrize("token", ["", "unknown", "unlicensed", "none", "tbd", "public_no_license"])
def test_unlicensed_token_vocabulary(token: str) -> None:
    assert token in GATE.UNLICENSED_TOKENS


# --------------------------------------------------------------------------- #
# DS-10 — evidence-class provenance consistency.
# Relabeling repository-generated / synthetic data as real-world FACT/MEASURED
# is a provable lie contradicting the manifest's own provenance fields.
# --------------------------------------------------------------------------- #
def _real_world_manifest(root: Path, rel: str = "data/fix/real.csv") -> dict:
    """A genuinely real-world (MEASURED) manifest with a granted license -> GREEN."""
    payload = b"ts,price\n1,100.0\n2,101.0\n"
    sha, nbytes = _write_dataset_file(root, rel, payload)
    files = [{"path": rel, "checksum_sha256": sha, "bytes": nbytes}]
    return {
        "manifest_version": "dataset_manifest.v1",
        "id": "real-fixture-v1",
        "source": {
            "vendor": "SomeExchange",
            "origin": "exchange_public",
            "uri": "https://example.com/depth",
            "retrieval_method": "public REST capture",
        },
        "retrieval_time": "2026-06-20T00:00:00Z",
        "query": "EXCHANGE_DEPTH symbol=BTCUSDT limit=10",
        "license": "MIT",
        "license_verified": True,
        "checksum": {"algorithm": "sha256", "value": GATE.dataset_digest(files)},
        "bytes": nbytes,
        "schema": {"format": "csv", "columns": ["ts", "price"], "description": "real fixture"},
        "coverage": {"rows": 2, "start": None, "end": None, "description": "2 rows"},
        "revision_status": "FROZEN",
        "access_restrictions": "none",
        "evidence_class": "MEASURED",
        "files": files,
    }


def test_ds10_simulation_relabeled_fact_is_red(tmp_path: Path) -> None:
    """SIMULATION->FACT inversion on a synthetic-origin manifest -> RED."""
    manifest = _valid_manifest(tmp_path)  # synthetic markers (repository_generated, etc.)
    manifest["evidence_class"] = "FACT"
    assert _run(tmp_path, manifest) == 1


def test_ds10_simulation_relabeled_measured_is_red(tmp_path: Path) -> None:
    """SIMULATION->MEASURED inversion on a synthetic-origin manifest -> RED."""
    manifest = _valid_manifest(tmp_path)
    manifest["evidence_class"] = "MEASURED"
    assert _run(tmp_path, manifest) == 1


def test_ds10_synthetic_retrieval_time_marker_alone_trips_inversion(tmp_path: Path) -> None:
    """Even if origin is scrubbed, the SYNTHETIC_GENERATED retrieval_time betrays it."""
    manifest = _valid_manifest(tmp_path)
    manifest["source"]["origin"] = "exchange_public"  # try to hide the origin
    manifest["query"] = "totally legit real capture"  # scrub the query marker
    manifest["evidence_class"] = "FACT"
    # retrieval_time is still SYNTHETIC_GENERATED -> still caught.
    assert _run(tmp_path, manifest) == 1


def test_ds10_generator_query_marker_alone_trips_inversion(tmp_path: Path) -> None:
    """A generator-script invocation left in `query` betrays a FACT claim."""
    manifest = _valid_manifest(tmp_path)
    manifest["source"]["origin"] = "exchange_public"
    manifest["retrieval_time"] = "2026-06-20T00:00:00Z"
    manifest["query"] = "python scripts/generate_sample_ohlcv.py --seed 42"
    manifest["evidence_class"] = "FACT"
    assert _run(tmp_path, manifest) == 1


def test_ds10_legitimate_simulation_still_green(tmp_path: Path) -> None:
    """A correctly-labeled SIMULATION with synthetic markers stays GREEN."""
    manifest = _valid_manifest(tmp_path)  # evidence_class already SIMULATION
    assert _run(tmp_path, manifest) == 0


def test_ds10_legitimate_real_world_measured_still_green(tmp_path: Path) -> None:
    """A genuinely real-world MEASURED manifest (no synthetic markers) stays GREEN."""
    manifest = _real_world_manifest(tmp_path)
    assert _run(tmp_path, manifest) == 0


def test_ds10_marker_helper_detects_all_three_signals() -> None:
    """Unit: synthetic_origin_markers surfaces origin, retrieval_time, and query."""
    doc = {
        "source": {"origin": "repository_generated"},
        "retrieval_time": "SYNTHETIC_GENERATED",
        "query": "python scripts/generate_sample_ohlcv.py --seed 42",
    }
    markers = GATE.synthetic_origin_markers(doc)
    assert len(markers) == 3
    doc_clean = {
        "source": {"origin": "exchange_public"},
        "retrieval_time": "2026-06-20T00:00:00Z",
        "query": "EXCHANGE_DEPTH symbol=BTCUSDT",
    }
    assert GATE.synthetic_origin_markers(doc_clean) == []
