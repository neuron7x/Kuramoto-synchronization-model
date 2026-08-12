# Epistemic Drift Elimination Act (2026-05-26)

## Problem (one sentence)
Documentation claims, claim-registry values, and executable invariant counters must stay 1:1 synchronized or governance truth becomes noisy.

## Falsifiable hypothesis
If invariant counts drift across `README.md`, `CLAIMS.md` (`C-INV-COUNT`), and `scripts/count_invariants.py`, the guard must fail-closed (non-zero exit) and block promotion.

## Contract
- Input: repository working tree.
- Output: exit code `0` only when all synchronized.
- Boundary: only invariant-count governance claim (`C-INV-COUNT`) is enforced by this act version.

## Acceptance criteria (not completion criteria)
- Drift metric: `Δ = 0` across all checked sources.
- CI mode: runs on every PR and push to `main`.
- Local mode: pre-commit hook runs before commit.

## Rollback path
- Revert commit introducing `scripts/check_epistemic_drift.py`, `.github/workflows/check_epistemic_drift.yml`, and the hook stanza in `.pre-commit-config.yaml`.

## Artifact owner
- Repository maintainers / governance owners.

## Mandatory appendices
- Appendix A — Executable control: `scripts/check_epistemic_drift.py`
- Appendix B — CI actuation: `.github/workflows/check_epistemic_drift.yml`
- Appendix C — Local actuation: `.pre-commit-config.yaml`
- Appendix D — Registry synchronization evidence: `CLAIMS.md` row `C-INV-COUNT`
