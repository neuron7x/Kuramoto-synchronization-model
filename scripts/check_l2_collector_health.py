#!/usr/bin/env python3
"""Long-running L2 collector health check — CLI over longrun_monitor.

Intended invocation: cron every ~60 s, or systemd watchdog sidecar.

Exit codes:
    0 — HEALTHY
    1 — DEGRADED
    2 — STALE
    3 — UNREACHABLE (log missing or no flush ever)
"""

from __future__ import annotations

# Standalone bootstrap: this gate must be runnable as `python <path>` from any
# cwd, not only via `python -m` from the repo root. The needed first-party
# package is registered by file location (no sys.path mutation — the
# import-architecture ratchet forbids path hacks; repo tooling, never shipped).
import importlib.util as _ilu
import sys as _sys
from pathlib import Path as _Path


def _ensure_pkg(_name: str, _pkg_dir: "_Path") -> None:
    _existing = _sys.modules.get(_name)
    if _existing is None:
        try:
            _existing = __import__(_name)
        except ModuleNotFoundError:
            _existing = None
    if _existing is not None:
        _existing_path = next(iter(getattr(_existing, "__path__", [])), "")
        if _Path(_existing_path).resolve() == _pkg_dir.resolve():
            return
        # An alien same-named package is importable (e.g. a stale editable
        # install of another repo). Trusting it means running foreign code —
        # shadow it with THIS repo's package for this process.
        _sys.modules.pop(_name, None)
    _spec = _ilu.spec_from_file_location(
        _name, _pkg_dir / "__init__.py", submodule_search_locations=[str(_pkg_dir)]
    )
    assert _spec and _spec.loader
    _mod = _ilu.module_from_spec(_spec)
    _sys.modules[_name] = _mod
    _spec.loader.exec_module(_mod)


_GS_REPO_ROOT = _Path(__file__).resolve().parents[1]
_ensure_pkg("research", _GS_REPO_ROOT / "research")

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from research.microstructure.longrun_monitor import (
    parse_log_tail,
    read_log_tail,
)

_EXIT = {"HEALTHY": 0, "DEGRADED": 1, "STALE": 2, "UNREACHABLE": 3}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log",
        type=Path,
        default=Path("logs/collector_longrun.log"),
        help="Path to collector log file",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=256 * 1024,
        help="Max bytes to read from tail of log (default 256 KiB)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional append-only JSONL history path",
    )
    args = parser.parse_args()

    text = read_log_tail(Path(args.log), max_bytes=int(args.max_bytes))
    now = datetime.now(timezone.utc)
    report = parse_log_tail(text, now_utc=now)
    payload = asdict(report)
    payload["log_path"] = str(args.log)

    print(json.dumps(payload, indent=2, sort_keys=True, default=str))

    if args.output is not None:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a") as fh:
            fh.write(
                json.dumps({**payload, "checked_at_utc": now.isoformat(timespec="seconds")}) + "\n"
            )

    return _EXIT.get(report.verdict, 3)


if __name__ == "__main__":
    sys.exit(main())
