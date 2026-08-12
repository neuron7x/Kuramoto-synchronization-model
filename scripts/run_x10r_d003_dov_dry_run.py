# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-003 — real BIS DoV-only dry run.

Runs ONLY the domain-of-validity gate on real-shape interbank
marginals. Does NOT call `gate_6_precursor_discriminative` or any
Gate 6 surface. Does NOT emit a bank-level inference claim. Does
NOT lift `INV-IDENTIFICATION-1`.

Allowed outputs (scoped tiers):

    WITHIN_VALIDATED_DOMAIN
    OUT_OF_VALIDATED_DOMAIN
    INSUFFICIENT_CERTIFICATE

Forbidden outputs:

    Gate 6 real-data PASS
    bank-level inference claim
    precursor detected
    liquidity contagion claim
    validated bank-level result

Input contract:

    --marginals path/to/file.json
        JSON of the form:
        {
            "label": "<source label>",
            "s_out": [...],
            "s_in": [...],
            "notes": "<reporter universe / period / aggregation>"
        }

    --certificate path/to/cert.json (optional)
        JSON serialisation of a GroundTruthRecoveryCertificate
        evidence_envelope. Defaults to the canonical D-001 / D-002A
        envelope built into this script.

By default the dry-run uses a REPRESENTATIVE synthetic BIS-LBS-like
marginal set (N=25 reporter universe, lognormal-heavy-tailed,
mass-balanced) so the gate path is exercised end-to-end without
requiring the BIS bulk-flat CSV. Real BIS bulk ingest stays
parameterised: when the user supplies `--marginals` from
`tools/build_bis_lbs_dataset.py` output, the same gate runs on
the real inputs.

Bibliographic anchors justify model class and reviewer traceability;
operational validity is determined only by gates, positive/negative
controls, null distributions, capsules, and power/FPR/MDE evidence.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import numpy as np

from research.reconstruction.positive_control import (
    GroundTruthRecoveryCertificate,
)
from research.reconstruction.prereg import emit_prereg
from research.reconstruction.recovery_audit import (
    DomainOfValidityStatus,
    check_domain_of_validity,
)
from research.reconstruction.ro_crate import emit_ro_crate


def _representative_synthetic_marginals(seed: int = 42) -> dict[str, Any]:
    """Build BIS-LBS-shaped synthetic marginals for the dry-run path.

    The reporter universe is approximated by N=25 nodes with
    lognormal-heavy-tailed strengths (sigma=1.5), mass-balanced
    so Σs_out = Σs_in. The result is *not* real BIS; it is a
    representative substrate that exercises the DoV gate on a
    real-shaped input. The dry-run will be re-run on actual BIS
    output once the user supplies `--marginals` pointing at the
    `tools/build_bis_lbs_dataset.py` artifact.
    """
    rng = np.random.default_rng(seed)
    n = 25
    s_out = rng.lognormal(mean=10.0, sigma=1.5, size=n)
    s_in = rng.lognormal(mean=10.0, sigma=1.5, size=n)
    s_in = s_in * (s_out.sum() / s_in.sum())
    return {
        "label": "REPRESENTATIVE_SYNTHETIC_BIS_LBS_SHAPE",
        "s_out": s_out.tolist(),
        "s_in": s_in.tolist(),
        "notes": (
            "Representative lognormal-heavy-tailed marginals at "
            "N=25 reporters. NOT real BIS bulk data. Used to "
            "exercise the DoV gate path end-to-end. Replace with "
            "tools/build_bis_lbs_dataset.py output for real run."
        ),
        "n_nodes": n,
        "seed": int(seed),
    }


