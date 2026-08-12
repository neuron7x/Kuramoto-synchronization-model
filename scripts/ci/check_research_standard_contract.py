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
    "standard_id",
    "status",
    "scope",
    "layers",
    "required_manifests",
    "release_gates",
    "handoff",
}


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


def add(errors: list[str], ok: bool, msg: str) -> None:
    if not ok:
        errors.append(msg)


def validate_standard(config_path: Path, layer_map_path: Path, root: Path = ROOT) -> dict[str, Any]:
    cfg = load_yaml(config_path)
    layer_map = load_json(layer_map_path)
    errors: list[str] = []

    missing = sorted(REQ.difference(cfg))
    add(errors, not missing, f"missing keys: {missing}")
    if missing:
        raise ValueError("; ".join(errors))

    add(errors, cfg["status"] == "DRAFT", "standard status must remain DRAFT")
    scope = cfg["scope"]
    add(errors, scope.get("evidence_level") == "HYPOTHESIS", "evidence level drift")
    add(errors, bool(scope.get("non_goals")), "non_goals must be non-empty")

    layers = cfg.get("layers", [])
    layer_ids = [layer.get("id") for layer in layers if isinstance(layer, dict)]
    add(errors, len(layer_ids) >= 5, "at least five layers required")
    add(errors, len(layer_ids) == len(set(layer_ids)), "duplicate layer id")
    required_layer_ids = {
        "claim_governance",
        "data_lineage",
        "method_certification",
        "experiment_epistemics",
        "release_provenance",
    }
    add(errors, required_layer_ids.issubset(set(layer_ids)), "required layer missing")

    manifest_paths = []
    for manifest in cfg.get("required_manifests", []):
        path = root / str(manifest.get("path", ""))
        manifest_paths.append(str(manifest.get("path", "")))
        if manifest.get("must_exist") is True:
            add(errors, path.exists(), f"missing manifest: {manifest.get('path')}")
            if path.exists():
                payload = load_json(path)
                add(
                    errors,
                    payload.get("status") == "DRAFT",
                    f"manifest not DRAFT: {manifest.get('path')}",
                )
                add(
                    errors,
                    bool(payload.get("required_fields")),
                    f"manifest missing required_fields: {manifest.get('path')}",
                )

    gates = cfg.get("release_gates", [])
    gate_ids = [gate.get("id") for gate in gates if isinstance(gate, dict)]
    add(errors, len(gate_ids) >= 3, "at least three gates required")
    add(errors, len(gate_ids) == len(set(gate_ids)), "duplicate gate id")
    for gate in gates:
        add(
            errors,
            bool(str(gate.get("command", "")).strip()),
            f"empty gate command: {gate.get('id')}",
        )
        add(
            errors, gate.get("blocks_release") is True, f"gate must block release: {gate.get('id')}"
        )

    add(errors, layer_map.get("standard_id") == cfg.get("standard_id"), "standard id mismatch")
    add(
        errors,
        layer_map.get("evidence_level") == scope.get("evidence_level"),
        "layer map evidence mismatch",
    )
    waves = layer_map.get("waves", [])
    add(errors, len(waves) == 4, "four waves required")
    roles = set(layer_map.get("required_roles", []))
    add(
        errors,
        {
            "research_lead",
            "methods_lead",
            "data_lead",
            "platform_lead",
            "security_lead",
            "external_reviewer",
        }.issubset(roles),
        "role set incomplete",
    )

    if errors:
        raise ValueError("; ".join(errors))
    return {
        "status": "PASS",
        "standard_id": cfg["standard_id"],
        "research_line": scope["research_line"],
        "evidence_level": scope["evidence_level"],
        "layers": len(layers),
        "manifests": len(manifest_paths),
        "gates": len(gates),
        "waves": len(waves),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=ROOT / "configs/research/geosync_research_standard.v1.yaml"
    )
    parser.add_argument(
        "--layers", type=Path, default=ROOT / "data/research/research_standard_layers.v1.json"
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        print(json.dumps(validate_standard(args.config, args.layers), sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
