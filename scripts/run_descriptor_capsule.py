#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""One-command runner for the integrated descriptor replay capsule.

Chains null_baseline → state_quantization → null_comparison →
descriptor_information_quality → descriptor_metadata and prints the
deterministic capsule manifest (digest, metadata, observed-vs-null rank,
information-quality, claim-safe fields) as JSON.

Run::

    python scripts/run_descriptor_capsule.py --config-json '{"observed": [0.1, -0.2, 0.4],
        "thresholds": [-0.5, 0.5], "labels": ["low", "mid", "high"], "null_seed": 42}'
    python scripts/run_descriptor_capsule.py --config-file capsule_config.json

The same config yields a byte-identical manifest and ``manifest_digest``.
Descriptor-only research infrastructure; emits no predictive or financial claim.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from analytics.signals.descriptor_capsule import build_capsule


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--config-json", type=str, help="inline JSON config object")
    group.add_argument("--config-file", type=Path, help="path to a JSON config file")
    args = parser.parse_args(argv)

    if args.config_json is not None:
        raw = args.config_json
    else:
        raw = args.config_file.read_text(encoding="utf-8")

    try:
        config: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"FAIL: config is not valid JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(config, dict):
        print("FAIL: config must be a JSON object", file=sys.stderr)
        return 2

    try:
        manifest = build_capsule(config)
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(manifest, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
