from __future__ import annotations

import importlib
import json
from pathlib import Path

import scripts.validate_metrics as vm


def _reload_with_artifacts(tmp_path: Path) -> None:
    import os

    os.environ["METRICS_VALIDATION_ARTIFACT_DIR"] = str(tmp_path / "artifacts")
    importlib.reload(vm)


def test_expectations_enforced(tmp_path: Path) -> None:
    _reload_with_artifacts(tmp_path)
    root = Path(__file__).resolve().parents[2]
    catalogs = [root / "observability" / "metrics.json"]

    runtime_status = vm.run_runtime(root, catalogs)
    assert runtime_status == 0

    status = vm.run_expectations(root, catalogs)
    assert status == 0

    artifact = Path(vm.ARTIFACT_DIR) / "expectations.json"
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["issues"] == []
