<!--
NOTE: this policy doc is itself part of the authoritative doc set, but it does
not assert a project maturity state, so it is not one of the gated docs in
scripts/ci/check_doc_status.py. It documents the schema and the gate.
-->

# Doc-Status Policy (DOC-003)

Authoritative status/release documents in this repository carry a
machine-readable **`doc_status`** front-matter block that pins their place on
the temporal-truth axis: is this document describing the project as it **is**
now, as it **was** at some point, or as we **intend** it to be?

The single source of truth for the project's maturity rung and the forbidden
claim-word firewall is [`governance/project_state.yaml`](../governance/project_state.yaml)
(GOV-005). Its `current_state` is **`RESEARCH_ALPHA`** — live claims rest on
synthetic / single-session evidence only, nothing is deployable. This policy
exists so no document that presents itself as *current* silently contradicts
that rung (e.g. by claiming "production-ready" or "validated").

## Front-matter schema

```yaml
---
doc_status:
  status: current            # required — current | historical | aspirational
  authoritative_for:         # required — non-empty list of concern tokens
    - <concern>
  valid_from: 2026-07-19     # required — ISO date the doc became authoritative
  valid_to: 2026-07-16       # optional — end of the validity window
  superseded_by: <path|id>   # optional — what replaced this doc
  generated_by: <path>       # optional — generator, for rendered surfaces
  defines_claim_vocabulary: false  # optional — see "use/mention" below
---
```

| Field | Required | Meaning |
| --- | --- | --- |
| `status` | yes | `current` (describes the project now), `historical` (a past snapshot, kept as evidence), `aspirational` (a target we have not reached). |
| `authoritative_for` | yes | The concern(s) this doc is the source of truth for. Non-empty. |
| `valid_from` | yes | ISO date the doc's content became authoritative. |
| `valid_to` | for `historical` | ISO date the validity window closed. |
| `superseded_by` | for `historical` | Path/id of the doc or artifact that replaced it. |
| `generated_by` | no | Generator script, for status surfaces rendered from the SSOT. |
| `defines_claim_vocabulary` | no | `true` only on the one doc that defines the firewall words. |

A **`historical`** doc must declare `valid_to` and/or `superseded_by` — it has
to say *why* it is no longer current. That is the difference between an honest
historical record and stale rot.

## The gate

`scripts/ci/check_doc_status.py` enforces, fail-closed:

1. **Schema** — every doc in the authoritative set has a parseable, valid
   `doc_status` block.
2. **No stale-current contradiction** — a doc marked `current` may not use a
   maturity/claim word that outranks `current_state`. The forbidden words come
   from the SSOT firewall (`validated`, `proven`, `production-ready`,
   `production-grade`, `deployable`, `guaranteed`, `risk-free`, …). Because the
   project is `RESEARCH_ALPHA`, any such word used as an affirmative prose claim
   in a `current` doc is a contradiction and fails the gate.

`historical` and `aspirational` docs are **not** scanned for maturity claims.
A historical release-truth snapshot is *allowed* to record a past claim — that
is exactly why we **mark it historical rather than delete it**.

Exit codes: `0` clean · `1` a `current` doc contradicts the project state ·
`2` structural error (missing/unparseable front-matter, bad schema, bad SSOT).

The gate writes an enumerated report to
[`artifacts/governance/doc_status_report.json`](../artifacts/governance/doc_status_report.json).

```bash
python scripts/ci/check_doc_status.py            # gate the tagged set + write report
python scripts/ci/check_doc_status.py --doc P.md # gate a single doc
```

## Use / mention discipline

The gate must not fire on the *vocabulary itself*. Three carve-outs, all
recorded in the report (never silent):

- **Code is not prose.** Fenced code blocks (```` ``` ````) and inline
  `` `code` `` are stripped before scanning — a claim word in an example
  command is not an assertion.
- **Definitional mentions.** A prose line that names a forbidden word as a
  definition/negation can carry the inline marker
  `<!-- doc-status:claim-mention -->`; the gate skips it and counts it in
  `mention_exemptions`.
- **The vocabulary-defining doc.** The one doc that *defines* the firewall
  (`docs/PROJECT_STATE_ONTOLOGY.md`) sets `defines_claim_vocabulary: true`; it
  is recorded, not scanned. At most one doc may set this.

## Governed doc set (current)

| Doc | Status | Authoritative for |
| --- | --- | --- |
| `docs/PROJECT_STATE_ONTOLOGY.md` | current | project maturity state, claim firewall |
| `docs/RELEASE_GATES.md` | current | release-gate requirements |
| `BASELINE.md` | current | physics invariant counts, grounding baseline |
| `DELIVERY.md` | historical | pre-final delivery snapshot (2026-05-05) |
| `docs/project-status.md` | historical | release-readiness snapshot (2025-12-19) |
| `ROADMAP.md` | aspirational | strategic roadmap |

## Residual / follow-up

This policy and gate cover the **authoritative** status/release set plus the
enforcing mechanism. Full-repository doc coverage (tagging the long tail of
`docs/**`, `*.md` reports and audit trails) is a larger follow-up: extend
`TAGGED_DOCS` in the gate as docs are triaged, and mark contradictory
historical release-truth docs `historical` rather than editing away their
past claims.