def _canonical_envelope_certificate() -> GroundTruthRecoveryCertificate:
    """Construct the canonical D-001 / D-002A evidence envelope.

    These are the dimensions on which the synthetic recovery
    surface has demonstrated recovery (per D-001
    operational-regime sweep + D-002A pilot infrastructure):
      * n_nodes ∈ {50, 80, 120} (D-002A pilot grid; per D-001
        also tested at N=80)
      * tested_at_densities ∈ {0.03, 0.05, 0.08, 0.12} (D-001)

    The DoV gate uses only `evidence_envelope()` (which reads
    `tested_at_*` fields); we supply minimal-yet-valid values
    for the dataclass's required fields so the certificate is
    schema-valid without claiming any per-density recovery
    report from this dry-run path.
    """
    return GroundTruthRecoveryCertificate(
        substrate_name="canonical_D001_D002A_envelope",
        n_nodes=80,
        target_density=0.05,
        sweep_densities=(0.03, 0.05, 0.08, 0.12),
        per_density_reports={},
        passed=True,
        failure_reasons=(),
        cert_id="D003-DOV-ENVELOPE-CANONICAL-v1",
        tested_at_n_nodes=(50, 80, 120),
        tested_at_densities=(0.03, 0.05, 0.08, 0.12),
    )


def _infer_density_from_marginals(s_out: np.ndarray, s_in: np.ndarray) -> float:
    """Crude density inference for the dry-run.

    Real BIS data ingest carries an explicit density from
    `tools/build_bis_lbs_dataset.py`. In the absence of that,
    we conservatively estimate density as the fraction of
    non-zero entries in a Cimini-calibrated p_ij grid at the
    same marginals — but for a dry-run we use the simpler
    proxy `min(1.0, mean_strength / max_strength)` which
    captures heterogeneity / concentration without requiring
    a full Cimini fit. The dry-run is by design DoV-only;
    the density observable is for envelope-comparison, not
    for reconstruction.
    """
    arr_out = np.asarray(s_out, dtype=np.float64)
    arr_in = np.asarray(s_in, dtype=np.float64)
    mean_s = float((arr_out.mean() + arr_in.mean()) / 2.0)
    max_s = float(max(arr_out.max(), arr_in.max()))
    if max_s <= 0.0:
        return 0.0
    return float(min(1.0, mean_s / max_s))


