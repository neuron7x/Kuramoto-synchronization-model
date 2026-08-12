#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
REQ = {
    "schema_version",
    "contract_id",
    "research_line",
    "claim_boundary",
    "state_machine",
    "data_model",
    "blocks",
    "gates",
    "outputs",
    "agent_handoff",
}
VIRTUAL_BLOCKS = {"agent_orchestrator"}


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"not an object: {path}")
    return data


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"not an object: {path}")
    return data


def schema_kinds(schema: dict[str, Any]) -> set[str]:
    return set(
        schema.get("$defs", {})
        .get("block", {})
        .get("properties", {})
        .get("kind", {})
        .get("enum", [])
    )


def add(errors: list[str], ok: bool, msg: str) -> None:
    if not ok:
        errors.append(msg)


def validate_contract(
    schema_path: Path, config_path: Path, map_path: Path, root: Path = ROOT
) -> dict[str, Any]:
    schema = load_json(schema_path)
    cfg = load_yaml(config_path)
    block_map = load_json(map_path)
    errors: list[str] = []

    missing = sorted(REQ.difference(cfg))
    add(errors, not missing, f"missing keys: {missing}")
    if missing:
        raise ValueError("; ".join(errors))

    boundary = cfg["claim_boundary"]
    add(errors, boundary.get("tier") == "HYPOTHESIS", "tier drift")
    add(errors, bool(boundary.get("allowed_language")), "empty allowed_language")
    add(errors, bool(boundary.get("forbidden_promotions")), "empty forbidden list")

    state = cfg["state_machine"]
    allowed_states = set(state.get("allowed", []))
    terminal_states = set(state.get("terminal", []))
    add(errors, state.get("initial") in allowed_states, "bad initial state")
    add(errors, not allowed_states.intersection(terminal_states), "state overlap")

    kinds = schema_kinds(schema)
    blocks = cfg.get("blocks", [])
    block_ids = [b.get("id") for b in blocks if isinstance(b, dict)]
    add(errors, bool(block_ids), "no blocks")
    add(errors, len(block_ids) == len(set(block_ids)), "duplicate block id")
    for block in blocks:
        add(errors, block.get("kind") in kinds, f"bad block kind: {block.get('id')}")

    block_id_set = set(block_ids) | VIRTUAL_BLOCKS
    for gate in cfg.get("gates", []):
        refs = set(gate.get("blocks", []))
        add(
            errors,
            not refs.difference(block_id_set),
            f"gate refs missing: {sorted(refs.difference(block_id_set))}",
        )
        add(errors, bool(str(gate.get("command", "")).strip()), "empty gate command")

    for out in cfg.get("outputs", []):
        add(errors, (root / out["path"]).exists(), f"missing output: {out['path']}")

    add(
        errors, block_map.get("research_line") == cfg.get("research_line"), "research_line mismatch"
    )
    add(errors, block_map.get("claim_tier") == boundary.get("tier"), "tier mismatch")
    add(errors, block_map.get("promotion_locked") is True, "lock drift")
    primitives = block_map.get("architecture_primitives", [])
    primitive_ids = [p.get("id") for p in primitives if isinstance(p, dict)]
    add(errors, bool(primitive_ids), "no primitives")
    add(errors, len(primitive_ids) == len(set(primitive_ids)), "duplicate primitive id")

    if errors:
        raise ValueError("; ".join(errors))
    return {
        "status": "PASS",
        "contract_id": cfg["contract_id"],
        "research_line": cfg["research_line"],
        "claim_tier": boundary["tier"],
        "blocks": len(blocks),
        "gates": len(cfg["gates"]),
        "primitives": len(primitives),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--schema",
        type=Path,
        default=ROOT / "schemas/research/inference_transformer_contract.schema.json",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/research/geosync_inference_transformer.v1.yaml",
    )
    parser.add_argument(
        "--map", type=Path, default=ROOT / "data/research/inference_transformer_blocks.v1.json"
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        print(json.dumps(validate_contract(args.schema, args.config, args.map), sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
