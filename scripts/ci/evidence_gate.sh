#!/usr/bin/env bash
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
#
# evidence_gate.sh — the single canonical release verification command (TASK 936).
#
# Composes every integrity, capsule, schema, claim, and coverage gate into one
# deterministic proof. Each layer writes evidence under reports/evidence_gate/,
# no failure is swallowed, and the final report prints PASS/FAIL per layer. The
# command exits non-zero if ANY layer fails.
#
# Layers 1-11 (core) prove integrity + capsule + claims and run on the sci-core
# stack. Layers 12-13 (coverage) are heavy and need the full test stack; pass
# --skip-coverage to run the core proof only (e.g. on the dependency-light lane).
#
# Usage:
#   bash scripts/ci/evidence_gate.sh                # full 13-layer release proof
#   bash scripts/ci/evidence_gate.sh --skip-coverage  # layers 1-11 only
set -uo pipefail
cd "$(dirname "$0")/../.."
export PYTHONPATH="${PYTHONPATH:-.}:."
PY="${PYTHON:-python3}"

SKIP_COVERAGE=0
for arg in "$@"; do
  case "$arg" in
    --skip-coverage) SKIP_COVERAGE=1 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

EVID_DIR="reports/evidence_gate"
mkdir -p "$EVID_DIR"
SUMMARY="$EVID_DIR/summary.txt"
: >"$SUMMARY"

declare -a NAMES=()
declare -a RESULTS=()
OVERALL=0

run_layer() {
  # run_layer "<name>" <command...>
  local name="$1"; shift
  local slug
  slug="$(echo "$name" | tr ' /' '__' | tr -cd 'A-Za-z0-9_')"
  local log="$EVID_DIR/${slug}.log"
  echo "──▶ ${name}"
  if "$@" >"$log" 2>&1; then
    NAMES+=("$name"); RESULTS+=("PASS")
    echo "PASS  ${name}" >>"$SUMMARY"
  else
    NAMES+=("$name"); RESULTS+=("FAIL")
    OVERALL=1
    echo "FAIL  ${name}" >>"$SUMMARY"
    echo "   ↳ evidence: ${log}"
    tail -n 5 "$log" | sed 's/^/   /'
  fi
}

invariant_witness() { test "$("$PY" scripts/count_invariants.py)" = "112"; }

run_layer "01 invariant witness"            invariant_witness
run_layer "02 python version matrix"        "$PY" scripts/check_python_matrix.py
run_layer "03 namespace policy"             "$PY" scripts/check_namespace_policy.py
run_layer "04 claim boundary"               "$PY" scripts/ci/check_claim_boundary.py
run_layer "05 manifest hash proof"          "$PY" scripts/ci/check_manifest_hashes.py --require-artifacts
run_layer "06 artifact truth gate"          "$PY" scripts/ci/check_research_artifact_truth.py
run_layer "07 claim-to-artifact graph"      "$PY" scripts/ci/check_claim_artifact_graph.py
run_layer "08 capsule schema validation"    "$PY" scripts/ci/check_capsule_schema.py
run_layer "09 capsule reproduction verify"  "$PY" scripts/reproduce/mfn_capsule.py --verify
run_layer "10 capsule secret boundary"      "$PY" tools/security/validate_capsule_secret_boundary.py
run_layer "11 research-line contract tests" "$PY" -m pytest tests/research_lines tests/ci -q -p no:cacheprovider

if [ "$SKIP_COVERAGE" -eq 0 ]; then
  run_layer "12 coverage baseline"          make coverage-baseline
  run_layer "13 release coverage 90 gate"   make coverage-90
else
  echo "SKIP  12 coverage baseline (--skip-coverage)"        >>"$SUMMARY"
  echo "SKIP  13 release coverage 90 gate (--skip-coverage)" >>"$SUMMARY"
fi

echo
echo "════════════ EVIDENCE GATE REPORT ════════════"
for i in "${!NAMES[@]}"; do
  printf '  %-4s %s\n' "${RESULTS[$i]}" "${NAMES[$i]}"
done
[ "$SKIP_COVERAGE" -eq 1 ] && printf '  %-4s %s\n' "SKIP" "12-13 coverage (--skip-coverage)"
echo "═══════════════════════════════════════════════"

if [ "$OVERALL" -eq 0 ]; then
  echo "EVIDENCE_GATE: PASS"
else
  echo "EVIDENCE_GATE: FAIL"
fi
exit "$OVERALL"