def run_dry_run(
    *,
    marginals_path: Path | None = None,
    certificate_path: Path | None = None,
    out_path: Path,
) -> dict[str, Any]:
    """Execute the D-003 DoV-only dry-run and emit a JSON capsule.

    Emits ONE of the three scoped tiers. NEVER calls Gate 6,
    NEVER touches `gate_6_precursor_discriminative`. The capsule
    contains the DomainCheck verdict plus provenance for the
    inputs and the certified envelope used.
    """
    if marginals_path is not None:
        payload = json.loads(marginals_path.read_text())
    else:
        payload = _representative_synthetic_marginals()

    s_out = np.asarray(payload["s_out"], dtype=np.float64)
    s_in = np.asarray(payload["s_in"], dtype=np.float64)

    if certificate_path is not None:
        cert_data = json.loads(certificate_path.read_text())
        certificate = GroundTruthRecoveryCertificate(
            substrate_name=str(cert_data.get("substrate_name", "user_supplied")),
            n_nodes=int(cert_data.get("n_nodes", 0)),
            target_density=float(cert_data.get("target_density", 0.0)),
            sweep_densities=tuple(float(x) for x in cert_data.get("sweep_densities", ())),
            per_density_reports={},
            passed=bool(cert_data.get("passed", True)),
            failure_reasons=tuple(cert_data.get("failure_reasons", ())),
            cert_id=str(cert_data.get("cert_id", "user-supplied-no-id")),
            tested_at_n_nodes=tuple(int(x) for x in cert_data.get("tested_at_n_nodes", ())),
            tested_at_densities=tuple(float(x) for x in cert_data.get("tested_at_densities", ())),
        )
    else:
        certificate = _canonical_envelope_certificate()

    # Density may be supplied by the marginals payload (this is the
    # path real BIS dataset_dir output should follow); otherwise we
    # fall back to the crude proxy below.
    if "inferred_density" in payload:
        inferred_density = float(payload["inferred_density"])
    else:
        inferred_density = _infer_density_from_marginals(s_out, s_in)

    t0 = time.time()
    check = check_domain_of_validity(
        s_out,
        s_in,
        certificate,
        inferred_density=inferred_density,
        require_dims=("n_nodes", "density"),
    )
    elapsed = time.time() - t0

    status_str = check.status.value
    allowed = {
        DomainOfValidityStatus.WITHIN_VALIDATED_DOMAIN.value,
        DomainOfValidityStatus.OUT_OF_VALIDATED_DOMAIN.value,
        DomainOfValidityStatus.INSUFFICIENT_CERTIFICATE.value,
    }
    if status_str not in allowed:
        # Hard fail-closed: the gate may emit ONLY the three
        # scoped tiers. Anything else is a contract breach.
        raise RuntimeError(
            f"D-003 contract breach: DoV gate emitted '{status_str}' "
            f"not in allowed scoped tiers {sorted(allowed)}"
        )

    capsule: dict[str, Any] = {
        "d003_dry_run_capsule_version": 1,
        "input_label": payload.get("label", "unspecified"),
        "input_notes": payload.get("notes", ""),
        "n_nodes_input": int(s_out.size),
        "inferred_density": inferred_density,
        "certified_envelope_source": "canonical_D001_D002A",
        "tested_at_n_nodes": list(certificate.tested_at_n_nodes),
        "tested_at_densities": list(certificate.tested_at_densities),
        "domain_check": check.as_dict(),
        "scoped_tier": status_str,
        "elapsed_seconds": elapsed,
        "forbidden_outputs_emitted": False,
        "gate_6_invoked": False,
        "bank_level_claim_emitted": False,
        "inv_identification_1_status": "globally_active",
        "claim_state": (
            "REAL_DOV_READY" if status_str == "within_validated_domain" else "REAL_DOV_REJECTED"
        ),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(capsule, indent=2))

    # Publication-readiness packaging (epic #640): emit machine-readable
    # provenance + preregistration templates alongside the capsule. These
    # are descriptive only and make no validity claim beyond `scoped_tier`.
    artifact_dir = out_path.parent
    crate_path = emit_ro_crate(capsule, artifact_dir)
    prereg_paths = emit_prereg(capsule, artifact_dir)
    capsule["ro_crate_metadata_path"] = str(crate_path)
    capsule["osf_prereg_path"] = str(prereg_paths["osf"])
    capsule["aspredicted_prereg_path"] = str(prereg_paths["aspredicted"])

    return capsule


def main() -> int:
    parser = argparse.ArgumentParser(description="D-003 DoV-only dry run")
    parser.add_argument("--marginals", type=Path, default=None)
    parser.add_argument("--certificate", type=Path, default=None)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("tmp/x10r_d003_dov_dry_run_capsule.json"),
    )
    args = parser.parse_args()

    capsule = run_dry_run(
        marginals_path=args.marginals,
        certificate_path=args.certificate,
        out_path=args.out,
    )

    print(
        f"D-003 DoV-only dry-run complete\n"
        f"  input        : {capsule['input_label']}\n"
        f"  n_nodes      : {capsule['n_nodes_input']}\n"
        f"  density      : {capsule['inferred_density']:.4f}\n"
        f"  scoped_tier  : {capsule['scoped_tier']}\n"
        f"  claim_state  : {capsule['claim_state']}\n"
        f"  notes        : {capsule['domain_check']['notes']}\n"
        f"  capsule      : {args.out}\n"
        f"  INV-IDENTIFICATION-1: {capsule['inv_identification_1_status']}\n"
        f"  Gate 6 invoked: {capsule['gate_6_invoked']}\n"
        f"  bank-level claim: {capsule['bank_level_claim_emitted']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
