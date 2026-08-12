#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "src/geosync/research/transformer"
PIPELINE = BASE / "pipeline.py"
OUT = ROOT / "artifacts/runs/ricci_microstructure_v1/inference_transformer_placeholder.json"


def shim(name: str, path: Path) -> None:
    mod = types.ModuleType(name)
    mod.__path__ = [str(path)]
    sys.modules.setdefault(name, mod)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--git-sha", default="0" * 40)
    args = parser.parse_args(argv)
    shim("src", ROOT / "src")
    shim("src.geosync", ROOT / "src/geosync")
    shim("src.geosync.research", ROOT / "src/geosync/research")
    shim("src.geosync.research.transformer", BASE)
    spec = importlib.util.spec_from_file_location(
        "src.geosync.research.transformer.pipeline", PIPELINE
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("pipeline import failed")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    artifact = module.write_placeholder_artifact(args.output, git_sha=args.git_sha)
    print(
        json.dumps(
            {
                "status": "PASS",
                "output": str(args.output),
                "output_sha256": artifact["output_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
