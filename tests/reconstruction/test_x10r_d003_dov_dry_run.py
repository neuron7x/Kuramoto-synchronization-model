# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-003 — tests for the real BIS DoV-only dry-run driver.

The dry-run driver MUST:

  * emit exactly ONE of the three scoped tiers
    (WITHIN_VALIDATED_DOMAIN / OUT_OF_VALIDATED_DOMAIN /
    INSUFFICIENT_CERTIFICATE);
  * never invoke Gate 6 (`gate_6_precursor_discriminative`);
  * never emit a bank-level inference claim;
  * never lift INV-IDENTIFICATION-1;
  * persist a JSON capsule with input provenance + verdict.

These tests pin the contract. They do not exercise real BIS bulk
ingest (that is a deployment-time concern); they prove the gate
path returns the correct tier for hand-crafted inputs.

Bibliographic anchors justify model class and reviewer traceability;
operational validity is determined only by gates, positive/negative
controls, null distributions, capsules, and power/FPR/MDE evidence.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

_DRIVER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_x10r_d003_dov_dry_run.py"


def _load_driver() -> ModuleType:
    spec = importlib.util.spec_from_file_location("d003_driver", _DRIVER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def driver() -> ModuleType:
    return _load_driver()


# ---------------------------------------------------------------------------
# Scoped-tier verdict tests
# ---------------------------------------------------------------------------


def test_dry_run_emits_one_of_three_scoped_tiers_on_default_input(
    driver: ModuleType, tmp_path: Path
) -> None:
    """Default representative-synthetic inputs produce a verdict that
    is one of WITHIN_VALIDATED_DOMAIN / OUT_OF_VALIDATED_DOMAIN /
    INSUFFICIENT_CERTIFICATE — never anything else."""
    out = tmp_path / "capsule.json"
    capsule = driver.run_dry_run(marginals_path=None, certificate_path=None, out_path=out)
    assert capsule["scoped_tier"] in {
        "within_validated_domain",
        "out_of_validated_domain",
        "insufficient_certificate",
    }
    assert capsule["gate_6_invoked"] is False
    assert capsule["bank_level_claim_emitted"] is False
    assert capsule["inv_identification_1_status"] == "globally_active"


def test_within_domain_when_input_matches_envelope(driver: ModuleType, tmp_path: Path) -> None:
    """Inputs inside the canonical envelope (N=80, density in
    [0.03, 0.12]) must produce WITHIN_VALIDATED_DOMAIN."""
    # Hand-craft 80 reporter universe with mean strength yielding
    # an inferred density inside [0.03, 0.12]. We use a lognormal
    # tail to keep the heterogeneity realistic.
    import numpy as np

    rng = np.random.default_rng(7)
    n = 80
    s_out = rng.lognormal(mean=10.0, sigma=1.0, size=n)
    s_in = rng.lognormal(mean=10.0, sigma=1.0, size=n)
    s_in = s_in * (s_out.sum() / s_in.sum())
    marginals = tmp_path / "marg_within.json"
    marginals.write_text(
        json.dumps(
            {
                "label": "TEST_WITHIN_SYNTHETIC",
                "s_out": s_out.tolist(),
                "s_in": s_in.tolist(),
                "inferred_density": 0.08,
                "notes": "hand-crafted within-envelope test (explicit density mirrors real BIS dataset_dir path)",
            }
        )
    )
    out = tmp_path / "capsule_within.json"
    capsule = driver.run_dry_run(marginals_path=marginals, certificate_path=None, out_path=out)
    assert capsule["scoped_tier"] == "within_validated_domain"
    assert capsule["claim_state"] == "REAL_DOV_READY"


def test_out_of_domain_when_n_nodes_below_envelope(driver: ModuleType, tmp_path: Path) -> None:
    """N=25 (real BIS reporter universe scale) is below the
    canonical envelope min N=50; must produce
    OUT_OF_VALIDATED_DOMAIN."""
    import numpy as np

    rng = np.random.default_rng(11)
    n = 25
    s_out = rng.lognormal(mean=10.0, sigma=1.0, size=n)
    s_in = rng.lognormal(mean=10.0, sigma=1.0, size=n)
    s_in = s_in * (s_out.sum() / s_in.sum())
    marginals = tmp_path / "marg_out.json"
    marginals.write_text(
        json.dumps(
            {
                "label": "TEST_OUT_SMALL_N",
                "s_out": s_out.tolist(),
                "s_in": s_in.tolist(),
                "notes": "real-BIS-reporter-scale (N=25), out of envelope",
            }
        )
    )
    out = tmp_path / "capsule_out.json"
    capsule = driver.run_dry_run(marginals_path=marginals, certificate_path=None, out_path=out)
    assert capsule["scoped_tier"] == "out_of_validated_domain"
    assert capsule["claim_state"] == "REAL_DOV_REJECTED"
    assert "n_nodes" in capsule["domain_check"]["out_of_range_dims"]


def test_insufficient_certificate_when_envelope_empty(driver: ModuleType, tmp_path: Path) -> None:
    """A certificate that is silent on every required dimension
    must produce INSUFFICIENT_CERTIFICATE."""
    import numpy as np

    cert = tmp_path / "empty_cert.json"
    cert.write_text(
        json.dumps(
            {
                "substrate_name": "empty",
                "n_nodes": 0,
                "target_density": 0.0,
                "sweep_densities": [],
                "passed": True,
                "failure_reasons": [],
                "cert_id": "EMPTY",
                "tested_at_n_nodes": [],
                "tested_at_densities": [],
            }
        )
    )
    rng = np.random.default_rng(13)
    s_out = rng.lognormal(mean=10.0, sigma=1.0, size=50).tolist()
    s_in_arr = rng.lognormal(mean=10.0, sigma=1.0, size=50)
    s_in_arr = s_in_arr * (sum(s_out) / float(s_in_arr.sum()))
    marg = tmp_path / "marg_insuf.json"
    marg.write_text(
        json.dumps(
            {
                "label": "TEST_INSUFFICIENT",
                "s_out": s_out,
                "s_in": s_in_arr.tolist(),
                "notes": "insufficient-certificate exercise",
            }
        )
    )
    out = tmp_path / "capsule_insuf.json"
    capsule = driver.run_dry_run(marginals_path=marg, certificate_path=cert, out_path=out)
    assert capsule["scoped_tier"] == "insufficient_certificate"
    assert capsule["claim_state"] == "REAL_DOV_REJECTED"


# ---------------------------------------------------------------------------
# Contract: no Gate 6 invocation, no forbidden tiers, capsule shape
# ---------------------------------------------------------------------------


def test_driver_does_not_import_gate_6_module() -> None:
    """Static guarantee: the dry-run driver does NOT IMPORT any
    Gate 6 surface. Source-level check on the driver file. The
    docstring may *mention* `gate_6_precursor_discriminative` to
    state the contract explicitly; what matters is the absence
    of an import."""
    src = _DRIVER_PATH.read_text(encoding="utf-8")
    assert "from research.reconstruction.kuramoto_on_reconstruction" not in src
    assert "import research.reconstruction.kuramoto_on_reconstruction" not in src
    # Forbid any executable call site by checking against the
    # canonical import + invocation patterns, ignoring docstring
    # / comment mentions.
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"'):
            continue
        assert (
            "gate_6_precursor_discriminative(" not in stripped
        ), f"forbidden call site found: {line!r}"


def test_capsule_records_forbidden_outputs_not_emitted(driver: ModuleType, tmp_path: Path) -> None:
    out = tmp_path / "capsule.json"
    capsule = driver.run_dry_run(marginals_path=None, certificate_path=None, out_path=out)
    assert capsule["forbidden_outputs_emitted"] is False
    assert capsule["gate_6_invoked"] is False
    assert capsule["bank_level_claim_emitted"] is False
    assert capsule["inv_identification_1_status"] == "globally_active"


def test_capsule_written_to_disk_with_correct_keys(driver: ModuleType, tmp_path: Path) -> None:
    out = tmp_path / "subdir" / "capsule.json"
    capsule = driver.run_dry_run(marginals_path=None, certificate_path=None, out_path=out)
    assert out.exists()
    persisted = json.loads(out.read_text())
    required_keys = {
        "d003_dry_run_capsule_version",
        "input_label",
        "n_nodes_input",
        "inferred_density",
        "domain_check",
        "scoped_tier",
        "claim_state",
        "gate_6_invoked",
        "bank_level_claim_emitted",
        "inv_identification_1_status",
    }
    assert required_keys.issubset(persisted.keys())
    assert persisted["scoped_tier"] == capsule["scoped_tier"]


def test_claim_state_mapping_is_disciplined(driver: ModuleType, tmp_path: Path) -> None:
    """The capsule's `claim_state` must be exactly REAL_DOV_READY
    iff scoped_tier is within_validated_domain; otherwise
    REAL_DOV_REJECTED. No third value is allowed."""
    out = tmp_path / "capsule.json"
    capsule = driver.run_dry_run(marginals_path=None, certificate_path=None, out_path=out)
    if capsule["scoped_tier"] == "within_validated_domain":
        assert capsule["claim_state"] == "REAL_DOV_READY"
    else:
        assert capsule["claim_state"] == "REAL_DOV_REJECTED"
