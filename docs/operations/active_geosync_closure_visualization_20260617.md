# Active GeoSync Closure Visualization

Status: coordination artifact.

Scope: operational visualization only. This document changes no runtime code, physics model, neuro validation, UI behavior, trading logic, or scientific claim.

Purpose: make the active closure protocol visually inspectable in a GitHub PR.

---

## 1. Terminal State Machine

```mermaid
stateDiagram-v2
    [*] --> OPEN

    OPEN --> VERIFIED: evidence collected
    OPEN --> FAILED: gate failed
    OPEN --> BLOCKED: external dependency

    VERIFIED --> MERGEABLE: same-SHA CI green + metrics pass
    MERGEABLE --> MERGED: merge executed

    FAILED --> ROOT_CAUSED: failure classified
    ROOT_CAUSED --> PATCHED: minimal fix applied
    PATCHED --> VERIFIED: re-run exact gates

    BLOCKED --> EXPLICIT_OWNER: owner + unblock condition recorded
    EXPLICIT_OWNER --> OPEN: dependency resolved

    MERGED --> LEDGER_SYNCED: resolution_ref recorded
    LEDGER_SYNCED --> SCORECARD_UPDATED: computed verdict refreshed
    SCORECARD_UPDATED --> [*]
```

---

## 2. Active PR Dependency Graph

```mermaid
graph TD
    A[#1153 Real CI Test Oracle] --> B[#1155 Governance Runtime Binding]
    A --> C[#1156 / #1154 Neuro Invariant Closure]
    A --> D[#1150 Kuramoto K-Scaling]
    A --> E[#1152 Ricci False-Bound Correction]
    A --> F[#1147 Q7 ECC / UI E2E]

    B --> G[Ledger Sync]
    C --> G
    D --> G
    E --> G
    F --> G

    G --> H[Final Physics / Governance Scorecard]

    A -. if backlog expands .-> Q[Quarantine Ledger]
    Q --> B
    Q --> C
    Q --> D
    Q --> E
    Q --> F
```

Interpretation:

- #1153 is the measurement keystone.
- Dependent lanes must be revalidated after #1153 terminalizes or after an explicit quarantine plan exists.
- The final scorecard is downstream of ledger synchronization, not upstream prose.

---

## 3. Execution Lane Map

| Lane | PR | Responsible role | Primary object | Required proof | Stop condition |
| --- | ---: | --- | --- | --- | --- |
| Measurement | #1153 | Measurement Owner | real fast-test oracle | non-zero collected tests + fail-closed zero guard | CI terminal or measured backlog ledger |
| Governance | #1155 | Governance Runtime Owner | runtime-bound governance kernel | scoring loaded, executed, thresholded, weakest-link clamped | runtime-binding tests green |
| Neuro | #1156 / #1154 | Neuro Invariant Owner | dopamine/serotonin trajectory invariant | fail-before/pass-after trajectory tests | C-NEURO-003 resolved or explicitly blocked |
| Kuramoto | #1150 | Physics Boundary Owner | K-scaling ownership | ambiguous K path rejected, valid declared path accepted | scale ambiguity = 0 |
| Ricci | #1152 | Physics Boundary Owner | false curvature-bound removal | tests prevent reintroduction of false bound | descriptor/policy boundary preserved |
| Q7 | #1147 | UI/E2E Owner | ECC runtime proof | CI Playwright evidence or bounded local gap | ECC evidence recorded |
| Ledger | follow-up | Ledger Owner | canonical audit truth | JSON/Markdown agreement + resolution_ref | stale entries = 0 |
| Scorecard | final | Ledger Owner | computed verdict | PASS/PARTIAL/FAIL derived from metrics | no prose-only verdict |

---

## 4. Metrics v2 Heatmap

Legend:

- PASS: evidence satisfies target.
- PARTIAL: evidence exists but has bounded gap.
- FAIL: required proof missing or contradicted.
- UNKNOWN: measurement unavailable; caps lane verdict at PARTIAL.

