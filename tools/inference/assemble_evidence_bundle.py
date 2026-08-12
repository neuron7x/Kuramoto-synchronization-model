#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Assemble and validate an inference evidence bundle (WP-09).

A bundle is one inspectable artifact that binds a *validated* context manifest
(WP-01) to the run's evidence: the input-data hash, the kernel config, real
null results, baseline / OOS / cost slots, the reproduction command, and a
claim card. The claim card is not free text — its tier is checked against the
canonical ladder via ``analytics.signals.claim_maturity.evaluate_promotion``:
**a bundle cannot claim a tier its evidence tokens do not earn**. The null
results are computed by the existing ``analytics.signals.null_baseline``
generator, so the bundle is bound to real computation, not placeholders.

This tool makes no predictive or market claim. The example bundle it ships is a
``MEASURED_SYNTHETIC`` structural artifact over a seeded null — it asserts the
binding works, nothing about out-of-sample utility. Baseline, OOS and cost
slots are honestly marked ``NOT_RUN`` until a real run fills them; a higher tier
is refused at assembly time because the evidence tokens are absent.

Exit codes::

    0  bundle assembled / validated
    1  refused (manifest invalid, claim tier unearned, bundle inconsistent)
    2  malformed invocation
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_REQUIRED_SECTIONS = (
    "context_manifest",
    "input_data_hash",
    "kernel_config",
    "null_results",
    "baseline_results",
    "oos_report",
    "cost_model",
    "reproduction_command",
    "claim_card",
)


def _load_module(rel: str, name: str) -> ModuleType:
    path = _ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _canonical_sha256(payload: dict[str, Any]) -> str:
    body = {k: v for k, v in payload.items() if k != "bundle_sha256"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _claim_card_violations(card: dict[str, Any], cm: ModuleType) -> list[str]:
    """Refuse a claim card whose evidence tokens do not earn its tier."""
    errors: list[str] = []
    tier = str(card.get("tier", ""))
    tokens = card.get("evidence_tokens", [])
    if tier not in cm.LADDER:
        errors.append(f"claim_card.tier {tier!r} is not a ladder rung")
        return errors
    if tier == cm.LADDER[0]:
        return errors  # ground state earns nothing, demands nothing
    if not isinstance(tokens, list) or not tokens:
        errors.append("claim_card.evidence_tokens must be a non-empty list")
        return errors
    try:
        verdict = cm.evaluate_promotion(cm.LADDER[0], tier, tokens)
    except ValueError as exc:
        errors.append(f"claim_card: {exc}")
        return errors
    if not verdict.allowed:
        errors.append(
            f"claim_card: tier {tier!r} is not earned; missing evidence "
            f"{list(verdict.missing_evidence)}"
        )
    if card.get("boundary") != cm.CLAIM_BOUNDARY:
        errors.append(f"claim_card.boundary must be {cm.CLAIM_BOUNDARY!r}")
    return errors


def validate_bundle(bundle: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for section in _REQUIRED_SECTIONS:
        if section not in bundle:
            errors.append(f"missing required section: {section}")
    if errors:
        return errors
    cm = _load_module("analytics/signals/claim_maturity.py", "_cm_bundle")
    errors.extend(_claim_card_violations(bundle["claim_card"], cm))
    expected = _canonical_sha256(bundle)
    if bundle.get("bundle_sha256") != expected:
        errors.append("bundle_sha256 does not match the canonical content hash")
    return errors


def assemble(manifest_path: Path, *, seed: int, n: int) -> dict[str, Any]:
    """Build a bundle from a validated manifest and a real seeded null."""
    vcm = _load_module("tools/inference/validate_context_manifest.py", "_vcm")
    schema = json.loads((_ROOT / "schemas/inference/context_manifest.schema.json").read_text())
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cm_violations = vcm.validate(manifest, schema, vcm._load_ladder())
    if cm_violations:
        raise SystemExit("context manifest invalid: " + "; ".join(cm_violations))

    nb = _load_module("analytics/signals/null_baseline.py", "_nb")
    null_array, null_meta = nb.make_gaussian_null(n, seed)
    null_results = {
        "generator": "make_gaussian_null",
        "n": int(n),
        "seed": int(seed),
        "mean": float(null_array.mean()),
        "std": float(null_array.std()),
        "metadata": dict(null_meta),
    }

    bundle: dict[str, Any] = {
        "schema_version": 1,
        "context_manifest": manifest,
        "input_data_hash": manifest["data_source"]["sha256"],
        "kernel_config": {"kernel": "kuramoto_ricci_composite", "params": {}},
        "null_results": null_results,
        "baseline_results": {"status": "NOT_RUN"},
        "oos_report": {"status": "NOT_RUN"},
        "cost_model": {"status": "NOT_RUN"},
        "reproduction_command": (
            f"python tools/inference/assemble_evidence_bundle.py "
            f"--manifest {manifest_path.as_posix()} --seed {seed} --n {n}"
        ),
        "claim_card": {
            "claim": "Seeded synthetic null ensemble assembled behind a validated context manifest.",
            "tier": manifest["claim_tier"],
            "evidence_tokens": ["observability", "synthetic_measurement"],
            "boundary": "descriptor_only_not_predictor",
        },
    }
    bundle["bundle_sha256"] = _canonical_sha256(bundle)

    violations = validate_bundle(bundle)
    if violations:
        raise SystemExit("assembled bundle is inconsistent: " + "; ".join(violations))
    return bundle


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", help="context manifest JSON to assemble from")
    parser.add_argument("--out", help="path to write the assembled bundle")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--n", type=int, default=512)
    parser.add_argument("--check", help="validate an existing bundle JSON instead of assembling")
    args = parser.parse_args(argv)

    if args.check:
        bundle = json.loads(Path(args.check).read_text(encoding="utf-8"))
        violations = validate_bundle(bundle)
        if violations:
            for v in violations:
                print(f"EVIDENCE-BUNDLE INVALID: {v}", file=sys.stderr)
            return 1
        print(f"evidence bundle valid: tier={bundle['claim_card']['tier']}")
        return 0

    if not args.manifest:
        raise SystemExit("either --manifest (assemble) or --check (validate) is required")
    bundle = assemble(Path(args.manifest), seed=args.seed, n=args.n)
    text = json.dumps(bundle, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(
        f"evidence bundle assembled: tier={bundle['claim_card']['tier']}, sha={bundle['bundle_sha256'][:12]}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
