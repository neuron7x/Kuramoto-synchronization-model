"""Generate a canary Deployment manifest from a rendered manifest bundle.

This helper reads the rendered manifest archive produced during the deploy
workflow, extracts the `tradepulse-api` Deployment, and writes a canary copy
with the correct labels and annotations so it can be applied independently.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import yaml


def generate_canary(source_path: Path, dest_path: Path) -> None:
    documents = list(yaml.safe_load_all(source_path.read_text()))
    output_docs = []

    for doc in documents:
        if not isinstance(doc, dict):
            continue
        if doc.get("kind") != "Deployment" or doc.get("metadata", {}).get("name") != "tradepulse-api":
            continue
        canary = copy.deepcopy(doc)
        metadata = canary.setdefault("metadata", {})
        metadata["name"] = f"{metadata.get('name')}-canary"
        metadata.setdefault("labels", {})
        metadata["labels"]["app.kubernetes.io/instance"] = "canary"
        metadata.setdefault("annotations", {})
        metadata["annotations"]["tradepulse.io/canary"] = "true"

        spec = canary.setdefault("spec", {})
        spec["replicas"] = 1
        selector = spec.setdefault("selector", {}).setdefault("matchLabels", {})
        selector["app.kubernetes.io/instance"] = "canary"
        selector["app.kubernetes.io/track"] = "canary"

        template = spec.setdefault("template", {})
        template_metadata = template.setdefault("metadata", {})
        template_labels = template_metadata.setdefault("labels", {})
        template_labels["app.kubernetes.io/instance"] = "canary"
        template_labels["app.kubernetes.io/track"] = "canary"

        output_docs.append(canary)

    if not output_docs:
        raise SystemExit("Failed to generate canary deployment from manifest")

    dest_path.write_text("\n---\n".join(yaml.safe_dump(doc) for doc in output_docs))


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        raise SystemExit("Usage: render_canary_manifest.py <source> <dest>")

    source_path = Path(argv[1])
    dest_path = Path(argv[2])
    generate_canary(source_path, dest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
