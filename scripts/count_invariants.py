# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Single source of truth for the GeoSync invariant count.

Authoritative input: ``.claude/physics/INVARIANTS.yaml``.
Every documentation surface (README badges, BASELINE.md, CLAUDE.md
header, CI invariant-count gate) reads from this script — never from a
hand-edited literal — so the four-way ``57 / 66 / 67 / 87`` drift that
the 2026-04-30 external audit flagged cannot recur.

Usage::

    python scripts/count_invariants.py
    python scripts/count_invariants.py --json
    python scripts/count_invariants.py --field id  # count distinct IDs

Exit code is ``0`` on success and ``2`` on parse failure.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
INVARIANTS_PATH: Final[Path] = REPO_ROOT / ".claude" / "physics" / "INVARIANTS.yaml"

_ID_LINE: Final[re.Pattern[str]] = re.compile(r"^\s*id:\s*(INV-[A-Za-z0-9_-]+)\s*$")


def collect_invariant_ids(path: Path = INVARIANTS_PATH) -> list[str]:
    """Return the ordered list of unique ``INV-*`` identifiers in the registry.

    The parser is intentionally regex-based and not dependent on PyYAML so
    that the count gate has a zero-dependency footprint and runs in the
    same lightweight CI step as the kernel self-check.
    """
    if not path.is_file():
        raise FileNotFoundError(f"INVARIANTS registry not found at {path}")
    seen: set[str] = set()
    ordered: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        match = _ID_LINE.match(raw_line)
        if match is None:
            continue
        invariant_id = match.group(1)
        if invariant_id in seen:
            continue
        seen.add(invariant_id)
        ordered.append(invariant_id)
    return ordered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON {count, ids, source}",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=INVARIANTS_PATH,
        help="path to INVARIANTS.yaml (default: .claude/physics/INVARIANTS.yaml)",
    )
    args = parser.parse_args(argv)
    try:
        ids = collect_invariant_ids(args.path)
    except FileNotFoundError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    if args.json:
        json.dump(
            {
                "count": len(ids),
                "ids": ids,
                "source": str(args.path.relative_to(REPO_ROOT)),
            },
            sys.stdout,
            indent=2,
            sort_keys=True,
        )
        sys.stdout.write("\n")
    else:
        print(len(ids))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
