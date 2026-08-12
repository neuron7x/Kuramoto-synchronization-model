# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Resolve an L2 Ricci session's baseline/null/falsifier ids to a registry.

A declared ``baseline_id`` / ``null_model_id`` / ``falsifier_id`` is only
provenance if it RESOLVES to a registered, described reference. An id that names
nothing is an unfalsifiable placeholder wearing the costume of provenance: it
lets a session *claim* it was judged against a baseline, tested against a null,
and exposed to a falsifier without any of those reference objects existing.

This checker is the resolution gate for
``schemas/research/l2_ricci_session.schema.json``. It reads the reference
registry (``config/research/l2_ricci_registry.yaml`` by default) and the session
artifact, and reports, fail-closed, any of the three ids that does not resolve
to its registry section. The ``*_unset`` placeholder ids the ``--dry-run``
skeleton emits are intentionally absent from the registry, so a placeholder
skeleton never resolves — exactly as a placeholder must not.

This is additive to the #1116 protocol: it does not relax any existing gate. A
session that fails registry resolution cannot be promotion-ready even if its
hashes, replay, and negative evidence are otherwise complete.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = ROOT / "config" / "research" / "l2_ricci_registry.yaml"

#: Maps each session id field to the registry section it must resolve into.
#: This is the whole contract: a baseline_id resolves in ``baselines``, a
#: null_model_id in ``null_models``, a falsifier_id in ``falsifiers``.
ID_FIELD_TO_SECTION: dict[str, str] = {
    "baseline_id": "baselines",
    "null_model_id": "null_models",
    "falsifier_id": "falsifiers",
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_registry(registry_path: Path) -> dict[str, dict[str, Any]]:
    """Return the registry's reference sections as ``{section: {id: entry}}``.

    A section that is missing or not a mapping resolves to an empty mapping, so
    a malformed registry resolves *nothing* (every id then fails) rather than
    silently passing. Fail-closed by construction.
    """
    raw = _load_yaml(registry_path)
    sections: dict[str, dict[str, Any]] = {}
    raw_map = raw if isinstance(raw, dict) else {}
    for section in ID_FIELD_TO_SECTION.values():
        entries = raw_map.get(section)
        sections[section] = entries if isinstance(entries, dict) else {}
    return sections


def resolve_session_refs(
    artifact: dict[str, Any],
    sections: dict[str, dict[str, Any]],
    artifact_path: Path,
) -> list[str]:
    """Return errors for every id field that does not resolve to its section.

    A resolvable id is a non-empty string present as a key in the matching
    registry section whose entry carries a non-empty ``description`` (an entry
    with no description is a stub, not a reference, and does not resolve).
    """
    errors: list[str] = []
    for field, section in ID_FIELD_TO_SECTION.items():
        value = artifact.get(field)
        if not isinstance(value, str) or not value:
            errors.append(f"{artifact_path}: {field}: missing or non-string id")
            continue
        entry = sections.get(section, {}).get(value)
        if entry is None:
            errors.append(
                f"{artifact_path}: {field}: '{value}' does not resolve to any "
                f"registered '{section}' entry"
            )
            continue
        description = entry.get("description") if isinstance(entry, dict) else None
        if not isinstance(description, str) or not description.strip():
            errors.append(
                f"{artifact_path}: {field}: '{value}' resolves to a '{section}' "
                "entry with no description (stub, not a reference)"
            )
    return errors


def check_artifact(artifact_path: Path, registry_path: Path) -> list[str]:
    """Resolve all three id fields of one session artifact against the registry."""
    sections = load_registry(registry_path)
    artifact = _load_json(artifact_path)
    if not isinstance(artifact, dict):
        return [f"{artifact_path}: <root>: expected object"]
    return resolve_session_refs(artifact, sections, artifact_path)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact",
        type=Path,
        required=True,
        help="Session artifact JSON whose id refs are resolved against the registry.",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help="Reference registry YAML (default: config/research/l2_ricci_registry.yaml).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    failures = check_artifact(args.artifact, args.registry)
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print(f"Resolved L2 Ricci registry refs (baseline/null/falsifier): {args.artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
