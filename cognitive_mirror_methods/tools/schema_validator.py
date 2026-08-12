from __future__ import annotations

import json
import sys
from pathlib import Path


def validate_schema_file(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: schema must be a JSON object")
    if "$schema" not in data:
        raise ValueError(f"{path}: missing $schema")
    if "type" not in data:
        raise ValueError(f"{path}: missing type")


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    root = Path(args[0]) if args else Path("cognitive_mirror_methods/schemas")
    files = sorted(root.rglob("*.json")) if root.is_dir() else [root]
    for file in files:
        validate_schema_file(file)
    print(f"validated {len(files)} schema file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
