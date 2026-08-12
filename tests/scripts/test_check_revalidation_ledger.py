# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Revalidation-ledger gate — self-falsification proof (DEBT_5).

``scripts/ci/check_revalidation_ledger.py`` must PASS on the shipped
``governance/REVALIDATION_LEDGER.yaml`` and FAIL CLOSED when a ledger entry is
malformed, when a lane is laundered (REPLAYED without a real-oracle sha or a
preserved evidence artifact, BOUNDED without a residual, promotion language in
a note), and EXIT 2 when the ledger itself is missing or malformed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "ci" / "check_revalidation_ledger.py"
REGISTRY_PATH = ROOT / "governance" / "REVALIDATION_LEDGER.yaml"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("check_revalidation_ledger", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_revalidation_ledger"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate() -> Any:
    return _load()


@pytest.fixture(scope="module")
def live() -> dict[str, Any]:
    return yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))


def _entry(live: dict[str, Any]) -> dict[str, Any]:
    return dict(live["entries"][0])


def _write(
    tmp_path: Path,
    entries: list[dict[str, Any]],
    *,
    schema_version: Any = 1,
    oracle_fix_pr: Any = 1153,
    coverage_bound: Any = "SKELETON — explicit, not a silent cap.",
) -> Path:
    payload: dict[str, Any] = {
        "schema_version": schema_version,
        "oracle_fix_pr": oracle_fix_pr,
        "coverage_bound": coverage_bound,
        "entries": entries,
    }
    p = tmp_path / "REVALIDATION_LEDGER.yaml"
    p.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return p


def _run(gate: Any, path: Path) -> int:
    out: int = gate.main(["--registry", str(path)])
    return out


def test_live_registry_passes(gate: Any) -> None:
    assert _run(gate, REGISTRY_PATH) == 0


def test_live_registry_has_seven_pending_lanes(live: dict[str, Any]) -> None:
    statuses = [e["replay_status"] for e in live["entries"]]
    assert len(statuses) == 7
    assert all(s == "PENDING" for s in statuses)


def test_missing_registry_returns_2(gate: Any, tmp_path: Path) -> None:
    assert _run(gate, tmp_path / "absent.yaml") == 2


def test_malformed_yaml_returns_2(gate: Any, tmp_path: Path) -> None:
    p = tmp_path / "REVALIDATION_LEDGER.yaml"
    p.write_text("entries: [unterminated", encoding="utf-8")
    assert _run(gate, p) == 2


def test_bad_schema_version_returns_2(gate: Any, live: dict[str, Any], tmp_path: Path) -> None:
    assert _run(gate, _write(tmp_path, [_entry(live)], schema_version=2)) == 2


def test_empty_entries_returns_2(gate: Any, tmp_path: Path) -> None:
    assert _run(gate, _write(tmp_path, [])) == 2


def test_non_int_oracle_fix_pr_returns_2(gate: Any, live: dict[str, Any], tmp_path: Path) -> None:
    assert _run(gate, _write(tmp_path, [_entry(live)], oracle_fix_pr="soon")) == 2


def test_empty_coverage_bound_returns_2(gate: Any, live: dict[str, Any], tmp_path: Path) -> None:
    assert _run(gate, _write(tmp_path, [_entry(live)], coverage_bound="  ")) == 2


def test_bad_sha_fails(gate: Any, live: dict[str, Any], tmp_path: Path) -> None:
    e = _entry(live)
    e["merge_sha"] = "deadbeef"
    assert _run(gate, _write(tmp_path, [e])) == 1


def test_bad_lane_class_fails(gate: Any, live: dict[str, Any], tmp_path: Path) -> None:
    e = _entry(live)
    e["lane_class"] = "marketing"
    assert _run(gate, _write(tmp_path, [e])) == 1


def test_duplicate_pr_fails(gate: Any, live: dict[str, Any], tmp_path: Path) -> None:
    a = _entry(live)
    b = dict(live["entries"][1])
    b["pr"] = a["pr"]
    assert _run(gate, _write(tmp_path, [a, b])) == 1


def test_duplicate_id_fails(gate: Any, live: dict[str, Any], tmp_path: Path) -> None:
    a = _entry(live)
    b = dict(live["entries"][1])
    b["id"] = a["id"]
    assert _run(gate, _write(tmp_path, [a, b])) == 1


def test_vacuous_flag_flipped_false_fails(gate: Any, live: dict[str, Any], tmp_path: Path) -> None:
    e = _entry(live)
    e["merged_under_vacuous_oracle"] = False
    assert _run(gate, _write(tmp_path, [e])) == 1


def test_promotion_language_in_note_fails(
    gate: Any, live: dict[str, Any], tmp_path: Path
) -> None:
    e = _entry(live)
    e["note"] = "The lane was validated and the gate passed under the oracle."
    assert _run(gate, _write(tmp_path, [e])) == 1


def test_replayed_without_oracle_sha_fails(
    gate: Any, live: dict[str, Any], tmp_path: Path
) -> None:
    e = _entry(live)
    e["replay_status"] = "REPLAYED"
    e["replay_evidence"] = "governance/REVALIDATION_LEDGER.yaml"
    # no oracle_terminal_sha
    assert _run(gate, _write(tmp_path, [e])) == 1


def test_replayed_without_existing_evidence_fails(
    gate: Any, live: dict[str, Any], tmp_path: Path
) -> None:
    e = _entry(live)
    e["replay_status"] = "REPLAYED"
    e["oracle_terminal_sha"] = "a" * 40
    e["replay_evidence"] = "artifacts/does_not_exist_replay.json"
    assert _run(gate, _write(tmp_path, [e])) == 1


def test_bounded_without_bound_fails(gate: Any, live: dict[str, Any], tmp_path: Path) -> None:
    e = _entry(live)
    e["replay_status"] = "BOUNDED"
    assert _run(gate, _write(tmp_path, [e])) == 1


def test_valid_replayed_passes(
    gate: Any, live: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Point the gate's ROOT at tmp_path so an evidence artifact created here is
    # resolved relative to the same root the gate uses for existence checks.
    g = gate
    monkeypatch.setattr(g, "ROOT", tmp_path)
    evidence_rel = "artifacts/replay/oracle_1153_replay.json"
    evidence_abs = tmp_path / evidence_rel
    evidence_abs.parent.mkdir(parents=True, exist_ok=True)
    evidence_abs.write_text('{"oracle": "live", "tests_run": 17600}\n', encoding="utf-8")

    e = _entry(live)
    e["replay_status"] = "REPLAYED"
    e["oracle_terminal_sha"] = "b" * 40
    e["replay_evidence"] = evidence_rel
    assert _run(gate, _write(tmp_path, [e])) == 0
