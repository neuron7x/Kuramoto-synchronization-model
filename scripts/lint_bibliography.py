#!/usr/bin/env python3
"""
Lint bibliography, citations, and claim mappings.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
BIB_PATH = ROOT / "docs" / "REFERENCES.bib"
CITATION_MAP_PATH = ROOT / "docs" / "CITATION_MAP.md"

REQUIRED_FIELDS = {"title", "author", "year"}
IDENTIFIER_FIELDS = {"doi", "isbn", "url"}
NEURO_KEYWORDS = (
    "serotonin",
    "basal ganglia",
    "free energy",
    "dopamine",
    "prediction error",
    r"\bRL\b",
)


class BibEntry:
    def __init__(self, key: str, fields: Dict[str, str]):
        self.key = key
        self.fields = fields


def parse_bibtex(path: Path) -> Dict[str, BibEntry]:
    entries: Dict[str, BibEntry] = {}
    current_key = None
    current_fields: Dict[str, str] = {}
    if not path.exists():
        raise FileNotFoundError(f"Missing bibliography file: {path}")

    entry_start = re.compile(r"@\w+\s*\{\s*([^,]+),")

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("@"):
            if current_key:
                entries[current_key] = BibEntry(current_key, current_fields)
                current_fields = {}
            match = entry_start.match(line)
            if not match:
                raise ValueError(f"Invalid BibTeX entry start: {line}")
            current_key = match.group(1).strip()
        elif line.startswith("}"):
            if current_key:
                entries[current_key] = BibEntry(current_key, current_fields)
                current_key, current_fields = None, {}
        else:
            if current_key and "=" in line:
                field_part, value_part = line.split("=", 1)
                field = field_part.strip().lower()
                value = value_part.strip().rstrip(",")
                if value.startswith("{") or value.startswith('"'):
                    value = value[1:]
                if value.endswith("}"):
                    value = value[:-1]
                if value.endswith('"'):
                    value = value[:-1]
                current_fields[field] = value.strip()
    if current_key:
        entries[current_key] = BibEntry(current_key, current_fields)
    return entries


def collect_doc_citations(root: Path) -> Set[str]:
    citations: Set[str] = set()
    citation_pattern = re.compile(r"\[@([A-Za-z0-9_\-\s;]+)\]")
    for path in root.rglob("*.md"):
        if ".github/agents" in str(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in citation_pattern.findall(text):
            for key in match.split(";"):
                cleaned = key.strip().lstrip("@")
                if cleaned:
                    citations.add(cleaned)
    return citations


def parse_citation_map(path: Path) -> List[Tuple[str, str, str, List[str]]]:
    rows: List[Tuple[str, str, str, List[str]]] = []
    if not path.exists():
        raise FileNotFoundError(f"Missing citation map: {path}")
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.startswith("| ---"):
            continue
        parts = [p.strip() for p in stripped.split("|")[1:-1]]
        if len(parts) < 5:
            continue
        claim_id, statement, location, code_path, citations_field = parts[:5]
        if claim_id.lower() == "claim id":
            continue
        if claim_id and (statement or location or code_path):
            citation_keys = re.findall(r"@([A-Za-z0-9_-]+)", citations_field)
            rows.append((claim_id, location, code_path, citation_keys))
    return rows


def check_required_fields(entry: BibEntry, errors: List[str]) -> None:
    missing = REQUIRED_FIELDS - set(entry.fields)
    if missing:
        errors.append(f"[{entry.key}] missing required fields: {', '.join(sorted(missing))}")
    if not any(field in entry.fields for field in IDENTIFIER_FIELDS):
        errors.append(f"[{entry.key}] missing identifier (one of doi/isbn/url)")


def check_duplicates(entries: Dict[str, BibEntry], errors: List[str]) -> None:
    seen: Dict[str, str] = {}
    for entry in entries.values():
        for field in ("doi", "isbn"):
            value = entry.fields.get(field)
            if value:
                key = f"{field}:{value.lower()}"
                if key in seen:
                    errors.append(
                        f"Duplicate {field} between {seen[key]} and {entry.key}: {value}"
                    )
                seen[key] = entry.key


def check_citation_map(rows: List[Tuple[str, str, str, List[str]]], errors: List[str]) -> None:
    ids: Set[str] = set()
    for claim_id, location, code_path, citations in rows:
        if claim_id in ids:
            errors.append(f"Duplicate Claim ID in CITATION_MAP.md: {claim_id}")
        ids.add(claim_id)
        if not citations:
            errors.append(f"Claim {claim_id} missing citations")
        if not location:
            errors.append(f"Claim {claim_id} missing 'Where in Repo' location")
        if not code_path:
            errors.append(f"Claim {claim_id} missing code mapping path")
    if not rows:
        errors.append("CITATION_MAP.md contains no claim rows")


def check_neuro_strictness(root: Path, errors: List[str]) -> None:
    neuro_roots = [
        root / "docs" / "neuro",
        root / "docs" / "neuromodulators",
    ]
    keyword_re = re.compile("|".join(NEURO_KEYWORDS), re.IGNORECASE)
    for neuro_root in neuro_roots:
        if not neuro_root.exists():
            continue
        for path in neuro_root.rglob("*.md"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "[heuristic]" in text.lower():
                continue
            if keyword_re.search(text) and "[@" not in text:
                errors.append(
                    f"{path.relative_to(root)} lacks citation for neuroscience keywords"
                )


def main() -> int:
    errors: List[str] = []

    try:
        entries = parse_bibtex(BIB_PATH)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Failed to parse {BIB_PATH}: {exc}")
        return 1

    if not entries:
        errors.append("No references found in docs/REFERENCES.bib")

    for entry in entries.values():
        check_required_fields(entry, errors)
    check_duplicates(entries, errors)

    citations_in_docs = collect_doc_citations(ROOT)
    for cite in sorted(citations_in_docs):
        if cite not in entries:
            errors.append(f"Missing BibTeX entry for citation key: {cite}")

    try:
        citation_rows = parse_citation_map(CITATION_MAP_PATH)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Failed to parse {CITATION_MAP_PATH}: {exc}")
        return 1

    check_citation_map(citation_rows, errors)

    map_citations = {c for _, _, _, cites in citation_rows for c in cites}
    missing_in_map = map_citations - citations_in_docs
    for key in sorted(missing_in_map):
        errors.append(f"Citation key {key} referenced in CITATION_MAP.md not found in docs")

    check_neuro_strictness(ROOT, errors)

    if errors:
        print("Bibliography lint failed:")
        for msg in errors:
            print(f" - {msg}")
        return 1

    print(f"Bibliography lint passed: {len(entries)} references, {len(citations_in_docs)} citations checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
