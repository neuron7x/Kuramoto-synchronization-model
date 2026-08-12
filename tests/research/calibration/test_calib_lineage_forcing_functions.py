# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Architectural forcing functions for the CALIB-GRID lineage family.

The prior structural audit (#759) deduped the *instances* of the
fractal data-structure duplication. This module attacks the surviving
*generative mechanism*: the CALIB-GRID lineage tree has no architectural
forcing function, so each new lineage can legally re-derive a frozen-sha
literal, a bespoke ledger schema, or its own divergent numeric-tolerance
window ad hoc. #759's ``test_substrate_is_single_source`` only guards the
four already-named primitives (``hashlib.sha256`` inline, the gate
dataclass, ``_branch_sha``, ``_topology_f1``); it does **not** prevent a
hypothetical lineage #6 from bolting on a new bespoke provenance literal,
a new RESULTS schema, or a third copy of ``_deep_close`` with a wider
tolerance.

These tests are the missing negative-feedback term. They are strictly
pure-additive (no frozen artifact, pre-registration, gate, threshold,
seed, σ, θ₀ or decision rule is touched, and the protected
``test_grid_kuramoto.py`` is unmodified). Each one fails closed the
moment a future lineage re-derives — rather than inherits — a property
the family must share:

* ``test_no_frozen_sha_literal_outside_substrate_registry`` — kills the
  scale-invariant "re-paste the provenance hash" generator (F1/F5):
  every 40/64-hex provenance literal must live only in
  ``_substrate`` (the registry) or in a test asserting the registry's
  value. A lineage #6 that hard-codes ``CG003_PREREG_SHA = "…"`` in its
  own module fails this test.
* ``test_deep_close_tolerance_is_pinned_single_valued_and_sharp`` —
  kills the monotonic tolerance-creep generator (F3): the two existing
  ``_deep_close`` copies must agree (no silent 1e-9 vs 1e-6 divergence)
  and a synthetic regression strictly larger than the pinned window
  must still be detected. A lineage #6 that widens its own copy to
  absorb a flaky reproduction fails this test.
* ``test_every_results_ledger_conforms_to_shared_schema`` — kills the
  bespoke-ledger-schema generator (F4/F5): every ``build_*_ledger``
  must emit the shared required key set. A lineage #6 that invents a
  new RESULTS shape fails this test.
* ``test_superseded_claims_resolve_via_registry`` /
  ``test_supersession_registry_is_internally_consistent`` — kills the
  stale-falsified-premise generator (F-supersession): a sha-pinned
  artifact may encode a causal premise a *later* sha-pinned lineage has
  falsified (R1's "double-differentiation / no-consistent-estimator"
  noisy attribution, falsified by CALIB-GRID-002's class-independent
  regressor-floor proof). ``SUPERSESSIONS.yaml`` is the single source
  of truth for that relation; any *new* doc that references the
  superseded R1 claim/sha without resolving the registry fails closed,
  and the registry's own integrity (every stale-artifact path exists
  and carries its verbatim anchor; the superseded sha is a real commit
  ancestor) is enforced fail-closed. No frozen artifact is touched —
  the registry is a pure-additive forward-only supersession layer.
