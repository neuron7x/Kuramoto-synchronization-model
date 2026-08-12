# Independent Signal-vs-Noise Audit (Deep, Verified)

Date (UTC): 2026-05-26  
Scope: repository-level governance, claim discipline, and verification plumbing (not strategy profitability)

## 1) One-line problem statement
Can this repository be trusted as a **research-grade, falsifiable, evidence-linked system** (signal), or is it mostly narrative complexity without enforceable proof (noise)?

## 2) Falsifiable hypothesis
**H0 (noise-dominant):** claims are not consistently tied to executable checks and reproducible artifacts.  
**H1 (signal-dominant):** core claims are bound to explicit evidence tiers, machine-checkable invariants, and test/CI controls.

**Refutation condition for H1:** if we find unresolved contradiction between headline claims and registry/evidence, or broken claim-validation path without explicit quarantine.

## 3) Invariants / contracts used for this audit
- Claim-evidence contract: every promoted claim must map to tier + artifact/process pointer.
- Invariant registry contract: declarative invariant count must be script-verifiable.
- Falsification contract: null/negative/adversarial pathways must exist in-code/docs.

## 4) Independent verification steps (executed)
1. Read top-level scientific/governance contract docs (`README.md`, `CLAIMS.md`).
2. Run invariant counter script.
3. Run claims-evidence validation tests.
4. Classify findings into **signal**, **noise**, **critical ambiguity**.

## 5) Findings

### SIGNAL (strong)
1. **Explicit claim tiering exists** (FACT/MEASURED/DERIVED/SIMULATION/etc.) with promotion/demotion protocol.  
2. **Registry-first narrative exists**: README states claim boundary and references invariant registry and formal checks.  
3. **Executable invariant count check works** (`scripts/count_invariants.py` returns 97).  
4. **Falsification framing is present** in claims language (e.g., hypothesis gates and explicit retractions).

### NOISE / RISK (material)
1. **Internal contradiction in invariant count claims**:
   - README presents 97 invariants.
   - Historical drift (87 vs 97) has been remediated; synchronization is now enforced by guardrails.
   - Script returns 97 now.
   This is governance drift and creates epistemic noise.
2. **Claims-evidence test suite currently red in this environment**, but failure is infrastructure-level deprecation path in `conftest.py` (`asyncio.iscoroutinefunction` deprecation under Python 3.14), not the claim logic itself.

## 6) Checklist mapping (your RESEARCH·ENGINEERING checklist)

- **PRE-WORK:** mostly satisfied at governance layer (problem, hypothesis, contracts, retraction pathways are explicit).
- **MATH:** partially evidenced (formulas present, but this audit did not rerun full numerical batteries).
- **IMPLEMENTATION:** strong modularization signal; however documentation consistency lag adds noise.
- **VALIDATION:** mixed; validation intent is strong, but local red tests indicate compatibility fragility.
- **FALSIFICATION:** strong positive signal (null/negative/retraction machinery is first-class).
- **ARTIFACT:** medium; many artifacts exist, but a key ledger mismatch degrades trust.
- **GOVERNANCE:** medium-to-strong; process exists, but stale claim count should be fixed immediately.
- **FINAL TEST (minimality):** current system is *not yet minimal-clean* because contradictory invariant count can be removed without harming core function and should be removed.

## 7) Verdict: Signal repo or noise repo?

**Verdict: SIGNAL-dominant, with governance-noise debt.**

Why:
- This is not random buzzword ware: there is a real claim-evidence apparatus, invariant registry discipline, and explicit falsification/retraction language.
- Trust risk is now primarily operational: guardrails must stay green in CI and local hooks to prevent regressions.

## 8) Priority actions (ordered)
1. Keep `C-INV-COUNT` synchronized via automated drift guards (CI + pre-commit).
2. Keep `conftest.py` on stable coroutine inspection API and enforce with tests.
3. Keep numeric drift checks fail-closed and visible in CI status.

## 9) Owner-facing summary (plain language)
If you are new owner: this repo is **not garbage**. It has unusually strong scientific-governance scaffolding. But you should treat it like an advanced lab with some stale labels. Fix the label drift and Python-compat test harness first; then you can trust the dashboards/claims much more.
