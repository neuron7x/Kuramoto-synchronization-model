"""Tests for the full-cycle runner helpers (SHA-256 hashing, stage config).

The main() entrypoint shells out to every CLI in turn, so it is covered
end-to-end by integration runs producing results/L2_FULL_CYCLE_MANIFEST.json.
These tests verify the lightweight pieces in isolation.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/run_l2_full_cycle.py")


def _load_runner_module() -> ModuleType:
    mod_name = "l2_full_cycle_runner"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {_SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    mod = _load_runner_module()
    payload = b"the replay hash must be bit-exact\n" * 128
    p = tmp_path / "probe.bin"
    p.write_bytes(payload)
    expected = hashlib.sha256(payload).hexdigest()
    got = mod._sha256_file(p)
    assert got == expected


def test_stages_unique_names_and_artifacts() -> None:
    mod = _load_runner_module()
    stages = mod.STAGES
    names = [s.name for s in stages]
    artifacts = [s.artifact for s in stages]
    assert len(names) == len(set(names)), "stage names must be unique"
    assert len(artifacts) == len(set(artifacts)), "artifact paths must be unique"
    assert all(a.startswith("results/L2_") for a in artifacts)


def test_stages_cover_expected_axes() -> None:
    mod = _load_runner_module()
    stages = mod.STAGES
    names = {s.name for s in stages}
    expected = {
        "killtest",
        "attribution",
        "purged_cv",
        "spectral",
        "hurst",
        "regime_markov",
        "robustness",
        "transfer_entropy",
        "conditional_te",
    }
    assert names == expected


def test_required_inputs_reference_committed_artifacts() -> None:
    mod = _load_runner_module()
    required = mod.REQUIRED_INPUTS
    for path in required:
        assert path.startswith("results/")


@pytest.mark.parametrize(
    "script_rel",
    [s.cli for s in _load_runner_module().STAGES],
)
def test_each_stage_cli_script_exists(script_rel: str) -> None:
    assert Path(script_rel).exists(), f"stage CLI missing: {script_rel}"
