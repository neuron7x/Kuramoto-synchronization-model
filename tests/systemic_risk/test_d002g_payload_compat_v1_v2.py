# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""v1/v2 ``NullAuditCellPayload`` sha branching compatibility.

Contract
--------
* A v1 payload (``payload_schema`` absent OR ``=PAYLOAD_SCHEMA_V1``) has
  a sha computed over the legacy 12-field sha input — back-compatible
  with pre-D-002G emissions on disk.
* A v2 payload (``payload_schema=PAYLOAD_SCHEMA_V2``) has a sha that
  also includes ``null_strategy`` + ``null_seed`` — the D-002G data
  contract.
* v1 and v2 with otherwise identical scientific fields produce
  DIFFERENT shas.
* Both shapes round-trip through ``from_payload_dict`` without sha
  mismatch.
* A v1 dict loaded into the v2 class still reads as v1 (mixed-mode
  loader); a v2 dict cannot be silently downgraded to v1.
"""

from __future__ import annotations

import hashlib

from research.systemic_risk.d002c_preflight import canonical_preflight_json
from research.systemic_risk.d002c_sweep_runner import (
    DEFAULT_NULL_STRATEGY,
    PAYLOAD_SCHEMA_V1,
    PAYLOAD_SCHEMA_V2,
    NullAuditCellPayload,
)


def _make_payload(schema: str, null_strategy: str, null_seed: int | None) -> NullAuditCellPayload:
    sha_input = {
        "cell_key": "compat",
        "N": 50,
        "lambda_": 0.5,
        "substrate_id": "ricci_flow",
        "metric_id": "sync_auc",
        "seed_ids": list(range(20)),
        "precursor_values": [float(i) * 0.1 for i in range(20)],
        "null_values": [float(i) * 0.05 for i in range(20)],
        "paired_by_seed": True,
        "crn_identity_hash": "compat-hash",
        "metric_version": "mv",
        "substrate_version": "sv",
    }
    if schema == PAYLOAD_SCHEMA_V2:
        sha_input["payload_schema"] = schema
        sha_input["null_strategy"] = null_strategy
        sha_input["null_seed"] = null_seed
    sha = hashlib.sha256(canonical_preflight_json(sha_input).encode("utf-8")).hexdigest()
    return NullAuditCellPayload(
        cell_key="compat",
        N=50,
        lambda_=0.5,
        substrate_id="ricci_flow",
        metric_id="sync_auc",
        seed_ids=tuple(range(20)),
        precursor_values=tuple(float(i) * 0.1 for i in range(20)),
        null_values=tuple(float(i) * 0.05 for i in range(20)),
        paired_by_seed=True,
        crn_identity_hash="compat-hash",
        metric_version="mv",
        substrate_version="sv",
        generated_at="",
        sha256=sha,
        payload_schema=schema,
        null_strategy=null_strategy,
        null_seed=null_seed,
    )


def test_v1_payload_roundtrips_with_legacy_sha() -> None:
    v1 = _make_payload(PAYLOAD_SCHEMA_V1, DEFAULT_NULL_STRATEGY, None)
    d = v1.to_payload_dict()
    assert "payload_schema" not in d, (
        "v1 to_payload_dict must omit payload_schema for byte-exact "
        f"legacy compatibility; got {sorted(d)}"
    )
    loaded = NullAuditCellPayload.from_payload_dict(d)
    assert loaded.sha256 == v1.sha256
    assert loaded.payload_schema == PAYLOAD_SCHEMA_V1
    assert loaded.null_strategy == DEFAULT_NULL_STRATEGY
    assert loaded.null_seed is None


def test_v2_payload_roundtrips_with_extended_sha() -> None:
    v2 = _make_payload(PAYLOAD_SCHEMA_V2, "M1_INDEPENDENT_SEED", 42)
    d = v2.to_payload_dict()
    assert d["payload_schema"] == PAYLOAD_SCHEMA_V2
    assert d["null_strategy"] == "M1_INDEPENDENT_SEED"
    assert d["null_seed"] == 42
    loaded = NullAuditCellPayload.from_payload_dict(d)
    assert loaded.sha256 == v2.sha256
    assert loaded.payload_schema == PAYLOAD_SCHEMA_V2
    assert loaded.null_strategy == "M1_INDEPENDENT_SEED"
    assert loaded.null_seed == 42


def test_v1_and_v2_shas_differ_on_same_scientific_fields() -> None:
    v1 = _make_payload(PAYLOAD_SCHEMA_V1, DEFAULT_NULL_STRATEGY, None)
    v2 = _make_payload(PAYLOAD_SCHEMA_V2, "M1_INDEPENDENT_SEED", 42)
    differ = v1.sha256 != v2.sha256
    msg = "v1 and v2 shas must differ when v2 carries non-default null_strategy/null_seed"
    assert differ, msg


def test_mixed_mode_loader_reads_both_schemas() -> None:
    """v1 dicts and v2 dicts both load through the same classmethod."""
    v1 = _make_payload(PAYLOAD_SCHEMA_V1, DEFAULT_NULL_STRATEGY, None)
    v2 = _make_payload(PAYLOAD_SCHEMA_V2, "M6_PLACEBO_COUPLING", 100043)
    for orig in (v1, v2):
        loaded = NullAuditCellPayload.from_payload_dict(orig.to_payload_dict())
        assert loaded == orig, (
            f"mixed-mode loader lost a field for {orig.payload_schema!r}; "
            f"loaded={loaded!r} orig={orig!r}"
        )
