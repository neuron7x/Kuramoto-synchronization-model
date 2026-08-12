# `docs/exocortex/` — Provenance & Methodology Index

This directory is the **research-provenance layer** of GeoSync: the small set of
documents required to reconstruct *why* the codebase looks the way it does and
*how* it stays correct. It is not API documentation. It is the trail an external
auditor follows from a passing test back to a falsifiable physical claim.

## Contents

| File | Purpose | Audience |
| --- | --- | --- |
| [`METHODOLOGY.md`](./METHODOLOGY.md) | Adversarial-orchestration roles, validation gates, escalation rules | Contributors, reviewers |
| [`RESEARCH_TIMELINE.md`](./RESEARCH_TIMELINE.md) | Chronology of substrates, models, and milestones the codebase rests on | Auditors, scientific reviewers |
| [`GLOSSARY.md`](./GLOSSARY.md) | Precise definitions of γ, INV, TACL, MFN, BN-Syn, and other in-house terms | New contributors |
| [`INVARIANTS_INDEX.md`](./INVARIANTS_INDEX.md) | Map of the 60 physics invariants in [`.claude/physics/INVARIANTS.yaml`](../../.claude/physics/INVARIANTS.yaml) by category and priority | Test authors, CI gatekeepers |
| [`VALIDATION.md`](./VALIDATION.md) | Exact commands for the five validation gates, in order | Contributors, CI engineers |

## Authority hierarchy

When two artifacts disagree, the right one to trust is the one closer to the
top of this list:

1. [`.claude/physics/INVARIANTS.yaml`](../../.claude/physics/INVARIANTS.yaml) — machine-readable physics constraints
2. [`physics_contracts/catalog.yaml`](../../physics_contracts/catalog.yaml) — module-anchored law catalog (parallel layer)
3. The Python tests under [`tests/`](../../tests/) that reference `INV-*` IDs
4. The narrative documents in this directory
5. Anything else

If a doc here contradicts the YAML, fix the doc. If a test contradicts the YAML,
fix the test or escalate the invariant — never weaken the assertion.

## Scope boundary

`.exocortex/` documents claims that are **provable from the repository** or
**published in cited literature**. It does not contain hypotheses that have not
yet been falsified. Speculative work lives under [`docs/`](..) or in
external research notes — not here.
