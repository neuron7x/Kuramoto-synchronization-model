#!/usr/bin/env bash
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
#
# phd-evidence reproducibility package (one command).
#
# Aggregates the fail-closed evidence gates and regenerates the machine-readable
# evidence artifacts. Exits non-zero if ANY gate fails. This is the single
# `make phd-evidence` entry point referenced by docs/phd/.
#
# NON-CLAIMS: wheel contract runs WITHOUT --strict on purpose — B.wheel=0
# (canonical packaging) is NOT achieved and is NOT claimed. No market/alpha
# outcome is produced. Witnesses are synthetic-only.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
PYTHON="${PYTHON:-python}"

rc_total=0
declare -a RESULTS=()

run() {
  local label="$1"; shift
  if "$@" >/tmp/phd_evidence_step.log 2>&1; then
    RESULTS+=("PASS  $label")
  else
    RESULTS+=("FAIL  $label (rc=$?)")
    rc_total=1
    echo "---- $label FAILED ----" >&2
    tail -n 25 /tmp/phd_evidence_step.log >&2
  fi
}

echo "🎓 phd-evidence: aggregating fail-closed evidence gates ..."

# 1. Wheel / artifact contract (non-strict: honest current state).
run "wheel_contract"            "$PYTHON" scripts/ci/check_wheel_contract.py
# 2. PhD traceability (every claim file bound; no forbidden over-claims).
run "phd_traceability"          "$PYTHON" scripts/ci/check_phd_traceability.py
# 3. Physics inference readiness (tier-labelled inference discipline).
run "physics_inference"         "$PYTHON" scripts/ci/check_physics_inference_readiness.py
# 4. Neuro claim boundary (no biological-equivalence overclaim in runtime).
run "neuro_claim_boundary"      "$PYTHON" scripts/ci/check_neuro_claim_boundary.py
# 5. Neuro ledger audit (OPERATIONAL needs INV-* binding; PARTIAL needs remediation).
run "neuro_symbolic_audit"      "$PYTHON" tools/audit/neuro_symbolic_audit.py
# 5b. Evidence integrity (teeth: INV/test references must RESOLVE; no fake promotion).
run "evidence_integrity"        "$PYTHON" scripts/ci/check_evidence_integrity.py
# 5c. Artifact freshness (deterministic evidence artifacts == regenerated; no hand-edits).
run "artifact_freshness"        "$PYTHON" scripts/ci/check_artifact_freshness.py
# 6. Regenerate machine-readable evidence artifacts (matrix + traceability + table).
run "witness_matrix"            "$PYTHON" scripts/ci/gen_law_mechanism_witness_matrix.py
run "distinguished_evidence"    "$PYTHON" scripts/ci/gen_distinguished_evidence_table.py
# 7. Reference-standard conformance certificate (the reference-standard gate —
#    derives the seven invariant laws from actual repo state; non-zero on any fail).
run "reference_conformance"     "$PYTHON" scripts/ci/gen_reference_conformance.py

echo ""
echo "──────────── phd-evidence summary ────────────"
for r in "${RESULTS[@]}"; do echo "  $r"; done
echo "───────────────────────────────────────────────"
if [ "$rc_total" -eq 0 ]; then
  echo "✅ phd-evidence: all gates green; artifacts regenerated under artifacts/academy_fellow/."
else
  echo "❌ phd-evidence: at least one gate failed (see logs above)." >&2
fi
exit "$rc_total"
