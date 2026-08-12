# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pathlib

import pytest
import yaml

REQUIRED_RESOURCE_KEYS = {"cpu", "memory", "timeout"}


@pytest.fixture(scope="module")
def heavy_job_config() -> dict[str, object]:
    path = pathlib.Path("configs/quality/heavy_math_jobs.yaml")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_heavy_jobs_defined_for_all_indicators(
    heavy_job_config: dict[str, object],
) -> None:
    jobs = heavy_job_config.get("jobs", {})
    expected = {
        "kuramoto_validation",
        "ricci_curvature_validation",
        "hurst_long_memory_validation",
    }
    assert expected.issubset(jobs.keys()), "Missing heavy-math job definitions"


@pytest.mark.parametrize(
    "job_name",
    [
        "kuramoto_validation",
        "ricci_curvature_validation",
        "hurst_long_memory_validation",
    ],
)
def test_heavy_jobs_include_resource_quotas(
    job_name: str, heavy_job_config: dict[str, object]
) -> None:
    job = heavy_job_config["jobs"][job_name]
    resources = job.get("resources", {})
    missing = REQUIRED_RESOURCE_KEYS - resources.keys()
    assert not missing, f"Job {job_name} missing resource keys: {sorted(missing)}"

    if job_name == "kuramoto_validation":
        assert "gpu" in resources, "Kuramoto validation must declare GPU option"

    assert job.get("blocking") is True
    assert "heavy_math" in job.get("markers", [])


def test_heavy_jobs_artifacts_are_declared(heavy_job_config: dict[str, object]) -> None:
    for job_name, payload in heavy_job_config["jobs"].items():
        artifacts = payload.get("artifacts", [])
        assert artifacts, f"Job {job_name} must declare artefacts for auditability"
        for artifact in artifacts:
            assert artifact.startswith("reports/heavy_math/"), artifact
