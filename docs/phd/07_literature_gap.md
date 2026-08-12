# 07 — Literature Gap (DRAFT)

> Status: **draft literature gap**, not a final literature review. It positions
> the contribution against established standards; it does not survey the field
> exhaustively.

## Thesis

Artifact-evaluation, reproducibility, and secure-software-supply-chain practices
are individually strong, but computational-finance research often lacks a
**unified, machine-checkable claim-governance mechanism** that prevents
synthetic, incomplete, or unverifiable evidence from being promoted into
empirical truth. The bindings exist as conventions; they are rarely fail-closed
in CI.

## Anchor domains

### 1. Artifact evaluation / reproducibility

ACM's artifact-review badging distinguishes *Artifacts Available*, *Artifacts
Evaluated — Functional* (documented, consistent, complete, exercisable), and
*Reusable* (above + well-structured for reuse), plus *Results Validated* /
*Reproduced*. GeoSync targets *Functional/Reusable* readiness via an executable
reproducibility package (`docs/phd/10_artifact_reproducibility_package.md`). It
does **not** claim *Results Reproduced* for any market result — none exists.

### 2. Secure software development

NIST's Secure Software Development Framework (SSDF) frames practices that reduce
vulnerabilities in released software and remove their root causes. GeoSync's
wheel contract + import ratchet (`scripts/ci/check_wheel_contract.py`,
`scripts/ci/check_import_architecture.py`) operationalize "remove the root cause,
fail closed" for packaging defects (e.g. the 70 latent import failures recorded
in `artifacts/wheel_contract.json`).

### 3. Supply-chain provenance

SLSA frames build provenance that cryptographically identifies an output package
and describes its build path (build isolation, digest-bound outputs). GeoSync's
clean-room `git archive` build + `wheel_sha256` in `artifacts/wheel_contract.json`
are a partial, repo-local analogue; full SLSA attestation is **not** claimed.

### 4. Research software engineering

CI gates, reproducibility contracts, and negative-result integrity are
established RSE concerns; GeoSync's contribution is binding them into a single
*promotion* system (`scripts/ci/check_phd_traceability.py`,
`governance/FALSIFIER_LEDGER.yaml`, `governance/NEGATIVE_EVIDENCE.yaml`).

### 5. Quantitative finance / market-structure research

This domain carries high overclaiming risk. Synthetic data cannot establish real
market structure, and a backtest result cannot become truth without a
pre-registered protocol, deterministic replay, and independent validation. This
dissertation makes **no** market, profitability, or predictive claim; the L2
study is pre-registered as falsification, not as a return objective
(`docs/phd/05_next_empirical_chapter.md`).

## Gap statement

> GeoSync targets the missing interface between *research claims* and *software
> release mechanics*: a machine-checkable promotion system in which a claim may
> only move upward when its artifacts, falsifiers, and CI gates permit.

## Standard support vs original contribution

- **Standard support (not novel):** badging taxonomy, SSDF root-cause discipline,
  SLSA provenance concepts, RSE CI practice.
- **Original contribution (this work):** the *unified, fail-closed, CI-enforced
  claim-promotion ledger* that fuses these into one mechanism for
  market-structure research — see `docs/phd/02_contributions.md` (C1–C5).
