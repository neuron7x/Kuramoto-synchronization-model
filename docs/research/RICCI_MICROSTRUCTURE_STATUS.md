# Ricci Microstructure — Canonical Lane Status

> **Status:** canonical lane-status. This is the **single** source of truth for
> the Ricci-microstructure research lane. The audit found three different
> status vocabularies across `docs/RICCI_MICROSTRUCTURE.md`,
> `docs/research/l2_ricci_evidence_protocol.md`, and `FORBIDDEN_CLAIMS.md`; this
> document reconciles them. Those documents should link here for status.

## Canonical status

| Field | Value |
|---|---|
| Lane | Ricci microstructure (L2 order-book curvature descriptor) |
| Domain | `market_microstructure_hypothesis` (see `docs/PHYSICS_CANON.md`) |
| Maturity | `HYPOTHESIS` |
| Evidence status | `Not Deployable` |
| Evidence boundary | One crypto-perps L2 session (single, immutable artifact) |
| Decision | `OBSERVE` |
| Falsifier | Multi-session failure, null-superiority, or cost-model failure |

## Reconciliation of prior wording

The three legacy descriptions are **consistent**, in different vocabularies;
they map onto the canonical row above as follows:

- `docs/RICCI_MICROSTRUCTURE.md` — "T3 / NOVEL / EXPLORATORY / FALSIFIABLE";
  the legacy doc already disclaims alpha, deployment, and confirmed-physics
  status. → exploratory-tier framing of `HYPOTHESIS`.
- `docs/research/l2_ricci_evidence_protocol.md` — `claim_tier: HYPOTHESIS`,
  `semantic_validation_status: PLACEHOLDER`, `decision: OBSERVE`. → the
  invariant-system framing; authoritative for the promotion protocol.
- `FORBIDDEN_CLAIMS.md` — allowlist entry "Ricci Microstructure", evidence
  boundary "one crypto-perps L2 session", status "Not Deployable". →
  the firewall framing of the same status.

## Non-claims

This lane makes **no** out-of-sample edge claim, **no** profitability claim, and
is **not** a deployable signal. It is a falsifiable descriptor under observation;
promotion above `HYPOTHESIS` requires multi-session real-data evidence with
data/config hashes, a seed, and a null baseline that the descriptor beats — see
the promotion protocol in `docs/research/l2_ricci_evidence_protocol.md`.

## Promotion gate

To advance `HYPOTHESIS → INSTRUMENTED → Measured-Single → Measured-Multi`:

1. Real L2 artifact with schema + provenance hashes (not synthetic).
2. Null baseline result the descriptor must strictly beat.
3. Falsifier run (multi-session / cost-model) returning the documented verdict.
4. Replay path that reproduces the artifact byte-for-byte.

Until all four hold across independent sessions, the canonical status remains
`Not Deployable`.
