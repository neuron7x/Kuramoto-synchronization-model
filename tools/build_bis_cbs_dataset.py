#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""CBS marginal loader for the X-10R reconstruction engine (issue #639).

This module is the **CBS adapter** that feeds the *same*, substrate-
agnostic Cimini-Squartini reconstruction engine
(`research.reconstruction.cimini_squartini.fit_cimini_squartini`).
It does NOT re-implement any reconstruction maths and it does NOT
re-implement the capsule. It only:

  1. reads a BIS Consolidated Banking Statistics (CBS) marginal
     dataset (JSON, see SCHEMA below), and
  2. derives per-node out/in marginal strength vectors
     ``(s_out, s_in)`` suitable for ``fit_cimini_squartini``.

WHY CBS IS A SEPARATE ADAPTER FROM LBS
======================================
``tools/build_bis_lbs_dataset.py`` builds the **LBS** (Locational
Banking Statistics) view: residence-based, country-aggregate, and
INCLUDING intragroup positions. CBS is a different ontology:

  * **nationality / parent-group based** — the reporting unit is the
    *consolidated banking group of a given nationality*, not the
    country of residence of an office; and
  * **intragroup positions are EXCLUDED** by construction — CBS
    consolidates a group's own internal claims away, leaving only
    positions vs. *unrelated* counterparties.

