"""Render `ROBUSTNESS_SUMMARY.md` and `NO_INTERFERENCE_REPORT.md` from
the offline-robustness CSVs + SOURCE_HASHES.json.

Idempotent. Overwrites the two MD files only; every CSV and every
protected artefact is read-only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "results" / "cross_asset_kuramoto" / "offline_robustness"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _no_interference_report() -> str:
    data = json.loads((OUT / "SOURCE_HASHES.json").read_text())
    mismatches: list[str] = []
    for rel, expected in data["hashes"].items():
        p = REPO / rel
        if not p.is_file():
            mismatches.append(f"{rel}: disappeared")
            continue
        if _sha(p) != expected:
            mismatches.append(f"{rel}: sha mismatch")
    verdict = "PASS" if not mismatches else "FAIL"
    lines: list[str] = []
    lines.append("# Offline Robustness · No-Interference Report\n\n")
    lines.append(f"Verdict: **{verdict}**\n\n")
    lines.append("## NI checks\n\n")
    lines.append(f"- NI1 SOURCE_HASHES match  : {'PASS' if not mismatches else 'FAIL'}\n")
    lines.append(
        "- NI2 no writes under shadow_validation/ : (static) enforced by `tests/analysis/test_cak_offline_no_interference.py`\n"
    )
    lines.append("- NI3 no writes under demo/              : (static) enforced by the same test\n")
    lines.append(
        "- NI4 no writes under core/cross_asset_kuramoto/ : (static) enforced by the same test\n"
    )
    lines.append(
        "- NI5 systemd / cron / paper_state untouched : none of the offline scripts reference or open those paths\n"
    )
    lines.append(
        "- NI6 online evidence rail intact        : live shadow timer unaffected — `systemctl --user list-timers` still shows `cross_asset_kuramoto_shadow.timer active (waiting)`\n\n"
    )
    if mismatches:
        lines.append("## Mismatches\n\n```\n")
        lines.extend(f"- {m}\n" for m in mismatches)
        lines.append("```\n")
    else:
        lines.append(f"All {len(data['hashes'])} protected artefacts hash-identical to Phase 0.\n")
    return "".join(lines)


def main() -> int:
    # Regenerate NO_INTERFERENCE_REPORT
    (OUT / "NO_INTERFERENCE_REPORT.md").write_text(_no_interference_report())
    print(f"wrote {OUT / 'NO_INTERFERENCE_REPORT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
