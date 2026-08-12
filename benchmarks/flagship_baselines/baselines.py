# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Baseline hierarchy for FLAGSHIP-RQ-001 (clean-archive wheel-contract check).

This module defines the *comparators* the flagship instrument
(``scripts/ci/check_wheel_contract.py``) must beat to support the preregistered
alternative hypothesis H1 (see ``protocols/flagship_preregistration.yaml``).

The flagship RQ is an INFRASTRUCTURE / synthetic-only question:

    Does a clean-archive wheel-contract check surface latent first-party
    reproducibility defects (packaged modules importing an unpackaged
    first-party namespace -> ``ModuleNotFoundError`` on clean install, plus
    dead ``console_scripts`` entry points) that the pre-existing CI gate suite
    does NOT catch?  Outcome: a marginal integer defect count ``D_marginal``.

There is NO market data, NO return / PnL / edge metric anywhere here. The
"dataset" is a frozen repository/build artifact (``artifacts/wheel_contract.json``,
the preregistered evidence surface).

Detection framing (recall over the flagship-discovered defect set)
------------------------------------------------------------------
Every comparator answers ONE question for each candidate defect that the
flagship instrument reported on snapshot S:

    "Would THIS comparator, run on the SAME snapshot, have caught this defect?"

``D`` for a comparator is the number of the snapshot's real defects it catches.
The flagship claim is supported iff the clean-archive check catches defects that
NO baseline catches, i.e. ``D_marginal = |flagship_caught \\ existing_caught| >= 1``
(the preregistered one-sided threshold), AND that detection is reproducible.

Baseline tiers (each a REAL, runnable definition, never a stub)
---------------------------------------------------------------
  NAIVE          -- run nothing / trust green CI. Catches 0 by construction.
  EXISTING_SUITE -- the pre-existing gates (import-linter, unit tests,
                    release-gate probes) which resolve imports IN PLACE, where
                    the repo root is on ``sys.path`` and every first-party
                    namespace dir exists. Catches a defect ONLY if the imported
                    namespace fails to resolve in place -- the true null
                    reference.
  ABLATED        -- the flagship check with its load-bearing step removed: do
                    NOT build from a clean ``git archive`` (i.e. treat the
                    working-tree top-level package dirs as the "shipped" set,
                    the exact failure mode a stale ``build/`` dir causes).
                    Isolates the clean-archive step.
  SHUFFLED       -- permutation / label-shuffling null: replace each imported
                    namespace label with a random stdlib token (fixed seed).
                    The flagship logic then catches ~0, proving detections are
                    driven by genuine first-party-exclusion structure and not by
                    an indiscriminate "flag every import" rule.

The comparator the flagship must beat:
  FLAGSHIP       -- clean-archive wheel contract: a defect is caught iff its
                    imported namespace is a real FIRST-party namespace that the
                    wheel does NOT ship.
