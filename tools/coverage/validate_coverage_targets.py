#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tools.coverage.surface_contract import (
    list_unmapped_files,
    load_coverage_targets,
    map_file_to_surface,
    validate_target_contract,
)

CRITICAL_PREFIXES = (
    "core/",
    "backtest/",
    "execution/",
    "analytics/",
    "ingestion/",
    "risk/",
    "data/",
)


def _normalize_repo_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _prefix_matches(file_path: str, prefix: str) -> bool:
    if prefix.endswith("/"):
        return file_path.startswith(prefix)
    return file_path == prefix or file_path.startswith(f"{prefix}/")


def _read_files(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(path)
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


def _is_critical(file_path: str) -> bool:
    normalized = _normalize_repo_path(file_path)
    return any(_prefix_matches(normalized, prefix) for prefix in CRITICAL_PREFIXES)


def _json_payload(
    targets_path: Path, targets: Any, unmapped: list[str], errors: list[str]
) -> dict[str, Any]:
    surfaces: dict[str, Any] = {}
    for name, cfg in targets.surfaces.items():
        surfaces[name] = {
            "paths": list(cfg.paths),
            "short_term": cfg.short_term,
            "mid_term": cfg.mid_term,
            "final": cfg.final,
            "claim_risk": cfg.claim_risk,
        }
    payload = {
        "schema_version": "1.0",
        "status": "fail" if errors else "pass",
        "targets_path": str(targets_path),
        "surfaces": surfaces,
        "unmapped_files": unmapped,
        "errors": errors,
    }
    if targets.weights is not None:
        payload["weights"] = {
            "divergence": targets.weights.divergence,
            "convergence": targets.weights.convergence,
        }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate coverage surface target contract.")
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--files", type=Path, required=False)
    parser.add_argument("--json-out", type=Path, required=False)
    args = parser.parse_args()

    errors: list[str] = []
    unmapped_files: list[str] = []
    supplied_files: list[str] = []

    try:
        targets = load_coverage_targets(args.targets)
    except (FileNotFoundError, ValueError) as exc:
        errors.append(str(exc))
        targets = None

    if targets is not None:
        errors.extend(validate_target_contract(targets))
        if args.files is not None:
            try:
                supplied_files = _read_files(args.files)
            except OSError as exc:
                errors.append(str(exc))
            else:
                unmapped_files = list_unmapped_files(supplied_files, targets)
                critical_unmapped = [
                    file_path for file_path in unmapped_files if _is_critical(file_path)
                ]
                if critical_unmapped:
                    errors.append(
                        "Critical supplied files are unmapped: "
                        + ", ".join(sorted(critical_unmapped))
                    )

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        if targets is not None:
            payload = _json_payload(args.targets, targets, unmapped_files, errors)
        else:
            payload = {
                "schema_version": "1.0",
                "status": "fail",
                "targets_path": str(args.targets),
                "surfaces": {},
                "unmapped_files": [],
                "errors": errors,
            }
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if errors:
        for err in errors:
            print(f"ERROR: {err}")
        return 1

    print(f"Coverage target contract is valid: {args.targets}")
    if args.files is not None and targets is not None and supplied_files:
        mapped = [
            file_path
            for file_path in supplied_files
            if map_file_to_surface(file_path, targets) is not None
        ]
        print(f"Mapped files: {len(mapped)}")
        print(f"Unmapped files: {len(unmapped_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
