#!/usr/bin/env python3
"""CLI for the D-002L-P1 refusal-only Treasury announcement oracle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from research.systemic_risk.d002l_treasury_oracle import (
    D002LTreasuryOracleError,
    crosscheck_registry,
    parse_announcement_records,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--announcement-records", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
        records = parse_announcement_records(args.announcement_records.read_bytes())
        result = crosscheck_registry(registry, records)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print(f"ORACLE_MATCH samples={result['matched_sample_count']}")
        return 0
    except (OSError, json.JSONDecodeError, D002LTreasuryOracleError) as exc:
        print(f"ORACLE_REFUSE: {exc}", file=sys.stderr)
        return 10


if __name__ == "__main__":
    raise SystemExit(main())
