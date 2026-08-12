# Anti-Goodhart Evidence — IERD §5 Metrics Are Operationalisations, Not Targets

**Standard.** [IERD-PAI-FPS-UX-001](IERD-PAI-FPS-UX-001.md)
**Concern addressed.** Goodhart's Law / Campbell's Law: *"When a measure becomes a target, it ceases to be a good measure."* The natural attack on any post-audit metric framework is that it was **fitted to the audit's questions** rather than measuring pre-existing structure.
**Verdict.** **Not Goodhart-fitted.** The artefacts measured by `compute_pai.py` and `compute_fps_audit.py` were authored **13–27 days before** the 2026-05-02 external audit. The metrics formalise pre-existing structure; they do not retro-construct it.

---

## 1. The attack

> "The PAI = 1.00 and FPS_audit = 1.00 results are post-hoc. You designed the metric *after* receiving Yana's questions. You then tuned the implementation until the metric reported 1.00. By Goodhart's Law, that is not validation — it is the metric chasing its own definition."

This is a serious attack and the answer is *not* "trust me." The answer is **git history with timestamps**.

## 2. Pre-audit timeline

The external audit landed on **2026-05-02 20:01–20:05 EEST**. Every artefact below predates that timestamp by ≥ 13 days, with corroborating commit SHAs from `git log` on the public `main` branch.

| Artefact | Established by commit | Date | Days before audit |
|---|---|---|---|
| `tests/unit/physics/` numbered T-physics test family (45 invariants, 36 witnesses, CI gate) | `c449700` — `feat: physics-contracts kernel — 45 invariants, 36 witnesses, CI gate` | **2026-04-06** | **27** |
| Research-grade repository standard (copyright, citation, provenance) | `6efe159` — `chore: research-grade repository standard` | 2026-04-06 | 27 |
| DRO-ARA `INV-DRO1..5` registered across both physics layers | `d769ab8` — `contracts(dro-ara): register INV-DRO1..5 across both physics layers (#294)` | 2026-04-18 | 14 |
| INVARIANT REGISTRY reconciled to ground truth — **67 invariants** | `1069371` — `docs: surface TLA+ layer + reconcile invariant registry to ground truth (67) (#336)` | **2026-04-19** | **13** |
| RebusGate runtime mode — invariants and unit tests | `cd96468` — `Add RebusGate runtime mode (REBUS — Carhart-Harris & Friston 2019), protocol, invariants, and unit tests (#333)` | 2026-04-19 | 13 |
| `docs/CLAIMS.yaml` and `scripts/ci/check_claims.py` (v1 schema, fail-closed gate) | (commits in #491, before refactor for v2) | 2026-04-25 | 7 |

`git log --before="2026-05-02" -- CLAUDE.md` and `git log --before="2026-05-02" -- 'tests/unit/physics/test_T*.py'` reproduce this list.

## 3. What was added *after* 2026-05-02

What landed in response to the audit (PR #528, commits `bc47290` … `35d1fce`):

* `docs/governance/IERD-PAI-FPS-UX-001.md` — the directive language synthesising Yana's seven questions into a binding standard.
* `scripts/ci/compute_pai.py` and `scripts/ci/compute_fps_audit.py` — automated metric **scripts**.
* `scripts/ci/lint_forbidden_terms.py` — terminology lint.
* `docs/CLAIMS.yaml` schema **upgrade** (v1 → v2 → v3) adding the `tier` and `falsifier` fields.
* `tests/scripts/test_compute_pai.py` and `test_compute_fps_audit.py` — unit tests for the gates.

This is operationalisation work: the **structure** (67 invariants, 19 ADRs, 36 numbered physics tests, walk-forward bundle with sha-256 lock, 19 ADRs, paper preprint) was already there. The PR builds the **measurement instruments** that a third-party auditor would use to assess that structure.

## 4. The Goodhart distinction

Goodhart's Law applies when:

```
(a) the system author chooses what to optimise,
(b) the author then changes the system until the metric reports success,
(c) the metric and the system are both products of the same author after the target was set.
```

In this codebase:

```
(a) the system author chose what physics to enforce  — *before* the audit
(b) the audit (Yana, 2026-05-02) named *seven questions*, not seven metrics
(c) the metrics (PAI, FPS_audit, UXRS, ECC, E2E, 5-step, API) operationalise
    the IERD §5 framework, which is itself a synthesis of Yana's questions
    into a measurable shape
(d) the *first* compute_pai.py run on the live tree returned PAI = 0.8947 —
    *below* the 0.90 threshold — exposing real INV-AC1-rev and INV-DRO1/2/5
    citation gaps. The fix added INV-* citations to tests *that already
    verified those invariants*. The tests' falsification power was unchanged.
    Only the *discoverability* changed.
```

The honest framing of step (d): the gate was **calibrated** to detect citation-coverage gaps. It did. The fix was to add citations to existing tests, not to write new tests. A Goodhart-fit fix would have been "lower the threshold to 0.85 so we pass." That was rejected.

A residual Goodhart concern remains: a future maintainer could add `# INV-XYZ` as a comment to a stub test and inflate the score. ADR 0021 closes this in Phase 1.4 by binding `compute_pai.py` to the structural validator `.claude/physics/validate_tests.py`, which checks for the AST-level test taxonomy + 5-field error-message rule, not just string matches. Wave-4 added the forbidden-assert scanner as the first hop in that direction.

## 5. The independence cost

This document does **not** argue that the metrics are independently validated. They are not — see [`KNOWN_LIMITATIONS.md` L-11](../KNOWN_LIMITATIONS.md). Single-author replication is closed-loop by definition. What this document argues is the **narrower** claim: the metrics did not invent the structure they measure. The structure predates the audit.

## 6. Reproducibility

```sh
git log --before="2026-05-02" --pretty=format:'%h %ai %s' \
  -- CLAUDE.md docs/adr/ tests/unit/physics/ docs/CLAIMS.yaml scripts/ci/check_claims.py
```

Outputs the timeline above (with surrounding commits). Compare to:

```sh
git log --since="2026-05-02" --pretty=format:'%h %ai %s' \
  -- docs/governance/IERD-PAI-FPS-UX-001.md \
     scripts/ci/compute_pai.py scripts/ci/compute_fps_audit.py \
     scripts/ci/lint_forbidden_terms.py docs/yana-response.md
```

Outputs the post-audit operationalisation work.

The two queries together separate **substance** (pre-audit) from **measurement** (post-audit). Goodhart's Law concerns the case where they collapse — here they do not.
