#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from tools.check_json_contract_evidence_policy import check_policy
from tools.validate_json_artifact_contract import validate_contract

DEFAULT_INPUTS = (
    Path("examples/json_artifact_contract.candidate.json"),
    Path("examples/json_artifact_contract.blocked.json"),
)


def _load(path: Path) -> tuple[dict[str, Any] | None, list[str], dict[str, object]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, [f"read_error:{exc}"], {"bytes": None, "sha256": None}
    meta = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    try:
        data = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        return None, [f"utf8_error:{exc.start}"], meta
    except json.JSONDecodeError as exc:
        return None, [f"json_error:{exc.lineno}:{exc.colno}"], meta
    if not isinstance(data, dict):
        return None, ["root_object_required"], meta
    return data, [], meta


def build(paths: list[Path]) -> dict[str, object]:
    seen: set[str] = set()
    items: list[dict[str, object]] = []
    for path in paths:
        key = str(path)
        repeated = key in seen
        seen.add(key)
        data, load_errors, meta = _load(path)
        contract_errors: list[str] = []
        policy_errors: list[str] = []
        if data is not None:
            contract_errors = validate_contract(data)
            policy_errors = check_policy(data)
        errors = ["repeated_path"] if repeated else []
        errors += load_errors + contract_errors + policy_errors
        item = {
            "path": key,
            "status": "OK" if not errors else "ERROR",
            "errors": errors,
        }
        item.update(meta)
        items.append(item)
    ok_count = sum(1 for item in items if item["status"] == "OK")
    return {
        "schema_version": "json_contract_receipt.v1",
        "status": "OK" if ok_count == len(items) else "ERROR",
        "item_count": len(items),
        "ok_count": ok_count,
        "error_count": len(items) - ok_count,
        "items": items,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument(
        "--out", type=Path, default=Path("artifacts/validation/json_contract_receipt.json")
    )
    args = parser.parse_args(argv)
    result = build(args.paths or list(DEFAULT_INPUTS))
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0 if result["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