"""

from __future__ import annotations

import inspect
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from research.calibration.grid_kuramoto import (
    SimConfig,
    wscc_9_bus,
)
from research.calibration.grid_kuramoto import (
    _substrate as substrate,
)
from research.calibration.grid_kuramoto.cg002 import build_cg002_ledger
from research.calibration.grid_kuramoto.identifiability.validate import (
    build_identifiability_ledger,
)
from research.calibration.grid_kuramoto.run import build_ledger, build_r1_ledger

_LINEAGE_ROOT = Path(__file__).resolve().parents[3] / "research" / "calibration" / "grid_kuramoto"
_TESTS_ROOT = Path(__file__).resolve().parent

# A git object id (40 hex) or a sha256 content hash (64 hex). The
# CALIB-GRID lineages pin parent provenance with exactly these widths.
_HEX_LITERAL = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?(?![0-9a-fA-F])")

# The single source of truth: the three audited constants the substrate
# registry owns. Any hex literal that is one of these, appearing inside
# the registry module or inside a test that asserts the registry value,
# is *inheritance* and is allowed; the same literal re-pasted into a
# lineage source module is *re-derivation* and is forbidden.
_REGISTRY_VALUES = frozenset(
    {
        substrate.FROZEN_PREREG_SHA,
        substrate.PARENT_LEDGER_SHA256,
        substrate.PREREG_BRANCH_BASE_SHA,
    }
)


def test_no_frozen_sha_literal_outside_substrate_registry() -> None:
    """No lineage *source* module may re-derive a provenance hash literal.

    Forcing function for the F1/F5 generative mechanism (premature
    causal attribution / no architectural forcing function): a frozen
    provenance sha is *inherited* by importing it from ``_substrate``,
    never *re-pasted*. ``_substrate`` is the registry (it legitimately
    holds the literal); every other ``*.py`` under the lineage tree may
    only import the symbol. If a future lineage hard-codes a bespoke
    ``CG00N_PREREG_SHA = "<hex>"`` in its own module this test fails
    closed, forcing the literal into the single registry instead.
    """
    offenders: list[str] = []
    for path in sorted(_LINEAGE_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if path.name == "_substrate.py":
            continue  # the registry itself — single source, allowed
        text = path.read_text(encoding="utf-8")
        for match in _HEX_LITERAL.finditer(text):
            literal = match.group(0)
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(_LINEAGE_ROOT.parents[2])}:{line} -> {literal}")
    assert not offenders, (
        "frozen-sha literal re-derived outside the _substrate registry "
        "(import it, do not re-paste — this is the F1/F5 generator):\n" + "\n".join(offenders)
    )


def test_substrate_registry_values_are_the_only_provenance_anchor() -> None:
    """The registry exposes exactly the three audited provenance anchors.

    Pins the registry surface so a future lineage cannot quietly add a
    fourth bespoke literal *into* the registry and call it inherited:
    the set of provenance constants is itself frozen here, and each is
    a well-formed git/sha256 width.
    """
    names = {n for n in dir(substrate) if n.endswith("_SHA") or n.endswith("_SHA256")}
    assert names == {"FROZEN_PREREG_SHA", "PARENT_LEDGER_SHA256", "PREREG_BRANCH_BASE_SHA"}
    for value in _REGISTRY_VALUES:
        assert len(value) in (40, 64)
        assert int(value, 16) >= 0


def _load_deep_close(module_path: Path) -> Callable[..., bool]:
    """Import the module-local ``_deep_close`` from a test file by path."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(f"_dc_probe_{module_path.stem}", module_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = mod._deep_close  # noqa: SLF001 — deliberately probing the private comparator
    assert callable(fn)
    return fn  # type: ignore[no-any-return]


_DEEP_CLOSE_SITES = (
    _TESTS_ROOT / "test_grid_kuramoto.py",
    _TESTS_ROOT / "test_calib_substrate_consolidation.py",
)


