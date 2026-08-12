from __future__ import annotations

import json
from pathlib import Path

from tools.update_autonomy_trend import build_ledger


def test_trend_summary_tracks_latest_cycle(tmp_path: Path) -> None:
    cycle = tmp_path / "cycle.json"
    cycle.write_text(
        json.dumps(
            {
                "schema_version": "autonomy_cycle.v1",
                "phases": [{"status": "OK"}],
                "decision": {"state": "READY_FOR_NEXT_CYCLE"},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    ledger = build_ledger(cycle, tmp_path / "ledger.json", 20)
    entry = ledger["entries"][0]
    summary = ledger["summary"]
    assert summary["total_cycles"] == 1
    assert summary["decision_counts"] == {"READY_FOR_NEXT_CYCLE": 1}
    assert summary["latest_decision_state"] == entry["decision_state"]
    assert summary["latest_cycle_sha256"] == entry["cycle_sha256"]