| Metric | Owner | Source of truth | PASS | PARTIAL | FAIL |
| --- | --- | --- | --- | --- | --- |
| real_test_oracle | Measurement Owner | GitHub Actions + collection log | collected_tests > 0 and zero-collection guard active | known backlog quarantined | any shard passes 0/0 |
| ci_truth | All lane owners | same-SHA PR checks | all required checks green on head SHA | non-critical optional check bounded | stale SHA, skipped gate, pending required gate |
| governance_binding | Governance Runtime Owner | runtime tests | kernel loaded and executed | advisory-only path bounded | JSON artifact not executed |
| dead_invariants | Neuro Invariant Owner | validation code + tests | 0 declared-unchecked invariants | invariant blocked with owner | config declares invariant without validation path |
| physics_ambiguity | Physics Boundary Owner | invariant/equivalence tests | ambiguity count = 0 | documented future capability gap | silent K scaling or false Ricci bound remains |
| ecc_runtime | UI/E2E Owner | CI Playwright / route specs | ECC >= 0.90 with runtime proof | local gap explicitly bounded | ECC claim without runtime proof |
| ledger_staleness | Ledger Owner | audit JSON + Markdown | stale entries = 0 | pending entry has explicit owner | merged PR listed as IN_PROGRESS |
| quarantine_integrity | Measurement Owner | quarantine ledger | every entry has owner, issue, expiry | limited temporary quarantine | hidden failures or unowned quarantine |
| cognitive_risk | Acting agent | cognitive gate | LOW/MEDIUM with mitigation | MEDIUM with explicit risk | HIGH before patch/merge |
| final_verdict_integrity | Ledger Owner | scorecard test | verdict computed from metrics | PARTIAL due known gaps | PASS with any required FAIL/UNKNOWN |

---

## 5. Closure Timeline

```mermaid
gantt
    title Active GeoSync Closure Order
    dateFormat  YYYY-MM-DD
    axisFormat  %m-%d

    section Measurement
    #1153 real fast-test oracle           :active, a1, 2026-06-17, 1d
    backlog measurement or quarantine     :a2, after a1, 1d

    section Governance
    #1155 runtime-binding revalidation    :b1, after a2, 1d

    section Physics / Neuro
    #1156 / #1154 neuro invariant         :c1, after b1, 1d
    #1150 Kuramoto scale ownership        :c2, after b1, 1d
    #1152 Ricci false-bound correction    :c3, after b1, 1d

    section UI / E2E
    #1147 Q7 ECC runtime boundary         :d1, after b1, 1d

    section Closure
    Ledger synchronization                :e1, after c1, 1d
    Final computed scorecard              :e2, after e1, 1d
```

Timeline semantics:

- Durations are placeholders for order, not calendar estimates.
- #1153 remains first because it restores the measurement instrument.
- Final scorecard starts only after active lanes are terminal or explicitly bounded.

---

## 6. Cognitive Evaluation Gate

```mermaid
flowchart TD
    P[Perception: What live state is observed?]
    A[Attention: What is the single active lane?]
    M[Memory: What assumptions came from prior context?]
    R[Reasoning: What inference connects evidence to action?]
    D[Decision: Patch, block, remeasure, or merge?]
    E[Error Check: What could be misread?]
    C{Cognitive risk HIGH?}
    S[Stop before patch or merge]
    X[Execute minimal action]

    P --> A --> M --> R --> D --> E --> C
    C -- yes --> S
    C -- no --> X
```

Required pre-action questions:

| Cognitive dimension | Required question | Blocking condition |
| --- | --- | --- |
| Perception | Did I inspect current PR state, files, and CI? | acting from memory only |
| Attention | Is there exactly one selected lane? | multi-lane patch without collision map |
| Memory | Which assumptions are stale-risk? | relying on old green state |
| Reasoning | What proof converts observation into action? | inference lacks test or log evidence |
| Decision | What is the smallest valid state transition? | broad refactor or unrelated cleanup |
| Interpretation | What term could be overloaded? | metaphor treated as runtime proof |

---

## 7. Final Readiness Funnel

```mermaid
flowchart LR
    O[Open PR Surface]
    T[#1153 Real Oracle]
    R[Revalidated Lanes]
    L[Ledger Sync]
    S[Scorecard]
    V{Final Verdict}

    O --> T
    T --> R
    R --> L
    L --> S
    S --> V

    V -- any required FAIL --> F[FAIL]
    V -- any UNKNOWN --> P[PARTIAL]
    V -- all required PASS --> PASS[PASS]
```

Readiness rule:

The final verdict cannot exceed the weakest required metric.

- Any required FAIL means FAIL.
- Any required UNKNOWN caps verdict at PARTIAL.
- PASS requires all required gates to be green on current evidence.
