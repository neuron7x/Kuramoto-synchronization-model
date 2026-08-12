# 01 — Research Questions

Each question is empirical about the *infrastructure*, answerable by repository
evidence (files, PRs, CI runs, artifacts). None is a market-performance question.

## RQ1 — Can machine-enforced claim governance reduce false empirical promotion?

**Operationalization.** Define false promotion as an unsupported promotion term
("validated", "profitable", "alpha", "edge", "predictive", "production-ready")
asserted without a linked evidence-chain or negative context. Measure whether a
fail-closed scanner + claim-boundary gate blocks such text at PR time.

**Evidence surface.** `scripts/ci/lint_forbidden_terms.py`,
`scripts/ci/check_claim_boundary.py`, `scripts/ci/check_claims.py`; release-gate
section A. **Negative finding recorded** (intellectual honesty): a naive
bare-word ban over-rejects honest *disclaimers* (e.g. "makes no predictive
claim" appears 34× in docs); the gate is deliberately narrow (compound patterns),
so RQ1's answer is *qualified yes within a scoped term-set*, not universal.

## RQ2 — Can artifact contracts expose hidden reproducibility debt before release?

**Operationalization.** Build the distributable wheel from a clean
`git archive HEAD` and detect packaged modules that import unpackaged first-party
namespaces (latent `ModuleNotFoundError` on clean install) and dead console
scripts — before release.

**Evidence surface.** `scripts/ci/check_wheel_contract.py` →
`artifacts/wheel_contract.json`. **Result:** exposed **70** pre-existing latent
broken imports (e.g. packaged `src/geosync/sdk/mlsdm/facade.py` imports
unpackaged `rl`, `runtime`) that no prior gate detected — direct affirmative
evidence for RQ2. A second hidden defect surfaced by the contract: a stale local
`build/` directory silently re-ships removed packages, defeating naive
`pip wheel .` (mitigated by clean-archive build).

## RQ3 — Can CI-gated falsifiers preserve negative-result integrity in market-structure research?

**Operationalization.** Require that each null/kill-test be *executable* (real
code + a test witness), recorded in a machine-readable ledger, and that a failed
falsifier blocks claim promotion; require that negative results be preserved
(sha-anchored, never rewritten into "partial success").

**Evidence surface.** `governance/FALSIFIER_LEDGER.yaml` (6 executable
falsifiers: permutation, phase-randomized/IAAFT, topology-preserving, cost-model,
lookahead-leakage, timestamp-integrity) + `scripts/ci/check_falsifier_ledger.py`
(fail-closed: rots → RED); `governance/NEGATIVE_EVIDENCE.yaml` +
`scripts/ci/check_negative_evidence.py` (preservation gate). **Result:**
affirmative for the *mechanism*; RQ3's empirical leg (does this preserve
integrity on a *real* market dataset?) is deferred to the chapter in `05` — no
real L2 falsification study has been run.
