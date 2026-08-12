# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import types
from pathlib import Path

import scripts.eval.run_redteam_policy as redteam


def _patch_args(monkeypatch, fixtures: Path, output: Path, strict: bool = False) -> None:
    monkeypatch.setattr(
        redteam.argparse.ArgumentParser,
        "parse_args",
        lambda self: types.SimpleNamespace(
            fixtures=fixtures, output=output, strict=strict, limit=None
        ),
    )


def test_run_generates_report(tmp_path: Path, monkeypatch) -> None:
    fixtures = tmp_path / "cases.yaml"
    fixtures.write_text(
        "test_cases:\n"
        "  - id: case1\n    category: inj\n    input_text: ignore all previous\n"
        "    expected_minimum_decision: BLOCK\n"
    )
    output = tmp_path / "report.json"
    _patch_args(monkeypatch, fixtures, output)

    engine = types.SimpleNamespace(strict_mode=False)

    def _evaluate(text: str, stage: str | None = None):
        decision = redteam.DecisionType.BLOCK if "ignore" in text else redteam.DecisionType.ALLOW
        result = types.SimpleNamespace(decision=decision, reasons=["stub"])
        trace = types.SimpleNamespace(trace_id="t-1")
        return result, trace

    engine.evaluate = _evaluate
    monkeypatch.setattr(redteam, "create_stub_policy_engine", lambda strict_mode=False: engine)

    assert redteam.main() == 0

    payload = json.loads(output.read_text())
    assert payload["summary"]["total_cases"] == 1
    assert payload["summary"]["failed"] == 0
    assert payload["results"][0]["actual_decision"]


def test_invalid_fixture_path(monkeypatch, tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    output = tmp_path / "out.json"
    _patch_args(monkeypatch, missing, output)

    assert redteam.main() == 1