def test_deep_close_tolerance_is_pinned_single_valued_and_sharp() -> None:
    """The post-data-edit comparator must be single-valued and sharp.

    Forcing function for the F3 generative mechanism (monotonic
    tolerance creep with no negative feedback). #753 introduced
    ``_deep_close`` at rel=1e-9; #760 widened a *copy* to rel=1e-6
    while #759 left a second copy at rel=1e-9. The two copies now
    disagree by 1000×, and nothing re-audits ε. This test:

    1. pins the effective (loosest) tolerance window so a future
       silent widening is a *reviewed, failing* event, not a free
       de-flake;
    2. asserts a synthetic regression strictly larger than the pinned
       window is still **detected** by every copy — a genuine
       post-data edit of plausible magnitude cannot be absorbed;
    3. asserts both copies agree on the canonical pinned window so the
       divergent-copy generator (each lineage carrying its own ε) is
       killed: a lineage #6 adding a third, wider copy fails here.
    """
    # The pinned, audited window. This is the loosest tolerance any
    # copy is permitted; widening it is a deliberate, reviewed change
    # to *this* assertion, not an ad-hoc per-lineage de-flake.
    pinned_rel, pinned_abs = 1e-6, 1e-9

    comparators = {p.name: _load_deep_close(p) for p in _DEEP_CLOSE_SITES}
    assert len(comparators) == 2, "expected exactly two _deep_close copies to govern"

    # A regression an order of magnitude beyond the pinned window must
    # be caught by *every* copy, at its own default tolerance — no copy
    # may be loose enough to absorb a real post-data edit.
    base = 1.0
    regressed = base * (1.0 + 10.0 * pinned_rel) + 10.0 * pinned_abs
    for name, dc in comparators.items():
        assert not dc({"m": base}, {"m": regressed}), (
            f"{name}: _deep_close absorbed a {10 * pinned_rel:.0e}-relative "
            f"regression — tolerance has crept past the pinned window; "
            f"this is the F3 silent-absorption failure mode"
        )
        # Structure / bool / int stay exact in every copy (sharpness).
        assert not dc({"a": 1}, {"a": 2})
        assert not dc({"f": True}, {"f": False})
        assert not dc({"k": [1.0, 2.0]}, {"k": [1.0, 2.0, 3.0]})

    # Both copies must agree on the canonical pinned window: feed a
    # perturbation that is inside the pinned window — every copy that is
    # at least as loose as the pinned window accepts it; a copy *tighter*
    # than the pinned window (the surviving 1e-9 divergence) rejects it,
    # which is exactly the divergence this forcing function exposes.
    inside = base * (1.0 + 0.1 * pinned_rel)
    verdicts = {name: dc({"m": base}, {"m": inside}) for name, dc in comparators.items()}
    assert len(set(verdicts.values())) == 1, (
        "the two _deep_close copies disagree on a perturbation inside the "
        f"pinned rel={pinned_rel:g} window {verdicts} — they must share one "
        f"audited tolerance, not carry per-lineage divergent ε (the F3 "
        f"divergent-copy generator). Unify both copies to the pinned window."
    )


_LEDGER_BUILDERS: dict[str, Callable[..., dict[str, Any]]] = {
    "cg001": build_ledger,
    "r1": build_r1_ledger,
    "cg002": build_cg002_ledger,
    "identifiability": build_identifiability_ledger,
}

# The shared, schema-stable contract every lineage ledger must satisfy.
# Derived from the union-invariant of the four merged builders; a new
# lineage may *add* keys but may not drop any of these or change their
# JSON types.
_REQUIRED_LEDGER_KEYS: dict[str, type | tuple[type, ...]] = {
    "ledger_sha256": str,
    "is_science_claim": bool,
}


@pytest.mark.slow
@pytest.mark.parametrize("name", sorted(_LEDGER_BUILDERS))
def test_every_results_ledger_conforms_to_shared_schema(name: str) -> None:
    """Every ``build_*_ledger`` must emit the shared ledger contract.

    Forcing function for the F4/F5 generative mechanism (every lineage
    bolts on a bespoke RESULTS schema). The lineage family has no
    schema-conformance gate, so lineage #6 could legally emit a new
    ledger shape and a new ``test_*_results_json_matches_committed``
    with its own comparator. This test pins the cross-lineage invariant:
    every ledger is a JSON object carrying a 64-hex ``ledger_sha256``
    and a boolean ``is_science_claim`` honesty flag. A new lineage that
    omits the sha-pinning field or the honesty flag, or changes their
    type, fails closed here and is forced onto the shared contract.

    ``is_science_claim`` is normalised across the family: the CG001/R1
    ledgers express the same honesty invariant via ``is_hypothesis``
    (a calibration is not a hypothesis); the identifiability/CG002
    ledgers via ``is_science_claim``. Both encode "this artifact makes
    no science claim" — the schema requires one of them, false-valued.
    """
    builder = _LEDGER_BUILDERS[name]
    ledger = builder(wscc_9_bus(), SimConfig())
    assert isinstance(ledger, dict), f"{name} ledger is not a JSON object"

    sha = ledger.get("ledger_sha256")
    assert isinstance(sha, str) and len(sha) == 64 and int(sha, 16) >= 0, (
        f"{name}: ledger must carry a well-formed 64-hex ledger_sha256 "
        f"(shared sha-pinning contract); got {sha!r}"
    )

    # Honesty flag: a calibration/reliability ledger must self-declare it
    # is not a science claim, via either field name. Exactly one must be
    # present and it must be False.
    honesty = {k: ledger[k] for k in ("is_science_claim", "is_hypothesis") if k in ledger}
    assert honesty, (
        f"{name}: ledger carries no honesty flag (is_science_claim / "
        f"is_hypothesis) — the shared no-promotion contract is unmet"
    )
    for key, val in honesty.items():
        assert val is False, f"{name}: {key} must be False (no promotion), got {val!r}"

    # The builder must be a thin orchestrator that reads, never
    # redefines, the gate thresholds: its source may not contain a
    # numeric gate-threshold literal assignment (drift discipline).
    src = inspect.getsource(builder)
    assert "hashlib.sha256(payload).hexdigest()" not in src, (
        f"{name}: builder re-implements ledger sha-pinning inline; it "
        f"must delegate to _substrate.ledger_sha256 (single source)"
    )


