# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Utility to build a registry of AI related assets in the GeoSync codebase.

The script scans one or more repository roots for trained model artefacts,
training scripts and dataset definitions, then exports a JSON file that
summarises what was found.  It is intentionally lightweight so it can run as
part of CI or a local developer workflow.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

LOGGER = logging.getLogger(__name__)


MODEL_EXTENSIONS = {".pkl", ".pt", ".h5", ".onnx", ".joblib"}
TRAINING_KEYWORDS = {"train", "trainer", "fit", "pipeline"}
TRAINING_EXTENSIONS = {".py", ".ipynb"}
DATASET_EXTENSIONS = {".csv", ".parquet", ".json", ".feather"}


@dataclass(slots=True)
class AssetRecord:
    """Structured representation of an AI asset."""

    name: str
    path: str
    kind: str
    description: str | None = None


def _is_training_script(path: Path) -> bool:
    """Return True when the file should be treated as a training asset."""

    if path.suffix not in TRAINING_EXTENSIONS:
        return False
    stem = path.stem.lower()
    return any(keyword in stem for keyword in TRAINING_KEYWORDS)


def _derive_description(asset: AssetRecord) -> str:
    """Provide a human readable description for an asset."""

    if asset.kind == "model":
        return "Trained model artefact"
    if asset.kind == "training_script":
        return "Model training or pipeline definition"
    if asset.kind == "dataset":
        return "Dataset or feature store extract"
    return "AI related asset"


def discover_assets(roots: Sequence[Path]) -> List[AssetRecord]:
    """Collect all matching AI assets within the provided repository roots."""

    discovered: list[AssetRecord] = []
    for root in roots:
        if not root.exists():
            LOGGER.debug("Skipping missing path %s", root)
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            try:
                relative_path = path.relative_to(Path.cwd())
            except ValueError:
                relative_path = path

            if suffix in MODEL_EXTENSIONS:
                discovered.append(
                    AssetRecord(
                        name=path.stem,
                        path=str(relative_path),
                        kind="model",
                    )
                )
            elif suffix in DATASET_EXTENSIONS:
                discovered.append(
                    AssetRecord(
                        name=path.stem,
                        path=str(relative_path),
                        kind="dataset",
                    )
                )
            elif _is_training_script(path):
                discovered.append(
                    AssetRecord(
                        name=path.stem,
                        path=str(relative_path),
                        kind="training_script",
                    )
                )

    for asset in discovered:
        if not asset.description:
            asset.description = _derive_description(asset)
    return discovered


def serialize_assets(assets: Iterable[AssetRecord]) -> list[dict[str, str]]:
    """Convert records into dictionaries suitable for JSON output."""

    return [asdict(asset) for asset in assets]


def save_registry(assets: Sequence[AssetRecord], output: Path) -> None:
    """Persist the collected assets into ``output`` as JSON."""

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        json.dump(serialize_assets(assets), handle, indent=2)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan repository for AI assets")
    parser.add_argument(
        "--roots",
        nargs="*",
        default=[
            "analytics",
            "application",
            "core",
            "geosync_hpc",
            "strategies",
            "observability",
        ],
        help="Root directories to scan",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("registry/assets_registry.json"),
        help="Path to the JSON file that will be written",
    )
    return parser


def main(args: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    parsed = parser.parse_args(args)

    roots = [Path(root) for root in parsed.roots]
    LOGGER.info("Scanning %d roots for AI assets", len(roots))
    assets = discover_assets(roots)
    LOGGER.info("Discovered %d assets", len(assets))
    save_registry(assets, parsed.output)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
