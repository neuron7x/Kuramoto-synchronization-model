# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Cimini-Squartini fitness reconstruction + instrument-validated
Kuramoto precursor test on the inferred network.

PR X-10R contract:
  Reconstruction is INFERENCE, not observation. Treating the inferred
  weighted adjacency as data is a category error. Any verdict from
  Kuramoto-on-reconstruction binds to the reconstruction class, not to
  the real bank-level network. The mandatory claim qualifier
  "via_max_entropy_reconstruction" must accompany any forward signal.
"""

from __future__ import annotations

from research.reconstruction.cimini_squartini import (
    HiddenFitness,
    fit_cimini_squartini,
    p_link,
)
from research.reconstruction.data_contract import (
    DataContractError,
    InputWindowContract,
    validate_input_window,
)
from research.reconstruction.density_calibration import (
    DENSITY_LOWER,
    DENSITY_UPPER,
    calibrate_density_z,
    density_bound_passes,
    inferred_density,
)
from research.reconstruction.kuramoto_on_reconstruction import (
    MIN_PRECURSOR_GAP,
    KuramotoRecoveryCertificate,
    PrecursorDirection,
    PrecursorReport,
    gate_6_precursor_discriminative,
    issue_kuramoto_recovery_certificate,
)
from research.reconstruction.negative_control import (
    NegativeControlCertificate,
    NegFalsePositiveError,
    neg_2d_grid,
    neg_path_lattice,
    neg_ring_lattice,
    run_all_negative_controls,
    run_negative_control,
)
from research.reconstruction.positive_control import (
    GroundTruthRecoveryCertificate,
    ReciprocityAwareRecoveryCertificate,
    compute_reciprocity_ratio,
    ground_truth_ba,
    ground_truth_core_periphery,
    ground_truth_hierarchical,
    reciprocity_keep_p_for_target,
    run_reciprocity_aware_recovery,
    run_recovery_on_substrate,
)
from research.reconstruction.prereg import (
    build_aspredicted_prereg,
    build_osf_secondary_data_prereg,
    emit_prereg,
)
from research.reconstruction.reconstruction_capsule import (
    ReconstructionCapsule,
    ReconstructionStatus,
    assert_real_data_status_legal,
    assert_synthetic_status_legal,
    build_reconstruction_capsule,
    hash_marginals,
    rerun_reconstruction_strict,
    serialise_reconstruction_capsule,
)
from research.reconstruction.recovery_audit import (
    RECOVERY_THRESHOLDS,
    DomainCheck,
    DomainOfValidityStatus,
    RecoveryReport,
    audit_recovery,
    check_domain_of_validity,
    conservation_of_mass_passes,
)
from research.reconstruction.ro_crate import (
    build_ro_crate_metadata,
    emit_ro_crate,
)
from research.reconstruction.weighted_allocation import (
    allocate_weights,
    sample_adjacency_bernoulli,
)

__all__ = [
    "DENSITY_LOWER",
    "DENSITY_UPPER",
    "DataContractError",
    "DomainCheck",
    "DomainOfValidityStatus",
    "GroundTruthRecoveryCertificate",
    "HiddenFitness",
    "InputWindowContract",
    "KuramotoRecoveryCertificate",
    "MIN_PRECURSOR_GAP",
    "NegFalsePositiveError",
    "NegativeControlCertificate",
    "PrecursorDirection",
    "PrecursorReport",
    "RECOVERY_THRESHOLDS",
    "ReciprocityAwareRecoveryCertificate",
    "ReconstructionCapsule",
    "ReconstructionStatus",
    "RecoveryReport",
    "allocate_weights",
    "assert_real_data_status_legal",
    "assert_synthetic_status_legal",
    "audit_recovery",
    "build_aspredicted_prereg",
    "build_osf_secondary_data_prereg",
    "build_reconstruction_capsule",
    "build_ro_crate_metadata",
    "calibrate_density_z",
    "check_domain_of_validity",
    "compute_reciprocity_ratio",
    "conservation_of_mass_passes",
    "density_bound_passes",
    "emit_prereg",
    "emit_ro_crate",
    "fit_cimini_squartini",
    "gate_6_precursor_discriminative",
    "ground_truth_ba",
    "ground_truth_core_periphery",
    "ground_truth_hierarchical",
    "hash_marginals",
    "inferred_density",
    "issue_kuramoto_recovery_certificate",
    "neg_2d_grid",
    "neg_path_lattice",
    "neg_ring_lattice",
    "p_link",
    "reciprocity_keep_p_for_target",
    "rerun_reconstruction_strict",
    "run_all_negative_controls",
    "run_negative_control",
    "run_reciprocity_aware_recovery",
    "run_recovery_on_substrate",
    "sample_adjacency_bernoulli",
    "serialise_reconstruction_capsule",
    "validate_input_window",
]
