# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Cross-artifact coherence of the D-002H authorisation chain.

The Gate F authorisation grant and the Gate G terminal final-lock each carry the
same shared facts — the A..E gate anchor shas, the D-002C ledger pin, the D-002H
prereg pin, the conjunction string. Today each grant is checked only against the
*hardcoded constants in its own gate test*; the two grants are never compared to
each other. So a re-anchor that updates one grant (and its test's constants) but
not the other would leave the grants mutually inconsistent while both gate tests
still pass — a silent duplication-drift in the authorisation chain.

This gate reads both grants from disk and asserts they AGREE directly (no
hardcoded shas here — it is single-source-by-comparison), and that the embedded
prereg pin points at the real on-disk prereg. It does not grant, weaken, or
re-verify authorisation; it refuses an internally incoherent chain.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTH_DIR = REPO_ROOT / "artifacts" / "d002h" / "authorization"
GATE_F = AUTH_DIR / "d002h_canonical_run_authorisation.json"
GATE_G = AUTH_DIR / "d002h_canonical_run_final_lock.json"
PREREG_RELPATH = "docs/governance/D002H_PREREGISTRATION.yaml"


def _load(path: Path) -> dict[str, Any]:
    assert path.is_file(), f"authorisation grant missing: {path}"
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return payload


def _anchors(chain: list[dict[str, Any]]) -> dict[str, str]:
    return {str(e["gate"]): str(e["anchor_sha"]) for e in chain if "anchor_sha" in e}


def test_ae_anchor_shas_agree_across_grants() -> None:
    """Each gate present in both grants must carry an identical anchor sha."""
    f_anchors = _anchors(_load(GATE_F)["prior_gate_chain"])
    g_anchors = _anchors(_load(GATE_G)["gate_chain"])
    shared = sorted(set(f_anchors) & set(g_anchors))
    assert shared, "no shared gates between the two grants — chain is malformed"
    for gate in shared:
        assert f_anchors[gate] == g_anchors[gate], (
            f"gate {gate} anchor drift across grants: "
            f"Gate-F={f_anchors[gate]!r} vs Gate-G={g_anchors[gate]!r}"
        )


def test_ledger_pin_agrees_across_grants() -> None:
    f = _load(GATE_F)["d002c_ledger_byte_exact_at_gate_e"]
    g = _load(GATE_G)["d002c_ledger_byte_exact"]
    assert f == g, f"D-002C ledger pin drift across grants: Gate-F={f!r} vs Gate-G={g!r}"


def test_prereg_pin_agrees_across_grants() -> None:
    f = _load(GATE_F)["d002h_prereg_byte_exact"]
    g = _load(GATE_G)["d002h_prereg_byte_exact"]
    assert f == g, f"D-002H prereg pin drift across grants: Gate-F={f!r} vs Gate-G={g!r}"


def test_embedded_prereg_pin_points_at_real_disk_file() -> None:
    """The grants' self-declared prereg pin must equal the on-disk prereg sha256.

    Closes the loop the per-gate tests leave open: they compare a hardcoded
    constant to disk; this compares the GRANT's own embedded pin to disk, so a
    grant that embeds a wrong pin is caught.
    """
    embedded = _load(GATE_G)["d002h_prereg_byte_exact"]
    disk = hashlib.sha256((REPO_ROOT / PREREG_RELPATH).read_bytes()).hexdigest()
    assert embedded == disk, (
        f"grant prereg pin {embedded!r} does not match on-disk prereg {disk!r} "
        f"at {PREREG_RELPATH}"
    )


def test_conjunction_required_agrees_across_grants() -> None:
    f = _load(GATE_F)["conjunction_required"]
    g = _load(GATE_G)["conjunction_required"]
    assert f == g, f"conjunction_required drift across grants: Gate-F={f!r} vs Gate-G={g!r}"
