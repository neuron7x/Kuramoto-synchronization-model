# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Characterization (golden) test pinning default_contract_registry()'s output.

This locks the full registry snapshot so default_contract_registry can be
decomposed into per-category builders with zero behaviour change: the snapshot
must stay structurally identical. The model-derived ``*_digest`` fields are
stripped before comparison — they are sha256 hashes of the pydantic models
(not produced by this function, and they read as secrets to the supply-chain
scanner). Everything the registry function actually controls — names, paths,
versions, SLAs, policies — is locked by the JSON fixture.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from application.microservices.contracts import default_contract_registry

_FIXTURE = Path(__file__).with_name("contract_registry_golden.json")


def _strip_digests(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_digests(v) for k, v in obj.items() if "digest" not in k.lower()}
    if isinstance(obj, list):
        return [_strip_digests(x) for x in obj]
    return obj


def _live_snapshot() -> Any:
    raw = json.loads(json.dumps(default_contract_registry().snapshot(), default=str))
    return _strip_digests(raw)


def test_registry_matches_golden_snapshot() -> None:
    expected = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    assert _live_snapshot() == expected, (
        "default_contract_registry() output changed — the decomposition must be "
        "behaviour-preserving. If a contract change is intended, regenerate the "
        "fixture deliberately."
    )


def test_registry_snapshot_is_deterministic() -> None:
    assert _live_snapshot() == _live_snapshot()
