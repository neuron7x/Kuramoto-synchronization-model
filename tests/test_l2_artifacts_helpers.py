"""Tests for the shared L2 artifact-loading helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.l2_artifacts import (
    load_json,
    load_json_or_skip,
    load_results_artifact,
)


def test_load_json_reads_round_trip(tmp_path: Path) -> None:
    payload = {"a": 1, "b": "two", "c": [1, 2, 3]}
    p = tmp_path / "probe.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    assert load_json(p) == payload


def test_load_json_raises_on_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_json(tmp_path / "missing.json")


def test_load_json_or_skip_returns_dict_when_present(tmp_path: Path) -> None:
    p = tmp_path / "ok.json"
    p.write_text(json.dumps({"x": 42}), encoding="utf-8")
    assert load_json_or_skip(p) == {"x": 42}


def test_load_json_or_skip_skips_when_absent(tmp_path: Path) -> None:
    with pytest.raises(pytest.skip.Exception):
        load_json_or_skip(tmp_path / "missing.json", reason="probe reason")


def test_load_results_artifact_reads_real_file_when_present() -> None:
    """Smoke-check against a known committed artifact."""
    path = Path("results/L2_HEADLINE_METRICS.json")
    if not path.exists():
        pytest.skip("headline metrics not present")
    data = load_results_artifact("L2_HEADLINE_METRICS.json")
    assert "ic_pooled" in data


def test_load_results_artifact_skips_on_missing_name() -> None:
    with pytest.raises(pytest.skip.Exception):
        load_results_artifact("L2_DOES_NOT_EXIST.json")
