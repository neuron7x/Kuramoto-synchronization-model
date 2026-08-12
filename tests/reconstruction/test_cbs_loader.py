# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""CBS marginal loader tests (issue #639, X-10R CBS adapter).

Acceptance: load the CBS fixture -> fit_cimini_squartini -> a valid
ReconstructionCapsule builds with a legal synthetic-path
ReconstructionStatus. Fails before the loader exists, passes after.

Falsifier: a CBS dataset that INCLUDES an intragroup position
(reporter_group == counterparty_group) is a CBS ontology-contract
violation (CBS excludes intragroup positions by construction). The
loader MUST reject it, and the CLI MUST exit non-zero. This protects
the CBS ontology claim against silently relabelling LBS-style
intragroup-inclusive data as CBS.

Honesty: nothing here is a predictive / alpha / tradeable / bank-level
claim. Recovery is defined only on synthetic substrates with known
truth; this synthetic fixture exercises the INPUT adapter only.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from research.reconstruction.cimini_squartini import fit_cimini_squartini, p_link
from research.reconstruction.reconstruction_capsule import (
    ReconstructionCapsule,
    ReconstructionStatus,
    assert_real_data_status_legal,
    assert_synthetic_status_legal,
    build_reconstruction_capsule,
    hash_marginals,
)
from tools.build_bis_cbs_dataset import (
    SCHEMA_VERSION,
    CbsContractViolation,
    CbsMarginals,
    load_cbs_marginals,
    main,
    parse_cbs_marginals,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_VALID = _FIXTURES / "cbs_marginals_valid.json"
_INTRAGROUP = _FIXTURES / "cbs_marginals_intragroup_violation.json"


# ---------------------------------------------------------------------------
# Loader basics
# ---------------------------------------------------------------------------


def test_valid_fixture_loads_marginals() -> None:
    marg = load_cbs_marginals(_VALID)
    assert isinstance(marg, CbsMarginals)
    assert marg.intragroup_excluded is True
    assert marg.reporting_period == "2023-Q4"
    # Node labels are the sorted union of all groups, deterministic.
    assert marg.node_labels == ("DE", "FR", "GB", "JP", "US")
    assert marg.n_nodes == 5
    assert marg.s_out.shape == (marg.n_nodes,)
    assert marg.s_in.shape == (marg.n_nodes,)
    assert np.all(marg.s_out >= 0.0)
    assert np.all(marg.s_in >= 0.0)


def test_marginal_mass_matches_total_claims() -> None:
    """Every claim contributes once to an out-marginal and once to an
    in-marginal, so both totals equal the summed claims."""
    marg = load_cbs_marginals(_VALID)
    total = 1850.0 + 920.0 + 740.0 + 1320.0 + 1610.0 + 880.0 + 1190.0 + 530.0 + 670.0 + 410.0 + 950.0 + 360.0
    assert float(marg.s_out.sum()) == pytest.approx(total)
    assert float(marg.s_in.sum()) == pytest.approx(total)


def test_out_and_in_marginals_are_directional() -> None:
    """DE reports 1850+920+740 outward; is reported on by US,GB,FR."""
    marg = load_cbs_marginals(_VALID)
    de = marg.node_labels.index("DE")
    assert float(marg.s_out[de]) == pytest.approx(1850.0 + 920.0 + 740.0)
    assert float(marg.s_in[de]) == pytest.approx(1320.0 + 530.0 + 670.0)


# ---------------------------------------------------------------------------
# Acceptance — CBS marginals feed the SAME engine and build a capsule
# ---------------------------------------------------------------------------


def test_cbs_marginals_feed_engine_and_build_capsule() -> None:
    marg = load_cbs_marginals(_VALID)

    fit = fit_cimini_squartini(marg.s_out, marg.s_in, target_density=0.20)
    # The engine returns a usable fitness object on the CBS marginals.
    assert fit.x.shape == (marg.n_nodes,)
    assert fit.y.shape == (marg.n_nodes,)
    assert np.isfinite(fit.z) and fit.z >= 0.0

    # Link probabilities are a valid Bernoulli field on the disk [0,1].
    p = p_link(fit.x, fit.y, fit.z)
    assert np.all(p >= 0.0) and np.all(p <= 1.0)
    assert float(np.trace(p)) == pytest.approx(0.0)  # no self-loops

    inferred_density = float(p.sum() / (marg.n_nodes * (marg.n_nodes - 1)))

    cap = build_reconstruction_capsule(
        payload_sha256=hash_marginals(marg.s_out, marg.s_in),
        scope_id="x10r/cbs-synthetic/2023-Q4",
        inferred_density=inferred_density,
        spectral_radius=float(np.max(np.abs(np.linalg.eigvals(p)))),
        L1_error_row=1.0e-10,
        L1_error_col=1.0e-10,
        n_nodes=marg.n_nodes,
        z_calibrated=fit.z,
        prng_seed=639,
        ground_truth_recovery_cert_id=hashlib.sha256(b"cbs-synthetic-gt").hexdigest(),
        kuramoto_recovery_cert_id=None,
        # Synthetic substrate -> synthetic-path status is the legal surface.
        reconstruction_status=ReconstructionStatus.GROUND_TRUTH_NOT_RECOVERED,
        code_sha=hashlib.sha256(b"cbs-loader-code").hexdigest(),
        metrics_sha=hashlib.sha256(b"cbs-loader-metrics").hexdigest(),
    )
    assert isinstance(cap, ReconstructionCapsule)
    # The status is on the synthetic-recovery legal surface, never the
    # real-data domain-of-validity surface.
    assert_synthetic_status_legal(cap.reconstruction_status)
    with pytest.raises(ValueError, match="INV-RECONSTRUCTION-2"):
        assert_real_data_status_legal(cap.reconstruction_status)


# ---------------------------------------------------------------------------
# Falsifier — intragroup positions must be REJECTED (CBS ontology)
# ---------------------------------------------------------------------------


def test_intragroup_position_is_rejected() -> None:
    with pytest.raises(CbsContractViolation, match="INTRAGROUP"):
        load_cbs_marginals(_INTRAGROUP)


def test_intragroup_cli_exits_non_zero() -> None:
    """The CLI MUST exit non-zero on an intragroup-including dataset —
    a silent accept would relabel LBS-style data as CBS."""
    rc = main(["--cbs-json", str(_INTRAGROUP)])
    assert rc != 0


def test_valid_cli_exits_zero() -> None:
    assert main(["--cbs-json", str(_VALID)]) == 0


# ---------------------------------------------------------------------------
# Schema / fail-closed contract
# ---------------------------------------------------------------------------


def test_wrong_schema_version_rejected() -> None:
    doc = {
        "schema_version": "bis.lbs.v9",
        "ontology": "nationality_parent_group",
        "intragroup_excluded": True,
        "reporting_period": "2023-Q4",
        "positions": [{"reporter_group": "DE", "counterparty_group": "US", "claim_usd_mn": 1.0}],
    }
    with pytest.raises(CbsContractViolation, match="schema_version"):
        parse_cbs_marginals(doc)


def test_intragroup_excluded_flag_must_be_true() -> None:
    doc = {
        "schema_version": SCHEMA_VERSION,
        "ontology": "nationality_parent_group",
        "intragroup_excluded": False,
        "reporting_period": "2023-Q4",
        "positions": [{"reporter_group": "DE", "counterparty_group": "US", "claim_usd_mn": 1.0}],
    }
    with pytest.raises(CbsContractViolation, match="intragroup_excluded"):
        parse_cbs_marginals(doc)


def test_wrong_ontology_rejected() -> None:
    doc = {
        "schema_version": SCHEMA_VERSION,
        "ontology": "residence_country",
        "intragroup_excluded": True,
        "reporting_period": "2023-Q4",
        "positions": [{"reporter_group": "DE", "counterparty_group": "US", "claim_usd_mn": 1.0}],
    }
    with pytest.raises(CbsContractViolation, match="ontology"):
        parse_cbs_marginals(doc)


def test_negative_claim_rejected() -> None:
    doc = {
        "schema_version": SCHEMA_VERSION,
        "ontology": "nationality_parent_group",
        "intragroup_excluded": True,
        "reporting_period": "2023-Q4",
        "positions": [{"reporter_group": "DE", "counterparty_group": "US", "claim_usd_mn": -5.0}],
    }
    with pytest.raises(CbsContractViolation, match="non-negative"):
        parse_cbs_marginals(doc)


def test_single_group_rejected() -> None:
    """A reconstruction needs >= 2 distinct nodes; but a single group
    can only appear via an intragroup position, which is rejected first.
    Use two rows that collapse to one group after rejecting nothing."""
    doc = {
        "schema_version": SCHEMA_VERSION,
        "ontology": "nationality_parent_group",
        "intragroup_excluded": True,
        "reporting_period": "2023-Q4",
        "positions": [{"reporter_group": "DE", "counterparty_group": "DE", "claim_usd_mn": 1.0}],
    }
    # Intragroup is caught before the node-count check.
    with pytest.raises(CbsContractViolation, match="INTRAGROUP"):
        parse_cbs_marginals(doc)


def test_empty_positions_rejected() -> None:
    doc = {
        "schema_version": SCHEMA_VERSION,
        "ontology": "nationality_parent_group",
        "intragroup_excluded": True,
        "reporting_period": "2023-Q4",
        "positions": [],
    }
    with pytest.raises(CbsContractViolation, match="positions"):
        parse_cbs_marginals(doc)


def test_missing_file_cli_exits_non_zero() -> None:
    assert main(["--cbs-json", "/nonexistent/cbs.json"]) != 0
