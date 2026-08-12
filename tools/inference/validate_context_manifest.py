#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed validator for an inference context manifest (WP-01).

A kernel run is admissible only behind a context manifest that declares the
problem, asset universe, time window, data-source contract (with a SHA-256
provenance pin), target variable, claim tier, at least one null model, at least
one stop rule, and the evidence path. This validator enforces the JSON Schema
at ``schemas/inference/context_manifest.schema.json`` and additionally:

* binds ``claim_tier`` to the canonical maturity ladder in
  ``analytics/signals/claim_maturity.LADDER`` (single source of truth — the
  schema does not duplicate the rung list);
* requires ``time_window.start`` to be strictly before ``time_window.end``.

It makes no scientific claim. It asserts that the run is contextualised before
it computes; it says nothing about whether the run's result is correct.

Exit codes::

    0  manifest valid and contextualised
    1  validation failure (schema, unknown claim tier, inverted window)
    2  malformed invocation (file/schema unreadable)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import jsonschema

_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_PATH = _ROOT / "schemas" / "inference" / "context_manifest.schema.json"


def _load_ladder() -> tuple[str, ...]:
    """Load the canonical maturity ladder as the single source of truth.

    Loaded standalone from ``analytics/signals/claim_maturity.py`` (which is
    pure-stdlib) so the validator does not drag in the heavy
    ``analytics.signals`` package init chain. Fails closed if the module or its
    ``LADDER`` symbol moves.
    """
    import importlib.util

    path = _ROOT / "analytics" / "signals" / "claim_maturity.py"
    spec = importlib.util.spec_from_file_location("_claim_maturity_for_context", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load claim-maturity ladder from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return tuple(module.LADDER)


def validate(manifest: dict[str, Any], schema: dict[str, Any], ladder: Sequence[str]) -> list[str]:
    """Return a list of human-readable violations (empty == valid)."""
    errors: list[str] = []
    validator = jsonschema.Draft202012Validator(schema)
    for err in sorted(validator.iter_errors(manifest), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "<root>"
        errors.append(f"schema[{loc}]: {err.message}")
    if errors:
        return errors

    tier = manifest["claim_tier"]
    if tier not in ladder:
        errors.append(
            f"claim_tier {tier!r} is not a rung in analytics.signals.claim_maturity.LADDER "
            f"({len(ladder)} rungs: {ladder[0]}..{ladder[-1]})"
        )

    window = manifest["time_window"]
    try:
        start = datetime.fromisoformat(window["start"])
        end = datetime.fromisoformat(window["end"])
    except ValueError as exc:
        errors.append(f"time_window: unparseable ISO-8601 ({exc})")
    else:
        if start >= end:
            errors.append("time_window: start must be strictly before end")
    return errors


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"unreadable JSON ({path}): {exc}") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="path to a context manifest JSON")
    args = parser.parse_args(argv)

    schema = _read_json(_SCHEMA_PATH)
    manifest = _read_json(Path(args.manifest))
    errors = validate(manifest, schema, _load_ladder())
    if errors:
        for err in errors:
            print(f"CONTEXT-MANIFEST INVALID: {err}", file=sys.stderr)
        return 1
    print(
        f"context manifest valid: tier={manifest['claim_tier']}, universe={len(manifest['asset_universe'])} assets."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