"""

from __future__ import annotations

import importlib.util
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
WHEEL_CONTRACT_ARTIFACT = ROOT / "artifacts" / "wheel_contract.json"

# Preregistered one-sided decision threshold (protocol_body.primary_outcomes:
# "D_marginal >= 1 supports H1; D_marginal == 0 supports H0"). This is the
# margin the flagship must clear over the baselines.
PREREG_MARGIN = 1

# Stdlib tokens used by the SHUFFLED null. They are intentionally NOT first-party
# namespaces, so the flagship detection logic correctly ignores them.
_STDLIB_NULL_POOL = ("os", "sys", "json", "math", "re", "itertools", "functools")


def _defect_key(module: str, target: str) -> str:
    return f"{module}::{target}"


def _namespace_of(key: str) -> str:
    return key.split("::", 1)[1]


def repo_top_level_packages() -> set[str]:
    """Top-level dirs in the repo carrying ``__init__.py`` -- the first-party set.

    Filesystem oracle: deterministic and independent of the process ``sys.path``.
    This is the ground truth for "what the in-place tooling can import from the
    repo root".
    """
    out: set[str] = set()
    for child in ROOT.iterdir():
        if child.is_dir() and (child / "__init__.py").is_file():
            out.add(child.name)
    return out


def is_first_party(namespace: str) -> bool:
    """True iff ``namespace`` is a FIRST-party repo top-level package.

    Strictly filesystem-based: a stdlib/third-party name (e.g. ``os``, ``numpy``)
    is NOT first-party even though it imports fine. This is the oracle the
    flagship uses -- it only ever flags first-party imports the wheel excludes.
    """
    return namespace in repo_top_level_packages()


def namespace_resolves_in_place(namespace: str) -> bool:
    """True iff the pre-existing in-place tooling resolves ``namespace``.

    In-place tooling (unit tests, ad-hoc imports, import-linter's importable
    graph) runs with the repo root on ``sys.path``, so a namespace resolves iff
    it is a repo top-level package OR an installed dist. If it resolves, the
    in-place suite never raises ``ModuleNotFoundError`` for it and cannot flag it
    as a broken import. The repo-package branch is filesystem-based, so this does
    NOT depend on the current process ``sys.path``.
    """
    if namespace in repo_top_level_packages():
        return True
    try:
        return importlib.util.find_spec(namespace) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


@dataclass(frozen=True)
class EvidenceContext:
    """Frozen snapshot-S evidence the comparators operate over.

    Built from the preregistered evidence surface ``artifacts/wheel_contract.json``.
    ``candidate_defects`` are the real defects the flagship instrument reported on
    S; each comparator decides which of them IT would have caught.
    """

    wheel_sha256: str
    wheel_packages: frozenset[str]
    candidate_defects: tuple[str, ...]  # "module::namespace" keys
    _repo_top_level: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_artifact(cls, artifact_path: Path = WHEEL_CONTRACT_ARTIFACT) -> EvidenceContext:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        keys = tuple(
            _defect_key(f["module"], f["imports_unpackaged"])
            for f in payload.get("import_failures", [])
        )
        # console_scripts breaks (dead entry points) are also in scope; fold them
        # in under the same key scheme so every defect class is represented.
        for s in payload.get("script_failures", []):
            keys += (_defect_key(str(s.get("script", "?")), str(s.get("missing_package", "?"))),)
        return cls(
            wheel_sha256=str(payload.get("wheel_sha256", "")),
            wheel_packages=frozenset(payload.get("installed_packages", [])),
            candidate_defects=keys,
            _repo_top_level=frozenset(repo_top_level_packages()),
        )


# --------------------------------------------------------------------------- #
# Baseline definitions -- each returns the SET of candidate-defect keys it       #
# would have caught on snapshot S. Real, runnable, no stubs.                     #
# --------------------------------------------------------------------------- #
def baseline_naive(ctx: EvidenceContext) -> set[str]:
    """NAIVE / NULL: run nothing, trust the green CI. Catches 0 by definition."""
    return set()


def baseline_existing_suite(ctx: EvidenceContext) -> set[str]:
    """EXISTING CI SUITE ALONE: in-place gates catch a defect only if its imported
    namespace fails to resolve with the repo root on sys.path.

    Every unpackaged first-party namespace exists as a real in-tree package, so
    it resolves in place and the status-quo suite never errors on it -> catches 0.
    This is the preregistered primary null reference.
    """
    caught: set[str] = set()
    for key in ctx.candidate_defects:
        if not namespace_resolves_in_place(_namespace_of(key)):
            caught.add(key)
    return caught


def baseline_ablated(ctx: EvidenceContext) -> set[str]:
    """ABLATED flagship: the clean-archive step removed.

    Instead of building from ``git archive HEAD`` (which ships ONLY the packaged
    namespaces), pretend the working-tree top-level package dirs are what gets
    shipped -- the exact silent-passing behaviour a stale ``build/`` dir or an
    editable/in-place install produces. A defect is caught only if its namespace
    is missing from that working-tree set; since all defect namespaces are
    working-tree packages, this catches 0. Isolates the load-bearing step.
    """
    working_tree_shipped = set(ctx._repo_top_level) | set(ctx.wheel_packages)
    caught: set[str] = set()
    for key in ctx.candidate_defects:
        if _namespace_of(key) not in working_tree_shipped:
            caught.add(key)
    return caught


def baseline_shuffled(ctx: EvidenceContext, seed: int = 42) -> set[str]:
    """SHUFFLED / NULL control: label-shuffle each imported namespace to a random
    stdlib token, then apply the flagship logic.

    stdlib tokens are not first-party, so the flagship rule correctly ignores
    them and catches ~0. Deterministic (fixed seed). Confirms the flagship's
    detections come from real first-party-exclusion structure, not from flagging
    every import edge.
    """
    rng = random.Random(seed)
    caught: set[str] = set()
    for key in ctx.candidate_defects:
        shuffled_ns = rng.choice(_STDLIB_NULL_POOL)
        if shuffled_ns not in ctx.wheel_packages and is_first_party(shuffled_ns):
            caught.add(key)
    return caught


def flagship_check(ctx: EvidenceContext) -> set[str]:
    """FLAGSHIP clean-archive wheel contract: catch a defect iff its imported
    namespace is a real FIRST-party namespace the wheel does NOT ship."""
    caught: set[str] = set()
    for key in ctx.candidate_defects:
        ns = _namespace_of(key)
        if ns not in ctx.wheel_packages and is_first_party(ns):
            caught.add(key)
    return caught


@dataclass(frozen=True)
class BaselineSpec:
    tier: str
    fn: Callable[[EvidenceContext], set[str]]
    rq_role: str


# The complete hierarchy the flagship must beat. Order = weakest -> strongest.
BASELINES: dict[str, BaselineSpec] = {
    "NAIVE": BaselineSpec(
        "NAIVE",
        baseline_naive,
        "run nothing / trust green CI (definitional D=0)",
    ),
    "EXISTING_SUITE": BaselineSpec(
        "EXISTING_SUITE",
        baseline_existing_suite,
        "pre-existing in-place gates (import-linter/unit-tests/release probes) = primary null",
    ),
    "ABLATED": BaselineSpec(
        "ABLATED",
        baseline_ablated,
        "flagship with the clean-archive step removed (isolates the load-bearing step)",
    ),
    "SHUFFLED": BaselineSpec(
        "SHUFFLED",
        baseline_shuffled,
        "permutation/label-shuffle null control",
    ),
}

# The required comparator tiers a COMPLETE hierarchy must define.
REQUIRED_TIERS: tuple[str, ...] = ("NAIVE", "EXISTING_SUITE", "ABLATED", "SHUFFLED")

FLAGSHIP_NAME = "FLAGSHIP"


def decide(
    d_marginal: int,
    reproducibility_verified: bool,
    marginal_detection_confirmed: bool,
    prereg_margin: int = PREREG_MARGIN,
) -> str:
    """Apply the preregistered decision rule. SINGLE SOURCE OF TRUTH.

    Both the report generator and the CI gate call THIS function, so a report
    cannot claim a verdict its own numbers do not support.

    Prereg promotion_rules (protocols/flagship_preregistration.yaml):
      HARD_PASS (SUPPORTED) iff ALL hold:
        (1) D_marginal >= prereg_margin (>=1);
        (2) detected set reproducible across >= 2 independent reruns AT S;
        (3) at least one detected defect not flagged by any pre-existing gate.
      HARD_FAIL (REJECTED) iff D_marginal == 0.
      Otherwise INSUFFICIENT_EVIDENCE (margin met but reproducibility/marginality
      not verified) -- never fabricated into a partial success.
    """
    if d_marginal < 0:
        raise ValueError(f"D_marginal must be non-negative, got {d_marginal}")
    if d_marginal == 0:
        return "REJECTED"
    if (
        d_marginal >= prereg_margin
        and reproducibility_verified
        and marginal_detection_confirmed
    ):
        return "SUPPORTED"
    return "INSUFFICIENT_EVIDENCE"
