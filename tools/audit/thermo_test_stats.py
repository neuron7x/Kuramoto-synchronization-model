from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict

REPO_ROOT = Path(__file__).resolve().parents[2]
_ORIGINAL_SYS_PATH = list(sys.path)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.audit._stats_common import collect_stats

sys.path[:] = _ORIGINAL_SYS_PATH


def collect_thermo_stats(base_dir: str | Path | None = None) -> Dict[str, object]:
    return collect_stats("thermo", base_dir)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect thermodynamics-related pytest statistics."
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write JSON output (default: stdout).",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        help="Base repository directory (defaults to repository root).",
    )
    args = parser.parse_args()

    stats = collect_thermo_stats(args.base_dir)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    else:
        json.dump(stats, sys.stdout, indent=2)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