CBS is therefore conceptually closer to a "bank-group node" ontology
than LBS and reduces (without eliminating) the country-to-bank
ontology drift (issue #639). It does NOT make the reconstruction a
bank-level interbank network, and it does NOT lift INV-IDENTIFICATION-1
or INV-RECONSTRUCTION-2 — see the X-10R boundary card.

ONTOLOGY CONTRACT (the thing this loader protects)
==================================================
Because CBS excludes intragroup positions, an intragroup position in
the input is a **schema violation**, not data. The loader
**rejects** any CBS position whose reporting group equals its
counterparty group (``reporter_group == counterparty_group``). This
is the falsifier that protects the CBS ontology claim: a loader that
silently accepted intragroup positions would be quietly relabelling
LBS-style (intragroup-inclusive) data as CBS. ``main`` exits
non-zero on any such violation.

NON-CLAIM (honesty boundary — read before extending)
====================================================
"reconstruction" / "marginal" here are INPUT-SIDE constructs only.
Nothing in this module is a predictive, alpha, tradeable, or
bank-level inference signal. Recovery is defined only on synthetic
substrates with known ground truth (see
``research.reconstruction.reconstruction_capsule`` boundary +
``docs/governance/X10R_BOUNDARY_CARD.md``). This loader produces the
*country/parent-group-aggregate* marginals that the engine consumes;
it asserts no market or product-readiness property whatsoever.

SCHEMA (CBS marginal dataset, JSON)
===================================
::

    {
      "schema_version": "bis.cbs.marginals.v1",
      "ontology": "nationality_parent_group",
      "intragroup_excluded": true,            # MUST be true for CBS
      "reporting_period": "2023-Q4",
      "positions": [
        {"reporter_group": "DE", "counterparty_group": "US",
         "claim_usd_mn": 1234.5},
        ...
      ]
    }

``positions`` are directed *consolidated foreign claims* of the
reporting nationality's banking group on the counterparty group.
``s_out[g]`` is the total outward claim of group ``g``; ``s_in[g]``
is the total claim *on* group ``g`` (its inward marginal). Node order
is the sorted union of all groups that appear, so the loader is
deterministic.

CLI
===
    python tools/build_bis_cbs_dataset.py --cbs-json <path>

Exit code 0 iff the dataset honours the CBS ontology contract and
yields a valid ``(s_out, s_in)`` pair; non-zero otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

SCHEMA_VERSION = "bis.cbs.marginals.v1"
ONTOLOGY = "nationality_parent_group"


class CbsContractViolation(ValueError):
    """Raised when a CBS dataset violates the CBS ontology contract.

    The canonical case is an intragroup position
    (``reporter_group == counterparty_group``): CBS excludes
    intragroup positions by construction, so their presence means the
    input is not CBS. Fail-closed — never silently accept.
    """


@dataclass(frozen=True)
class CbsMarginals:
    """Per-node CBS marginal strengths, engine-ready.

    ``s_out`` / ``s_in`` are aligned to ``node_labels`` (sorted group
    codes) and are exactly the vectors ``fit_cimini_squartini``
    consumes. ``intragroup_excluded`` records that the source honoured
    the CBS contract (always ``True`` for a successfully loaded CBS
    dataset — the loader rejects otherwise).
    """

    node_labels: tuple[str, ...]
    s_out: np.ndarray
    s_in: np.ndarray
    reporting_period: str
    intragroup_excluded: bool

    @property
    def n_nodes(self) -> int:
        return len(self.node_labels)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CbsContractViolation(message)


def parse_cbs_marginals(doc: dict[str, Any]) -> CbsMarginals:
    """Validate a CBS marginal document and derive ``(s_out, s_in)``.

    Fail-closed on every contract violation. In particular, ANY
    intragroup position (``reporter_group == counterparty_group``)
    raises :class:`CbsContractViolation` — this is the ontology
    falsifier that distinguishes CBS from LBS.
    """
    _require(isinstance(doc, dict), "CBS document must be a JSON object")

    schema = doc.get("schema_version")
    _require(
        schema == SCHEMA_VERSION,
        f"unexpected schema_version {schema!r}; expected {SCHEMA_VERSION!r}",
    )

    ontology = doc.get("ontology")
    _require(
        ontology == ONTOLOGY,
        f"CBS ontology must be {ONTOLOGY!r} (nationality/parent-group); got {ontology!r}",
    )

    # The CBS contract: intragroup positions are excluded by construction.
    # A source that does not assert this is not CBS; reject fail-closed.
    _require(
        doc.get("intragroup_excluded") is True,
        "CBS contract requires intragroup_excluded == true "
        "(CBS consolidates intragroup positions away by construction); "
        "got intragroup_excluded="
        f"{doc.get('intragroup_excluded')!r}",
    )

    reporting_period = doc.get("reporting_period")
    _require(
        isinstance(reporting_period, str) and bool(reporting_period),
        "reporting_period must be a non-empty string",
    )
    assert isinstance(reporting_period, str)  # narrow for mypy

    positions = doc.get("positions")
    _require(
        isinstance(positions, list) and len(positions) > 0,
        "positions must be a non-empty list",
    )
    assert isinstance(positions, list)  # narrow for mypy

    out_strength: dict[str, float] = {}
    in_strength: dict[str, float] = {}
    groups: set[str] = set()

    for idx, pos in enumerate(positions):
        _require(isinstance(pos, dict), f"positions[{idx}] must be an object")
        reporter = pos.get("reporter_group")
        counterparty = pos.get("counterparty_group")
        _require(
            isinstance(reporter, str) and bool(reporter),
            f"positions[{idx}].reporter_group must be a non-empty string",
        )
        _require(
            isinstance(counterparty, str) and bool(counterparty),
            f"positions[{idx}].counterparty_group must be a non-empty string",
        )
        assert isinstance(reporter, str) and isinstance(counterparty, str)

        # FALSIFIER — protects the CBS ontology claim. CBS excludes
        # intragroup positions; an intragroup row means this input is
        # not CBS (it is LBS-style, intragroup-inclusive). Reject.
        _require(
            reporter != counterparty,
            f"positions[{idx}] is an INTRAGROUP position "
            f"(reporter_group == counterparty_group == {reporter!r}); "
            "CBS excludes intragroup positions by construction. "
            "Accepting this would relabel LBS-style data as CBS.",
        )

        raw_claim = pos.get("claim_usd_mn")
        if isinstance(raw_claim, bool) or not isinstance(raw_claim, (int, float)):
            raise CbsContractViolation(f"positions[{idx}].claim_usd_mn must be a number")
        claim = float(raw_claim)
        _require(
            np.isfinite(claim) and claim >= 0.0,
            f"positions[{idx}].claim_usd_mn must be finite and non-negative; got {claim}",
        )

        groups.add(reporter)
        groups.add(counterparty)
        out_strength[reporter] = out_strength.get(reporter, 0.0) + claim
        in_strength[counterparty] = in_strength.get(counterparty, 0.0) + claim

    node_labels = tuple(sorted(groups))
    _require(
        len(node_labels) >= 2,
        f"CBS reconstruction needs >= 2 distinct groups; got {len(node_labels)}",
    )

    s_out = np.array([out_strength.get(g, 0.0) for g in node_labels], dtype=np.float64)
    s_in = np.array([in_strength.get(g, 0.0) for g in node_labels], dtype=np.float64)

    # fit_cimini_squartini normalises by the mean, which requires a
    # positive mean on each side. A degenerate all-zero marginal would
    # be silently un-fittable; reject it here with a clear message.
    _require(
        float(s_out.sum()) > 0.0 and float(s_in.sum()) > 0.0,
        "both s_out and s_in must have positive total mass",
    )

    return CbsMarginals(
        node_labels=node_labels,
        s_out=s_out,
        s_in=s_in,
        reporting_period=reporting_period,
        intragroup_excluded=True,
    )


def load_cbs_marginals(path: Path) -> CbsMarginals:
    """Read and validate a CBS marginal dataset from ``path``."""
    text = path.read_text(encoding="utf-8")
    doc = json.loads(text)
    return parse_cbs_marginals(doc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build_bis_cbs_dataset",
        description=(
            "Load BIS CBS (nationality/parent-group) marginals for the "
            "X-10R reconstruction engine. Rejects intragroup positions "
            "(CBS ontology contract)."
        ),
    )
    parser.add_argument("--cbs-json", required=True, type=Path)
    args = parser.parse_args(argv)

    if not args.cbs_json.is_file():
        print(f"FAIL: {args.cbs_json} not found", file=sys.stderr)
        return 1

    try:
        marg = load_cbs_marginals(args.cbs_json)
    except CbsContractViolation as exc:
        # Non-zero exit protects the CBS ontology claim (issue #639).
        print(f"FAIL: CBS contract violation: {exc}", file=sys.stderr)
        return 2
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: invalid CBS dataset: {exc}", file=sys.stderr)
        return 1

    sys.stderr.write(
        f"OK: CBS marginals loaded — n_groups={marg.n_nodes}, "
        f"period={marg.reporting_period}, "
        f"out_mass={float(marg.s_out.sum()):.1f}, "
        f"in_mass={float(marg.s_in.sum()):.1f} (intragroup excluded)\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
