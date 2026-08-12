from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.update_autonomy_trend import _rooted, build_ledger


def _cycle(path: Path, state: str = "READY_FOR_NEXT_CYCLE", statuses: list[str] | None = None) -> None:
    vector = statuses or ["OK", "OK", "OK"]
    path.write_text(
        json.dumps(
            {
                "schema_version": "autonomy_cycle.v1",
                "phases": [
                    {"phase": f"phase_{index}", "status": status}
                    for index, status in enumerate(vector, start=1)
                ],
                "decision": {"state": state, "status_vector": vector},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def test_build_ledger_records_cycle_digest(tmp_path: Path) -> None:
    cycle = tmp_path / "cycle.json"
    ledger_path = tmp_path / "trend.json"
    _cycle(cycle)
    ledger = build_ledger(cycle, ledger_path, 20)
    assert ledger["schema_version"] == "autonomy_trend.v1"
    entry = ledger["entries"][0]
    assert entry["sequence"] == 1
    assert entry["cycle_schema_version"] == "autonomy_cycle.v1"
    assert len(entry["cycle_sha256"]) == 64
    assert entry["decision_state"] == "READY_FOR_NEXT_CYCLE"
    assert entry["status_vector"] == ["OK", "OK", "OK"]
    assert entry["status_counts"] == {"OK": 3}
    assert entry["phase_count"] == 3
    assert ledger["summary"]["status_counts"] == {"OK": 3}
    assert ledger["summary"]["phase_count_total"] == 3


def test_build_ledger_respects_limit(tmp_path: Path) -> None:
    cycle = tmp_path / "cycle.json"
    ledger_path = tmp_path / "trend.json"
    _cycle(cycle, "OBSERVE_WITH_DEBT", ["OK", "WARN"])
    ledger_path.write_text(
        json.dumps(
            {
                "schema_version": "autonomy_trend.v1",
                "entries": [
                    {
                        "sequence": 1,
                        "cycle_schema_version": "autonomy_cycle.v1",
                        "cycle_sha256": "0" * 64,
                        "decision_state": "READY_FOR_NEXT_CYCLE",
                        "status_vector": ["OK"],
                        "status_counts": {"OK": 1},
                        "phase_count": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    ledger = build_ledger(cycle, ledger_path, 1)
    assert len(ledger["entries"]) == 1
    assert ledger["entries"][0]["decision_state"] == "OBSERVE_WITH_DEBT"
    assert ledger["entries"][0]["status_counts"] == {"OK": 1, "WARN": 1}


def test_build_ledger_aggregates_status_counts(tmp_path: Path) -> None:
    cycle = tmp_path / "cycle.json"
    ledger_path = tmp_path / "trend.json"
    _cycle(cycle, "REPAIR_REQUIRED", ["OK", "RED", "RED"])
    ledger_path.write_text(
        json.dumps(
            {
                "schema_version": "autonomy_trend.v1",
                "entries": [
                    {
                        "sequence": 4,
                        "cycle_schema_version": "autonomy_cycle.v1",
                        "cycle_sha256": "a" * 64,
                        "decision_state": "OBSERVE_WITH_DEBT",
                        "status_vector": ["OK", "WARN"],
                        "status_counts": {"OK": 1, "WARN": 1},
                        "phase_count": 2,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    ledger = build_ledger(cycle, ledger_path, 20)
    assert ledger["entries"][-1]["sequence"] == 5
    assert ledger["summary"]["status_counts"] == {"OK": 2, "RED": 2, "WARN": 1}
    assert ledger["summary"]["phase_count_total"] == 5


def test_rooted_keeps_absolute_path(tmp_path: Path) -> None:
    absolute = tmp_path / "cycle.json"
    assert _rooted(tmp_path / "repo", str(absolute)) == absolute


def test_rooted_resolves_relative_path(tmp_path: Path) -> None:
    assert _rooted(tmp_path, "artifacts/trend.json") == tmp_path / "artifacts" / "trend.json"


def test_build_ledger_rejects_non_positive_limit(tmp_path: Path) -> None:
    cycle = tmp_path / "cycle.json"
    _cycle(cycle)
    with pytest.raises(ValueError, match="limit"):
        build_ledger(cycle, tmp_path / "trend.json", 0)
