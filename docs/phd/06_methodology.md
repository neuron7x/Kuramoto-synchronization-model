# 06 — Methodology

## 1. Research Design

This is an **artifact-centered** dissertation: the object of study is a running
repository and its CI, not a market deployment. The design is **verification-
first** — a claim is admissible only when machine-checked bindings exist — and
**falsification-over-confirmation**: the system is evaluated by what it *refuses
to let pass*. CI is treated as an **operational oracle** (a gate that blocks
release), explicitly **not** as a source of epistemic or scientific truth: a
green pipeline is necessary, never sufficient.

## 2. System Boundary

GeoSync is research-governance infrastructure. It is **not** a trading bot, it
is **not** a return-generating product, and it does **not** assert any market
regularity as proven. No profitability, edge, or investment claim is made
anywhere in this dissertation (enforced by `scripts/ci/check_claim_boundary.py`
and `scripts/ci/check_phd_traceability.py`).

## 3. Claim Lifecycle

A claim moves through explicit stages and may only advance when the bound gate
permits:

```
HYPOTHESIS → ADMISSIBLE → MEASURED → REPLICATED → REJECTED / RETIRED
```

- HYPOTHESIS: stated, not yet bound.
- ADMISSIBLE: bound to invariant + method + falsifier + CI gate (no empirical
  result yet). This is the highest tier most of GeoSync currently occupies.
- MEASURED: a real dataset + replay produced a verdict (none claimed here).
- REPLICATED: an independent re-run reproduced the verdict.
- REJECTED / RETIRED: a falsifier killed it; recorded as preserved negative
  evidence (`governance/NEGATIVE_EVIDENCE.yaml`), never rewritten.

## 4. Claim Binding Model

Every claim binds to eight artifacts: invariant (`.claude/physics/INVARIANTS.yaml`),
dataset, method, artifact, falsifier (`governance/FALSIFIER_LEDGER.yaml`), replay
command, CI gate, and a limitation-ledger entry (`docs/phd/04_limitation_ledger.md`).
Missing any binding caps the claim at HYPOTHESIS.

## 5. Negative-Evidence Method

Failure, rejection, downgrade, and non-promotion are treated as **positive
research outputs**. A killed hypothesis that is sha-anchored and preserved is a
contribution, not an embarrassment. The preservation contract is enforced by
`scripts/ci/check_negative_evidence.py`; rewriting a negative into a "partial
success" fails the build.

## 6. Software-Artifact Method

The governance is implemented as committed, CI-enforced mechanisms — the wheel
contract (`scripts/ci/check_wheel_contract.py`), the package-boundary ratchet
(`scripts/ci/check_package_boundary.py`), the import ratchet
(`scripts/ci/check_import_architecture.py`), the falsifier ledger
(`scripts/ci/check_falsifier_ledger.py`), and diff-bound commit acceptors
(`tools/commit_acceptor/validate_commit_acceptor.py`). Method = code + gate, not
prose.

## 7. Validity Discipline

Five validity layers are kept strictly separate and never conflated:

| Layer | Question | Evidence |
|---|---|---|
| build validity | does it build/install cleanly? | `artifacts/wheel_contract.json` |
| artifact validity | is the output schema-valid + hashed? | schema gates |
| claim admissibility | is the claim bound to a falsifier + gate? | `check_phd_traceability.py` |
| empirical validity | did a real dataset produce the verdict? | NOT established (see `05`) |
| external validity | does it generalize beyond this repo/domain? | NOT established (see `09`) |

The dissertation contributes at the first three layers. The last two are open
(`docs/phd/09_threats_to_validity.md`). Admissibility is never reported as
empirical truth.