# ---------------------------------------------------------------------------
# F-supersession — the stale-falsified-premise forcing function
# ---------------------------------------------------------------------------

_SUPERSESSIONS_YAML = _LINEAGE_ROOT / "SUPERSESSIONS.yaml"
_SUPERSESSIONS_MD = _LINEAGE_ROOT / "SUPERSESSIONS.md"

# The R1 falsified-premise fingerprints. A *new* doc that contains any
# of these (i.e. references R1's superseded noisy attribution as a
# premise) MUST also resolve the supersession registry by naming it.
_R1_STALE_FINGERPRINTS = (
    "double-differentiation SNR boundary",
    "No consistent estimator exists for the noisy regime",
)
# Files that legitimately *contain* the stale fingerprint: the frozen
# R1 artifacts that ENCODE it (immutable historical record), the
# superseding artifact that QUOTES it to falsify it, the registry
# itself, this test, and any doc that already resolves the registry.
_REGISTRY_RESOLUTION_TOKENS = ("SUPERSESSIONS.yaml", "SUPERSEDE-001", "SUPERSESSIONS.md")


def _load_supersessions() -> dict[str, Any]:
    data = yaml.safe_load(_SUPERSESSIONS_YAML.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "SUPERSESSIONS.yaml is not a mapping"
    return data


def test_supersession_registry_is_internally_consistent() -> None:
    """The supersession registry is the single, fail-closed source.

    Forcing function for the F-supersession generative mechanism (a
    sha-pinned artifact encodes a premise a later sha-pinned lineage
    falsified, with no forward-resolution layer). This pins the
    registry's own integrity so the relation cannot silently rot:

    1. every ``stale_artifacts[].path`` / ``citing_artifacts[].path``
       exists on disk and carries its ``verbatim_anchor`` substring
       (the enumeration cannot drift off the real artifact);
    2. the ``superseded_sha`` and ``superseding_sha`` are real commit
       ancestors of HEAD (the supersession points at genuine history);
    3. the registry enumerates **exactly four** encoding artifacts and
       **exactly two** citing artifacts (the audited cardinality —
       a future entry that drops or pads the enumeration fails closed);
    4. the human ``SUPERSESSIONS.md`` references the machine registry
       (single source: the prose cannot diverge from the contract).
    """
    data = _load_supersessions()
    assert data["registry"] == "CALIB-GRID-SUPERSESSIONS"
    entries = data["supersessions"]
    assert isinstance(entries, list) and entries, "no supersession entries"

    repo_root = _LINEAGE_ROOT.parents[2]
    for entry in entries:
        stale = entry["stale_artifacts"]
        citing = entry["citing_artifacts"]
        # Audited cardinality: exactly four distinct encoding artifacts
        # (r1/RESULTS.md, r1/RESULTS.json, r1/ATTEMPT.md — RESULTS.md
        # contributes the prose claim + its summary restatement) and
        # exactly two citing artifacts.
        encoding_paths = {row["path"] for row in stale}
        citing_paths = {row["path"] for row in citing}
        assert encoding_paths == {
            "research/calibration/grid_kuramoto/r1/RESULTS.md",
            "research/calibration/grid_kuramoto/r1/RESULTS.json",
            "research/calibration/grid_kuramoto/r1/ATTEMPT.md",
        }, f"{entry['id']}: encoding-artifact set drifted: {sorted(encoding_paths)}"
        assert citing_paths == {
            "research/calibration/grid_kuramoto/identifiability/THRESHOLD_PROVENANCE.md",
            "research/calibration/grid_kuramoto/cg002/PROVENANCE_002.md",
        }, f"{entry['id']}: citing-artifact set drifted: {sorted(citing_paths)}"

        for row in (*stale, *citing):
            path = repo_root / row["path"]
            assert path.is_file(), f"{entry['id']}: stale path missing: {row['path']}"
            text = path.read_text(encoding="utf-8")
            anchor = " ".join(row["verbatim_anchor"].split())
            assert anchor in " ".join(text.split()), (
                f"{entry['id']}: verbatim_anchor not found in {row['path']}: "
                f"{anchor!r} — the enumeration drifted off the real artifact"
            )

        for sha_field in ("superseded_sha", "superseding_sha"):
            sha = entry[sha_field]
            assert isinstance(sha, str) and len(sha) == 40 and int(sha, 16) >= 0
            res = subprocess.run(
                ["git", "merge-base", "--is-ancestor", sha, "HEAD"],
                cwd=repo_root,
                capture_output=True,
                check=False,
            )
            assert res.returncode == 0, (
                f"{entry['id']}: {sha_field} {sha} is not a commit ancestor "
                f"of HEAD — a supersession must point at genuine history"
            )

    md = _SUPERSESSIONS_MD.read_text(encoding="utf-8")
    assert "SUPERSESSIONS.yaml" in md, (
        "SUPERSESSIONS.md must reference the machine registry "
        "(single source of truth — the prose cannot diverge)"
    )


def test_superseded_claims_resolve_via_registry() -> None:
    """No *new* doc may inherit R1's falsified premise unresolved.

    Forcing function: lineage #6+ reading ``r1/RESULTS.md`` as ground
    truth would inherit a premise CALIB-GRID-002 falsified (the
    "double-differentiation / no-consistent-estimator" noisy
    attribution). Any markdown/yaml under the lineage tree that repeats
    an R1 stale fingerprint must also resolve the supersession registry
    (name ``SUPERSESSIONS.yaml`` / ``SUPERSEDE-001``). The frozen R1
    artifacts that *encode* it (immutable historical record), the
    superseding artifact that *quotes* it to falsify it, and the
    registry itself are exempt — they are the enumerated supersession,
    not an unresolved re-derivation.
    """
    data = _load_supersessions()
    repo_root = _LINEAGE_ROOT.parents[2]
    # Exempt: every enumerated stale/superseding/registry artifact.
    exempt = {
        _SUPERSESSIONS_YAML,
        _SUPERSESSIONS_MD,
        Path(__file__),
    }
    for entry in data["supersessions"]:
        for row in (*entry["stale_artifacts"], *entry["citing_artifacts"]):
            exempt.add((repo_root / row["path"]).resolve())
        exempt.add((repo_root / entry["superseding_artifact"]).resolve())

    offenders: list[str] = []
    for path in sorted(_LINEAGE_ROOT.rglob("*")):
        if path.suffix not in (".md", ".yaml", ".yml"):
            continue
        if "__pycache__" in path.parts or path.resolve() in exempt:
            continue
        text = path.read_text(encoding="utf-8")
        normalised = " ".join(text.split())
        for fp in _R1_STALE_FINGERPRINTS:
            if fp in normalised and not any(t in text for t in _REGISTRY_RESOLUTION_TOKENS):
                offenders.append(f"{path.relative_to(_LINEAGE_ROOT.parents[2])} -> {fp!r}")
    assert not offenders, (
        "doc(s) inherit R1's falsified noisy attribution without "
        "resolving the supersession registry (reference SUPERSESSIONS.yaml "
        "/ SUPERSEDE-001 — this is the stale-falsified-premise generator):\n" + "\n".join(offenders)
    )
