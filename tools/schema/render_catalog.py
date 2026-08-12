# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Render a markdown catalogue of all registered event schemas."""

from __future__ import annotations

import argparse
from pathlib import Path

from core.messaging.schema_registry import EventSchemaRegistry


def _format_version_entry(entry: dict[str, str]) -> str:
    parts = [f"- **Version** `{entry['version']}`"]
    if "subject" in entry:
        parts.append(f"  - Subject: `{entry['subject']}`")
    if "namespace" in entry:
        parts.append(f"  - Namespace: `{entry['namespace']}`")
    formats = ", ".join(entry.get("formats", []))
    parts.append(f"  - Formats: {formats}")
    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render event schema catalogue")
    parser.add_argument("--registry", default="schemas/events", help="Path to registry directory")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/integrations/event_channels.md"),
        help="Destination markdown file",
    )
    args = parser.parse_args()

    registry = EventSchemaRegistry.from_directory(args.registry)
    catalogue = registry.catalogue()

    lines = ["# GeoSync Event Schema Catalogue", ""]
    lines.append(
        "This document is auto-generated from the canonical schema registry.\n"
        "It enumerates all events, their version history, and integration metadata."
    )
    lines.append("")

    for event, details in sorted(catalogue.items()):
        lines.append(f"## `{event}`")
        lines.append("")
        lines.append(f"- Latest version: `{details['latest']}`")
        if subjects := details.get("subjects"):
            lines.append("- Subjects:")
            for version, subject in subjects.items():
                lines.append(f"  - `{version}`: `{subject}`")
        if namespaces := details.get("namespaces"):
            lines.append("- Namespaces:")
            for version, namespace in namespaces.items():
                lines.append(f"  - `{version}`: `{namespace}`")
        lines.append("")
        lines.append("### Versions")
        lines.append("")
        for entry in details["versions"]:
            lines.append(_format_version_entry(entry))
            lines.append("")
        lines.append("---")
        lines.append("")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
