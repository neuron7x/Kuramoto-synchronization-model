from __future__ import annotations

import importlib
import json
from pathlib import Path

import scripts.validate_metrics as vm


def _reload_with_artifacts(tmp_path: Path) -> None:
    import os

    os.environ["METRICS_VALIDATION_ARTIFACT_DIR"] = str(tmp_path / "artifacts")
    importlib.reload(vm)


def _write_runtime_snapshots(baseline: str, final: str) -> None:
    runtime_artifact = Path(vm.ARTIFACT_DIR) / "runtime.json"
    runtime_artifact.parent.mkdir(parents=True, exist_ok=True)
    runtime_artifact.write_text(
        json.dumps({"snapshots": {"baseline": baseline, "final": final}}),
        encoding="utf-8",
    )


def _prepare_expectations(
    tmp_path: Path, expectations: dict[str, dict[str, object]], *, baseline: str, final: str
) -> Path:
    _reload_with_artifacts(tmp_path)
    root = tmp_path / "repo"
    expectations_path = root / "observability" / "metrics_expectations.json"
    expectations_path.parent.mkdir(parents=True, exist_ok=True)
    expectations_path.write_text(json.dumps(expectations), encoding="utf-8")
    _write_runtime_snapshots(baseline, final)
    return root


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


def test_expectations_enforce_bounds(tmp_path: Path) -> None:
    root = _prepare_expectations(
        tmp_path,
        {
            "tradepulse_process_cpu_percent": {
                "type": "gauge",
                "finite": True,
                "min": 0.0,
                "max": 100.0,
            }
        },
        baseline="tradepulse_process_cpu_percent 10",
        final="tradepulse_process_cpu_percent 120",
    )

    status = vm.run_expectations(root, [])

    artifact = Path(vm.ARTIFACT_DIR) / "expectations.json"
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert status == 1
    assert any(
        issue["code"] == "above_max"
        and issue["metric"] == "tradepulse_process_cpu_percent"
        for issue in payload["issues"]
    )


def test_expectations_enforce_latency_non_negative(tmp_path: Path) -> None:
    root = _prepare_expectations(
        tmp_path,
        {
            "tradepulse_api_request_latency_seconds": {
                "type": "histogram",
                "finite": True,
                "min": 0.0,
            }
        },
        baseline="tradepulse_api_request_latency_seconds 0.5",
        final="tradepulse_api_request_latency_seconds -0.25",
    )

    status = vm.run_expectations(root, [])

    payload = json.loads((Path(vm.ARTIFACT_DIR) / "expectations.json").read_text())
    assert status == 1
    assert any(
        issue["code"] == "below_min"
        and issue["metric"] == "tradepulse_api_request_latency_seconds"
        for issue in payload["issues"]
    )


def test_expectations_enforce_monotonic_counter(tmp_path: Path) -> None:
    root = _prepare_expectations(
        tmp_path,
        {
            "tradepulse_api_requests_total": {
                "type": "counter",
                "monotonic": True,
                "finite": True,
                "min": 0.0,
            }
        },
        baseline="tradepulse_api_requests_total 5",
        final="tradepulse_api_requests_total 3",
    )

    status = vm.run_expectations(root, [])

    payload = json.loads((Path(vm.ARTIFACT_DIR) / "expectations.json").read_text())
    assert status == 1
    assert any(
        issue["code"] == "monotonicity"
        and issue["metric"] == "tradepulse_api_requests_total"
        for issue in payload["issues"]
    )
