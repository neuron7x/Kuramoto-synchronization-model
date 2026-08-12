from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from runtime.riee.engine import PrefrontalCortexEngine


def test_riee_emits_telemetry_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pfc = PrefrontalCortexEngine(gamma_claim=1.0)
    status = pfc.enforce(1.0)
    assert status.state_validity

    log = Path("artifacts/quarantine/riee_events.jsonl")
    assert log.exists()
    payload: dict[str, Any] = json.loads(log.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert "timestamp_utc" in payload
    assert payload["status"]["reason"] in {"ok", "epistemic drift detected"}
