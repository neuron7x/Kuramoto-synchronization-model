# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Negative-evidence registry gate — self-falsification proof.

``scripts/ci/check_negative_evidence.py`` must PASS on the shipped
``governance/NEGATIVE_EVIDENCE.yaml`` and FAIL CLOSED when a negative result
is lost (artifact deleted), rewritten (sha dropped), mis-categorised, or
laundered into a "partial success" (non-negative verdict / promotion
language). The shipped registry covers all four categories.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "ci" / "check_negative_evidence.py"
REGISTRY_PATH = ROOT / "governance" / "NEGATIVE_EVIDENCE.yaml"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("check_negative_evidence", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_negative_evidence"] = module
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


def _write(tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
    p = tmp_path / "NEGATIVE_EVIDENCE.yaml"
    p.write_text(yaml.safe_dump({"schema_version": 1, "entries": entries}, sort_keys=False), encoding="utf-8")
    return p


def _run(gate: Any, path: Path) -> int:
    return gate.main(["--registry", str(path)])


def test_live_registry_passes(gate: Any) -> None:
    assert _run(gate, REGISTRY_PATH) == 0


def test_live_registry_covers_all_four_categories(live: dict[str, Any]) -> None:
    cats = {e["category"] for e in live["entries"]}
    assert cats == {"failed_null_comparison", "invalid_input", "calibration_miss", "replay_mismatch"}


def test_lost_artifact_fails(gate: Any, live: dict[str, Any], tmp_path: Path) -> None:
    e = _entry(live)
    e["artifact"] = "research/gone/RESULTS.md"
    assert _run(gate, _write(tmp_path, [e])) == 1


def test_dropped_sha_fails(gate: Any, live: dict[str, Any], tmp_path: Path) -> None:
    e = _entry(live)
    e["sha"] = "deadbeef"
    assert _run(gate, _write(tmp_path, [e])) == 1


def test_bad_category_fails(gate: Any, live: dict[str, Any], tmp_path: Path) -> None:
    e = _entry(live)
    e["category"] = "great_success"
    assert _run(gate, _write(tmp_path, [e])) == 1


def test_non_negative_verdict_fails(gate: Any, live: dict[str, Any], tmp_path: Path) -> None:
    e = _entry(live)
    e["verdict"] = "VALIDATED"
    assert _run(gate, _write(tmp_path, [e])) == 1


def test_promotion_language_fails(gate: Any, live: dict[str, Any], tmp_path: Path) -> None:
    # laundering a negative into a "partial success" must be rejected
    e = _entry(live)
    e["description"] = "A partial success: the null was partially validated."
    assert _run(gate, _write(tmp_path, [e])) == 1


def test_missing_registry_returns_2(gate: Any, tmp_path: Path) -> None:
    assert _run(gate, tmp_path / "absent.yaml") == 2


def test_empty_entries_returns_2(gate: Any, tmp_path: Path) -> None:
    assert _run(gate, _write(tmp_path, [])) == 2
