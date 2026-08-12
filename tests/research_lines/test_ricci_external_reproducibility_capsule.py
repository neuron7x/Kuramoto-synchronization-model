# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""External-reproducibility-block guard for the ricci_microstructure_v1 line.

PR #998 added an ``external_reproducibility`` block to the line contract that
declares a credential-free public fallback (a placeholder artifact + a replay
command). Nothing tested that block, so the declared fallback could silently
rot (artifact deleted, replay command renamed) or — worse — be quietly upgraded
into a real-reproducibility claim by swapping in non-zero hashes. Doctrine:
``No public fallback -> No external reproducibility``.

This capsule pins the block, deterministically and without private data:

  1. the declared fallback artifact exists and replays cleanly via the exact
     command recorded in the contract (V4 external reproducibility / V2 replay);
  2. that artifact is provably a *placeholder* — zero data/git hashes, HYPOTHESIS
     tier, NOT_RUN falsification — so it can never masquerade as a promotable
     real result (V9 negative-evidence preservation);
  3. the contract keeps the fallback honest: ``status: PARTIAL`` with
     ``fallback_quality: PUBLIC_PLACEHOLDER`` and the synthetic ceiling pinned at
     ``INSTRUMENTED`` (V1 claim safety / promotion blocker).

Fail interpretation: any drift here means the public fallback changed shape —
review before trusting anything downstream of this line. Fail closed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tools.research import validate_ricci_artifact_schema

_ROOT = Path(__file__).resolve().parents[2]
_LINE = _ROOT / "research_lines" / "ricci_microstructure_v1"
_CONTRACT = _LINE / "contract.yaml"


def _contract() -> dict[str, Any]:
    return yaml.safe_load(_CONTRACT.read_text(encoding="utf-8"))


def _external_repro() -> dict[str, Any]:
    block = _contract().get("external_reproducibility")
    assert isinstance(block, dict), "contract is missing the external_reproducibility block"
    return block


def test_fallback_is_declared_partial_public_placeholder() -> None:
    """The fallback must stay an honest, non-promoting public placeholder."""
    block = _external_repro()
    assert block.get("status") == "PARTIAL", (
        "external_reproducibility.status must remain PARTIAL — a placeholder "
        "fallback cannot claim FULL external reproducibility for the L2 claim."
    )
    assert block.get("fallback_quality") == "PUBLIC_PLACEHOLDER", (
        "fallback_quality must stay PUBLIC_PLACEHOLDER until a real, hash-pinned "
        "order-book session is committed."
    )


def test_synthetic_ceiling_blocks_promotion() -> None:
    """The placeholder fallback must not lift the synthetic maturity ceiling."""
    limits = _contract().get("promotion_limits", {})
    assert (
        limits.get("synthetic_max_state") == "INSTRUMENTED"
    ), "synthetic_max_state must remain INSTRUMENTED; placeholders never promote a claim."
    assert (
        _contract().get("state") == "INSTRUMENTED"
    ), "line state must remain INSTRUMENTED while only synthetic evidence exists."


def test_declared_fallback_artifact_replays_clean() -> None:
    """The artifact named in the contract must exist and pass its replay command."""
    block = _external_repro()
    artifact_rel = block.get("public_or_cached_input")
    assert isinstance(artifact_rel, str) and artifact_rel, "missing public_or_cached_input path"
    artifact = _ROOT / artifact_rel
    assert artifact.is_file(), f"declared fallback artifact does not exist: {artifact_rel}"

    # Replay via the exact tool the contract's replay_command names; exit 0 means
    # the public, credential-free fallback path is intact and schema+semantic valid.
    rc = validate_ricci_artifact_schema.main(["--semantic", "--artifact", str(artifact)])
    assert rc == 0, "declared replay_command failed on the public fallback artifact"


def test_fallback_artifact_is_a_zero_hash_placeholder() -> None:
    """Negative-evidence preservation: the fallback can never look like real data."""
    import json

    block = _external_repro()
    artifact = _ROOT / block["public_or_cached_input"]
    payload = json.loads(artifact.read_text(encoding="utf-8"))

    assert payload.get("artifact_role") == "placeholder"
    assert payload.get("score_source") == "placeholder"
    assert payload.get("claim_tier") == "HYPOTHESIS"
    assert payload.get("falsification_status") == "NOT_RUN"
    # Zero provenance hashes are the structural proof that no real session backs
    # this artifact. If any of these become non-zero, promotion logic must be
    # re-reviewed before the artifact is trusted — so fail closed here.
    assert payload.get("data_sha256") == "0" * 64, "placeholder must carry a zero data_sha256"
    assert payload.get("git_sha") == "0" * 40, "placeholder must carry a zero git_sha"
    assert float(payload.get("score", -1.0)) == 0.0, "placeholder score must be exactly 0.0"
