#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Doc-status gate (DOC-003) — temporal truth of authoritative status docs.

Every doc in the authoritative status/release set carries a machine-readable
``doc_status`` YAML front-matter block::

    ---
    doc_status:
      status: current            # current | historical | aspirational
      authoritative_for: [ ... ] # non-empty list of concern tokens
      valid_from: 2026-07-19     # ISO date the doc became authoritative
      valid_to: 2026-07-16       # optional — end of the validity window
      superseded_by: <path|id>   # optional — what replaced it
      generated_by: <path>       # optional — generator, for rendered surfaces
    ---

The single source of truth for the project's maturity rung and the forbidden
claim-word firewall is ``governance/project_state.yaml`` (GOV-005). This gate
reads that SSOT and enforces, fail-closed:

1. **Schema** — every tagged doc has a parseable ``doc_status`` block with a
   valid ``status`` enum, a non-empty ``authoritative_for`` list and an ISO
   ``valid_from``. A ``historical`` doc must additionally declare *why* it is
   no longer current (``superseded_by`` and/or ``valid_to``).

2. **No stale-current contradiction** — a doc marked ``current`` may not assert
   a maturity/claim word that outranks the project's ``current_state``. The
   forbidden claim words are taken from the SSOT firewall (``validated``,
   ``production-ready``, ``deployable`, …). Because ``current_state`` is
   ``RESEARCH_ALPHA`` (synthetic-/single-session evidence only), any such word
   used as an affirmative prose claim in a ``current`` doc is a contradiction.

   ``historical`` and ``aspirational`` docs are **not** scanned for this — a
   historical release-truth snapshot is *allowed* to record a past claim; that
   is exactly why it is marked historical rather than deleted.

Use/mention discipline (so the gate does not fire on the vocabulary itself):
  * fenced code blocks (``` ... ```) and inline ``code`` are stripped before
    scanning — claim words in example commands are not prose claims;
  * a prose line bearing the inline marker ``<!-- doc-status:claim-mention -->``
    is a definitional mention and is skipped (and recorded in the report);
  * the one doc that *defines* the firewall may set
    ``defines_claim_vocabulary: true`` in its front-matter, which exempts it
    from the affirmative-claim scan while still being recorded in the report.

Exit codes (fail-closed):
  0  clean
  1  at least one ``current`` doc contradicts the project state
  2  structural error (missing/unparseable front-matter, bad schema, bad SSOT)

Usage::

    python scripts/ci/check_doc_status.py                 # gate the tagged set
    python scripts/ci/check_doc_status.py --report out.json
    python scripts/ci/check_doc_status.py --doc some/file.md   # gate one file
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = ROOT / "governance/project_state.yaml"
DEFAULT_REPORT = ROOT / "artifacts/governance/doc_status_report.json"

EXIT_OK = 0
EXIT_FLAGGED = 1
EXIT_ERROR = 2

VALID_STATUSES = ("current", "historical", "aspirational")
MENTION_MARKER = "<!-- doc-status:claim-mention -->"

# The authoritative status/release doc set this gate governs. Paths are
# relative to the repository root. Full-repository doc coverage is a larger
# follow-up (DOC-003 residual); this gate covers the authoritative set plus the
# enforcing mechanism.
TAGGED_DOCS: tuple[str, ...] = (
    "docs/PROJECT_STATE_ONTOLOGY.md",
    "docs/RELEASE_GATES.md",
    "BASELINE.md",
    "DELIVERY.md",
    "docs/project-status.md",
    "ROADMAP.md",
)


class DocStatusError(Exception):
    """Structural failure — the gate fails closed (exit 2)."""


# --------------------------------------------------------------------------- #
# SSOT (project_state.yaml) loading.
# --------------------------------------------------------------------------- #
def load_state(path: Path = STATE_FILE) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise DocStatusError(f"cannot read/parse SSOT {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise DocStatusError(f"{path}: top level must be a mapping")
    if "current_state" not in raw:
        raise DocStatusError(f"{path}: missing current_state")
    if not isinstance(raw.get("forbidden_claims"), list) or not raw["forbidden_claims"]:
        raise DocStatusError(f"{path}: forbidden_claims must be a non-empty list")
    return raw


def _forbidden_patterns(state: dict[str, Any]) -> list[tuple[str, re.Pattern[str]]]:
    out: list[tuple[str, re.Pattern[str]]] = []
    for entry in state["forbidden_claims"]:
        if not isinstance(entry, dict) or "claim" not in entry or "pattern" not in entry:
            raise DocStatusError(f"forbidden_claims entry missing claim/pattern: {entry!r}")
        try:
            out.append((entry["claim"], re.compile(entry["pattern"], re.IGNORECASE)))
        except re.error as exc:
            raise DocStatusError(f"bad forbidden-claim regex for {entry['claim']!r}: {exc}") from exc
    return out


# --------------------------------------------------------------------------- #
# Front-matter parsing.
# --------------------------------------------------------------------------- #
def split_front_matter(text: str) -> tuple[dict[str, Any] | None, str]:
    """Return (front_matter_mapping | None, body).

    Front matter is a leading ``---`` fenced YAML block. If absent, returns
    ``(None, text)``.
    """
    if not text.startswith("---"):
        return None, text
    lines = text.splitlines(keepends=True)
    # First line is the opening fence (``---`` possibly with trailing spaces).
    if lines[0].strip() != "---":
        return None, text
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            fm_text = "".join(lines[1:idx])
            body = "".join(lines[idx + 1 :])
            try:
                data = yaml.safe_load(fm_text)
            except yaml.YAMLError as exc:
                raise DocStatusError(f"unparseable front-matter YAML: {exc}") from exc
            if data is None:
                data = {}
            if not isinstance(data, dict):
                raise DocStatusError("front-matter must parse to a mapping")
            return data, body
    raise DocStatusError("front-matter opening '---' has no closing '---'")


def _strip_code(body: str) -> str:
    """Remove fenced code blocks and inline code so example claim words in
    commands/snippets are not read as prose assertions."""
    without_fences = re.sub(r"```.*?```", "", body, flags=re.DOTALL)
    return re.sub(r"`[^`\n]*`", "", without_fences)


# --------------------------------------------------------------------------- #
# Per-doc evaluation.
# --------------------------------------------------------------------------- #
def _parse_date(value: Any, field: str, rel: str) -> str:
    if isinstance(value, _dt.date):
        return value.isoformat()
    if not isinstance(value, str):
        raise DocStatusError(f"{rel}: {field} must be an ISO date, got {value!r}")
    try:
        _dt.date.fromisoformat(value)
    except ValueError as exc:
        raise DocStatusError(f"{rel}: {field} is not an ISO date: {value!r}") from exc
    return value


def evaluate_doc(
    path: Path,
    state: dict[str, Any],
    patterns: list[tuple[str, re.Pattern[str]]],
    rel: str | None = None,
) -> dict[str, Any]:
    """Validate one tagged doc and return its report record. Raises
    :class:`DocStatusError` on any structural problem (fail-closed)."""
    rel = rel or str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DocStatusError(f"cannot read tagged doc {rel}: {exc}") from exc

    front, body = split_front_matter(text)
    if front is None or "doc_status" not in front:
        raise DocStatusError(f"{rel}: no 'doc_status' front-matter block")
    meta = front["doc_status"]
    if not isinstance(meta, dict):
        raise DocStatusError(f"{rel}: doc_status must be a mapping")

    status = meta.get("status")
    if status not in VALID_STATUSES:
        raise DocStatusError(f"{rel}: status must be one of {VALID_STATUSES}, got {status!r}")

    authoritative_for = meta.get("authoritative_for")
    if not isinstance(authoritative_for, list) or not authoritative_for:
        raise DocStatusError(f"{rel}: authoritative_for must be a non-empty list")

    if "valid_from" not in meta:
        raise DocStatusError(f"{rel}: valid_from is required")
    valid_from = _parse_date(meta["valid_from"], "valid_from", rel)

    valid_to = meta.get("valid_to")
    if valid_to is not None:
        valid_to = _parse_date(valid_to, "valid_to", rel)
    superseded_by = meta.get("superseded_by")
    generated_by = meta.get("generated_by")
    defines_vocab = bool(meta.get("defines_claim_vocabulary", False))

    # A historical doc must record *why* it is no longer current.
    if status == "historical" and valid_to is None and not superseded_by:
        raise DocStatusError(
            f"{rel}: historical docs must declare 'valid_to' and/or 'superseded_by'"
        )

    record: dict[str, Any] = {
        "path": rel,
        "status": status,
        "authoritative_for": list(authoritative_for),
        "valid_from": valid_from,
        "valid_to": valid_to,
        "superseded_by": superseded_by,
        "generated_by": generated_by,
        "defines_claim_vocabulary": defines_vocab,
        "contradictions": [],
        "mention_exemptions": 0,
        "scanned": False,
    }

    # Only 'current' docs are held to the project-state maturity firewall.
    if status != "current":
        return record

    if defines_vocab:
        # The doc that defines the firewall names the forbidden words on
        # purpose; recorded, not scanned.
        return record

    record["scanned"] = True
    scan_source = _strip_code(body)
    exemptions = 0
    for raw_line in scan_source.splitlines():
        if MENTION_MARKER in raw_line:
            # Count only lines that actually mention a forbidden word.
            if any(pat.search(raw_line) for _claim, pat in patterns):
                exemptions += 1
            continue
        for claim, pat in patterns:
            m = pat.search(raw_line)
            if m:
                record["contradictions"].append(
                    {
                        "claim": claim,
                        "current_state": state["current_state"],
                        "matched_text": m.group(0),
                        "line": raw_line.strip()[:200],
                    }
                )
    record["mention_exemptions"] = exemptions
    record["contradictions"].sort(key=lambda c: (c["claim"], c["matched_text"]))
    return record


# --------------------------------------------------------------------------- #
# Report + driver.
# --------------------------------------------------------------------------- #
def build_report(
    docs: list[dict[str, Any]],
    state: dict[str, Any],
) -> dict[str, Any]:
    counts = {s: 0 for s in VALID_STATUSES}
    for d in docs:
        counts[d["status"]] += 1
    total_contradictions = sum(len(d["contradictions"]) for d in docs)
    flagged = [d["path"] for d in docs if d["contradictions"]]
    return {
        "gate": "check_doc_status",
        "current_state": state["current_state"],
        "project_version": (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        if (ROOT / "VERSION").exists()
        else None,
        "status": "FLAGGED" if total_contradictions else "PASS",
        "counts_by_status": counts,
        "doc_count": len(docs),
        "contradiction_count": total_contradictions,
        "flagged_docs": sorted(flagged),
        "docs": sorted(docs, key=lambda d: d["path"]),
    }


def _emit(report: dict[str, Any], report_path: Path | None) -> None:
    payload = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    print(payload)
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(payload + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Doc-status stale-current gate (DOC-003).")
    parser.add_argument("--doc", type=str, default=None, help="Gate a single doc instead of the tagged set.")
    parser.add_argument("--state-file", type=str, default=None, help="Override SSOT path.")
    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help=f"Write JSON report here (default set-mode target: {DEFAULT_REPORT}).",
    )
    parser.add_argument("--no-write", action="store_true", help="Do not write the report artifact.")
    args = parser.parse_args(argv)

    state_path = Path(args.state_file) if args.state_file else STATE_FILE
    try:
        state = load_state(state_path)
        patterns = _forbidden_patterns(state)
    except DocStatusError as exc:
        _emit({"gate": "check_doc_status", "status": "ERROR", "error": str(exc)}, None)
        return EXIT_ERROR

    if args.doc is not None:
        targets = [Path(args.doc)]
        rels = [args.doc]
        report_path = Path(args.report) if args.report else None
    else:
        targets = [ROOT / d for d in TAGGED_DOCS]
        rels = list(TAGGED_DOCS)
        if args.no_write:
            report_path = None
        else:
            report_path = Path(args.report) if args.report else DEFAULT_REPORT

    docs: list[dict[str, Any]] = []
    try:
        for path, rel in zip(targets, rels):
            docs.append(evaluate_doc(path, state, patterns, rel=rel))
    except DocStatusError as exc:
        _emit({"gate": "check_doc_status", "status": "ERROR", "error": str(exc)}, None)
        return EXIT_ERROR

    report = build_report(docs, state)
    _emit(report, report_path)
    return EXIT_FLAGGED if report["contradiction_count"] else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
