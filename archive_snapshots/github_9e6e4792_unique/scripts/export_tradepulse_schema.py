"""Utility for exporting the TradePulse configuration JSON schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.config import export_tradepulse_settings_schema


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export the TradePulse configuration JSON schema",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional destination path for the generated schema. Prints to stdout when omitted.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Indentation level used when writing the schema to disk (default: 2).",
    )
    return parser.parse_args(args)


def main() -> None:
    args = parse_args()
    schema = export_tradepulse_settings_schema(args.output, indent=args.indent)
    if args.output is None:
        json.dump(schema, fp=sys.stdout, indent=args.indent, sort_keys=True)
        sys.stdout.write("\n")


if __name__ == "__main__":  # pragma: no cover - manual tool
    main()
