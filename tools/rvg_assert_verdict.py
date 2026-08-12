#!/usr/bin/env python3
"""RVG-1 verdict-status assertion — the single, explicit CI enforcement gate.

The RVG workflow must never be ambiguous about what a green job means. This tool
makes the enforcement mode a required, explicit choice:

  --mode bootstrap
      The repository verdict MAY be FAIL, but the verdict artifact must still be
      *sound*: schema-valid, arithmetic-recomputed, hash-bound to real files, and
      free of placeholder evidence (empty SBOM, or a `tool: none` mutation record
      pretending to a score). A structurally-sound FAIL passes; a placeholder or
      tampered artifact does not. Use while the full repo cannot yet meet the
      RVG thresholds — the job proves *instrument integrity*, not a PASS verdict.

  --mode enforce
      The verdict itself must be PASS (all soundness checks still apply, and the
      mutation evidence must be a real run — bootstrap_report_only is rejected).

Exit non-zero on any violation. Stdlib + the sibling rvg_verify_artifacts helpers
only, so the gate carries no dependency surface of its own.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Runs as `python tools/rvg_assert_verdict.py ...` → tools/ is sys.path[0], so
# the sibling verifier imports directly and we reuse its proven checks.
import rvg_verify_artifacts as verify


class AssertError(Exception):
    pass


def _is_placeholder_sbom(verdict: dict[str, Any]) -> bool:
    """The verdict must record a real SBOM (sbom_present is set by the hardened
    sbom_present() which already rejects an empty component list)."""
    return not bool(verdict.get("sbom_present"))


def _mutation_state(verdict: dict[str, Any]) -> str:
    """Classify the mutation evidence carried by the verdict."""
    if verdict.get("mutation_bootstrap_report_only"):
        return "bootstrap"
    if "mutation_score" in verdict and verdict.get("mutation_score") is not None:
        return "real"
    return "absent"


def assert_verdict(
    verdict_path: Path,
    *,
    mode: str,
    manifest_path: Path | None = None,
    schema_path: Path | None = None,
    root: Path | None = None,
) -> None:
    if mode not in ("bootstrap", "enforce"):
        raise AssertError(f"unknown --mode {mode!r} (expected bootstrap|enforce)")
    if not verdict_path.is_file():
        raise AssertError(f"verdict: missing at {verdict_path}")

    manifest_path = manifest_path or (verdict_path.parent / "audit.hashes")
    if schema_path is None:
        default_schema = Path("audit/schema/verdict.schema.json")
        schema_path = default_schema if default_schema.is_file() else None

    verdict = json.loads(verdict_path.read_text("utf-8"))

    # --- Soundness (applies to BOTH modes) ------------------------------------
    try:
        verify.validate_schema(verdict, schema_path)
        verify.cross_check_recompute(verdict)
        verify.verify_hash_manifest(verdict_path, manifest_path, root=root)
    except verify.VerifyError as exc:
        raise AssertError(f"unsound verdict artifact: {exc}") from exc

    # --- Non-placeholder evidence (applies to BOTH modes) ---------------------
    if _is_placeholder_sbom(verdict):
        raise AssertError("placeholder evidence: SBOM absent or empty (no dependency inventory)")

    mutation = _mutation_state(verdict)
    if mutation == "absent":
        raise AssertError(
            "placeholder evidence: mutation neither real nor explicitly bootstrap_report_only"
        )

    verdict_value = verdict.get("verdict")
    if verdict_value not in ("PASS", "FAIL"):
        raise AssertError(f"verdict: bad value {verdict_value!r}")

    # --- Mode-specific enforcement --------------------------------------------
    if mode == "enforce":
        if mutation != "real":
            raise AssertError("enforce: mutation evidence must be a real run (not bootstrap)")
        if verdict_value != "PASS":
            raise AssertError(f"enforce: verdict is {verdict_value}, expected PASS")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Assert an RVG verdict under an explicit mode")
    p.add_argument("verdict", help="path to RVG_VERDICT.json")
    p.add_argument("--mode", required=True, choices=("bootstrap", "enforce"))
    p.add_argument("--manifest", help="hash manifest (default: <verdict dir>/audit.hashes)")
    p.add_argument(
        "--schema", help="verdict JSON schema (default: audit/schema/verdict.schema.json)"
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        assert_verdict(
            Path(args.verdict),
            mode=args.mode,
            manifest_path=Path(args.manifest) if args.manifest else None,
            schema_path=Path(args.schema) if args.schema else None,
        )
    except AssertError as exc:
        print(f"RVG verdict assertion FAILED [{args.mode}]: {exc}", file=sys.stderr)
        return 1
    verdict = json.loads(Path(args.verdict).read_text("utf-8"))
    print(
        f"RVG verdict assertion OK [{args.mode}]: verdict={verdict.get('verdict')} "
        f"(instrument integrity proven)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
