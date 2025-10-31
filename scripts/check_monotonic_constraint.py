"""Fail fast when thermodynamic audit logs show monotonic violations."""

from __future__ import annotations

import sys
from pathlib import Path


AUDIT_LOG = Path("observability/audit/thermo_audit.log")


def main() -> int:
    if not AUDIT_LOG.exists():
        print("No thermodynamic audit log found; assuming clean run.")
        return 0

    try:
        lines = [line.strip() for line in AUDIT_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError as exc:  # pragma: no cover - defensive fallback
        print(f"Failed to read {AUDIT_LOG}: {exc}", file=sys.stderr)
        return 1

    if not lines:
        print("Thermodynamic audit log present but empty; all good.")
        return 0

    print("Monotonic constraint violations detected – review required:", file=sys.stderr)
    for line in lines:
        print(line, file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
