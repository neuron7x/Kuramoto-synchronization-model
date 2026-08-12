#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.check_json_contract_evidence_policy import check_policy
from tools.validate_json_artifact_contract import validate_contract

DEFAULT_INPUTS = (
    Path("examples/json_artifact_contract.candidate.json"),
    Path("examples/json_artifact_contract.blocked.json"),
)


def _load(path: Path) -> tuple[dict[str, object] | None, list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"invalid_json:{exc.lineno}:{exc.colno}"]
    except OSError as exc:
        return None, [f"read_error:{exc}"]
    if not isinstance(data, dict):
        return None, ["root_must_be_object"]
    return data, []


def build(paths: list[Path]) -> dict[str, object]:
    items: list[dict[str, object]] = []
    overall = "OK"
    for path in paths:
        data, load_errors = _load(path)
        contract_errors: list[str] = []
        policy_errors: list[str] = []
        if data is not None:
            contract_errors = validate_contract(data)
            policy_errors = check_policy(data)
        errors = load_errors + contract_errors + policy_errors
        status = "OK" if not errors else "ERROR"
        if errors:
            overall = "ERROR"
        items.append(
            {
                "path": str(path),
                "status": status,
                "load_errors": load_errors,
                "contract_errors": contract_errors,
                "policy_errors": policy_errors,
            }
        )
    return {
        "schema_version": "json_contract_validation_bundle.v1",
        "status": overall,
        "items": items,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts/validation/json_contract_validation_bundle.json"),
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
