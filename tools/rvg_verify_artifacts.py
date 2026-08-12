#!/usr/bin/env python3
"""RVG-1 artifact verifier — binds a verdict to files and re-proves its math.

Given a verdict JSON and a sha256 hash manifest (audit.hashes), this tool:

  1. Validates the verdict against the verdict JSON schema (if jsonschema is
     available; otherwise a minimal built-in structural check).
  2. Independently recomputes every percentage from the raw numerator/
     denominator pairs the verdict carries, and fails if any recompute differs
     from the stored value by more than CROSS_CHECK_TOLERANCE.
  3. Confirms the hash manifest exists and that the verdict file itself is
     covered by (or consistent with) the manifest.

Fail-closed: any missing input or failed check exits non-zero.

Companion helper `diff_reproducibility` compares two verdict JSON blobs and
returns the set of differing fields excluding the known non-deterministic ones,
so `make rvg` can be run twice and asserted byte-stable modulo timestamp/commit.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path
from typing import Any

CROSS_CHECK_TOLERANCE = 0.01
NONDETERMINISTIC_FIELDS = ("timestamp_utc", "commit", "python_version")

# (percentage_field, [numerator, denominator]_field)
RECOMPUTE_PAIRS = (
    ("line_coverage", "line_coverage_raw"),
    ("branch_coverage", "branch_coverage_raw"),
    ("mutation_score", "mutation_score_raw"),
    ("test_pass_rate", "test_pass_rate_raw"),
)

REQUIRED_FIELDS = ("repo", "verdict", "fail_reasons")


class VerifyError(Exception):
    pass


def _recompute(numerator: float, denominator: float) -> float:
    if denominator == 0:
        raise VerifyError("recompute: zero denominator")
    return round(numerator / denominator * 100.0, 2)


def validate_schema(verdict: dict[str, Any], schema_path: Path | None) -> None:
    """Prefer jsonschema; fall back to a minimal required-field check."""
    if schema_path is not None and schema_path.is_file():
        # Dynamic import: jsonschema is an optional dep. Loading it via
        # importlib (rather than a static `import`) keeps the tool stdlib-only
        # under mypy --strict without a type-ignore suppression.
        try:
            jsonschema = importlib.import_module("jsonschema")
        except ImportError:
            jsonschema = None  # fall through to structural check
        if jsonschema is not None:
            try:
                jsonschema.validate(verdict, json.loads(schema_path.read_text("utf-8")))
                return
            except Exception as exc:  # jsonschema.ValidationError etc.
                raise VerifyError(f"schema: verdict failed validation: {exc}") from exc

    missing = [k for k in REQUIRED_FIELDS if k not in verdict]
    if missing:
        raise VerifyError(f"schema: verdict missing required fields {missing}")
    if verdict["verdict"] not in ("PASS", "FAIL"):
        raise VerifyError(f"schema: bad verdict value {verdict['verdict']!r}")


def cross_check_recompute(verdict: dict[str, Any]) -> list[str]:
    """Re-derive each stored percentage from its raw pair. Returns checked keys."""
    checked: list[str] = []
    for pct_field, raw_field in RECOMPUTE_PAIRS:
        if pct_field not in verdict:
            continue
        raw = verdict.get(raw_field)
        if not (isinstance(raw, (list, tuple)) and len(raw) == 2):
            raise VerifyError(f"{pct_field}: missing raw pair {raw_field}")
        recomputed = _recompute(float(raw[0]), float(raw[1]))
        stored = float(verdict[pct_field])
        if abs(recomputed - stored) > CROSS_CHECK_TOLERANCE:
            raise VerifyError(
                f"{pct_field}: recompute {recomputed} != stored {stored} "
                f"(delta > {CROSS_CHECK_TOLERANCE})"
            )
        checked.append(pct_field)

    # Derived-metric consistency.
    if "branch_coverage" in verdict and "mutation_score" in verdict:
        bc = float(verdict["branch_coverage"])
        ms = float(verdict["mutation_score"])
        if "oracle_gap" in verdict:
            if abs(round(bc - ms, 2) - float(verdict["oracle_gap"])) > CROSS_CHECK_TOLERANCE:
                raise VerifyError("oracle_gap: inconsistent with branch/mutation")
            checked.append("oracle_gap")
        if "verified_test_strength" in verdict:
            if (
                abs(round(min(bc, ms), 2) - float(verdict["verified_test_strength"]))
                > CROSS_CHECK_TOLERANCE
            ):
                raise VerifyError("verified_test_strength: inconsistent with min(branch, mutation)")
            checked.append("verified_test_strength")
    return checked


def _sha256(path: Path) -> str:
    """Streamed sha256 of a file (chunked so large artifacts don't load fully)."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_hash_manifest(
    verdict_path: Path, manifest_path: Path, *, root: Path | None = None
) -> None:
    """Recompute every manifest digest and confirm the verdict is hash-bound.

    The manifest is `sha256sum` output (``<64-hex>␠␠<path>`` per line) whose paths
    are relative to the repo root the audit ran from. For each entry we:

      * reject malformed lines (missing digest/path, non-64-char digest),
      * resolve the path and reject anything escaping ``root`` (path-traversal),
      * recompute sha256(file) and fail on any mismatch (tamper detection),
      * skip the manifest's own line (it is written mid-`sha256sum`, so its
        self-hash is intrinsically stale — see audit/RVG_PROTOCOL.md §8).

    Finally the verdict file MUST appear (and therefore have matched) in the
    manifest; otherwise the verdict is unbound and rejected.
    """
    if not manifest_path.is_file():
        raise VerifyError(f"hash-manifest: missing at {manifest_path}")

    root_resolved = (root or Path.cwd()).resolve()
    manifest_resolved = manifest_path.resolve()
    verdict_resolved = verdict_path.resolve()
    verdict_seen = False

    lines = [ln for ln in manifest_path.read_text("utf-8").splitlines() if ln.strip()]
    if not lines:
        raise VerifyError("hash-manifest: empty")

    for ln in lines:
        parts = ln.split(None, 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise VerifyError(f"hash-manifest: malformed entry: {ln!r}")
        expected, raw_path = parts[0], parts[1].strip()
        candidate = (root_resolved / raw_path).resolve()

        # Confinement: no manifest entry may point outside the audited root.
        try:
            candidate.relative_to(root_resolved)
        except ValueError:
            raise VerifyError(
                f"hash-manifest: path escapes root {root_resolved}: {raw_path!r}"
            ) from None

        # The manifest cannot honestly hash itself (written while sha256sum runs).
        if candidate == manifest_resolved:
            continue

        if not candidate.is_file():
            raise VerifyError(f"hash-manifest: missing file {candidate}")
        actual = _sha256(candidate)
        if actual != expected:
            raise VerifyError(
                f"hash-manifest: digest mismatch for {candidate}: "
                f"expected={expected}, actual={actual}"
            )
        if candidate == verdict_resolved:
            verdict_seen = True

    if not verdict_seen:
        raise VerifyError(f"hash-manifest: verdict not covered: {verdict_path}")


def diff_reproducibility(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    """Fields that differ between two verdicts, excluding non-deterministic ones."""
    keys = set(a) | set(b)
    diffs = []
    for k in sorted(keys):
        if k in NONDETERMINISTIC_FIELDS:
            continue
        if a.get(k) != b.get(k):
            diffs.append(k)
    return diffs


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2:
        print(
            "usage: rvg_verify_artifacts.py VERDICT.json audit.hashes [schema.json]",
            file=sys.stderr,
        )
        return 2
    verdict_path = Path(argv[0])
    manifest_path = Path(argv[1])
    schema_path = Path(argv[2]) if len(argv) > 2 else None

    try:
        if not verdict_path.is_file():
            raise VerifyError(f"verdict: missing at {verdict_path}")
        verdict = json.loads(verdict_path.read_text("utf-8"))
        validate_schema(verdict, schema_path)
        checked = cross_check_recompute(verdict)
        verify_hash_manifest(verdict_path, manifest_path)
    except VerifyError as exc:
        print(f"RVG artifact verification FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"RVG artifact verification OK (recomputed: {', '.join(checked) or 'none'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
