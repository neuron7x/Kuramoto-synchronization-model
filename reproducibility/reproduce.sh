#!/usr/bin/env bash
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
#
# Reproduces the GeoSync canonical artefact set and verifies every
# output against its pinned sha256. A single non-matching line exits
# non-zero and surfaces the drift.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

green() { printf '\033[32m%s\033[0m\n' "$*"; }
red()   { printf '\033[31m%s\033[0m\n' "$*"; }

# ──────────────────────────────────────────────────────────────────────
# 1. CNS ontology guard — structural + SLA-bounded contract check.
# ──────────────────────────────────────────────────────────────────────
green "▸ 1/3 · CNS ontology guard"
python scripts/check_cns_ontology_usage.py

# ──────────────────────────────────────────────────────────────────────
# 2. TLA⁺ TLC — model-checks the admission-gate safety invariants.
# ──────────────────────────────────────────────────────────────────────
green "▸ 2/3 · TLA+ admission-gate proof"
TLC_OUTPUT="$(mktemp)"
(
  cd formal/tla
  java -cp /opt/tla2tools.jar tlc2.TLC -config MC.cfg AdmissionGate.tla
) > "$TLC_OUTPUT" 2>&1 || { red "TLC failed"; cat "$TLC_OUTPUT"; exit 1; }

# Assert TLC signalled successful completion.
if ! grep -q "Model checking completed. No error has been found" "$TLC_OUTPUT"; then
  red "TLC did not report clean completion"
  cat "$TLC_OUTPUT"
  exit 1
fi
# And that it explored the expected state space (the spec pins
# 853 states / 547 distinct when the constants in MC.cfg stay fixed).
if ! grep -q "853 states generated, 547 distinct states found" "$TLC_OUTPUT"; then
  red "TLC state-space diverged from pinned expectation (853/547)"
  grep "states generated" "$TLC_OUTPUT" || true
  exit 1
fi
green "  ✓ TLC explored 853 states, 547 distinct, 0 invariant violations"

# ──────────────────────────────────────────────────────────────────────
# 3. Sha256 pinning of the canonical artefacts.
# ──────────────────────────────────────────────────────────────────────
green "▸ 3/3 · sha256 manifest verification"
(
  cd "$ROOT"
  sha256sum --check --strict reproducibility/manifest.sha256
)
green "  ✓ every pinned artefact matches"

green "✓ reproduction complete — all three checks green"
