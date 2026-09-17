# ECP-AS Iteration 001 — Engineering Report

**Status:** PASS_INTERNAL_VERIFICATION_PENDING_EXTERNAL_AUDIT

## Delivered

Iteration 001 extracts a domain-independent epistemic control plane from the existing GeoSync verification substrate. It adds an authoritative claim-state runtime, fail-closed promotion contracts, P/C/A/I oracle-independence checks, hidden-lineage rejection, tamper-evident event history, negative-evidence preservation/resolution, deterministic promotion certificates, typed dependency/invalidation primitives, a structured claim compiler, experiment ranking, legacy adapters, and an adversarial flagship witness.

## Internal verification

- 32/32 targeted ECP-AS tests PASS.
- `compileall` PASS.
- Pre-promoted claims are rejected at registration.
- State skipping is rejected.
- Ledger tampering is detected on reopen.
- Shared-lineage verifier is rejected as independent.
- Independent verifier permits `OBSERVED -> REPLICATED` when all other contract conditions hold.
- Unresolved blocking negative evidence prevents bounded promotion.
- Negative evidence is never rewritten; resolution is a separate event.

## Explicit boundary

This iteration establishes executable control-plane semantics. It does **not** yet establish that ECP-AS reduces unsafe scientific claim promotion in real autonomous-research workloads. That remains the central empirical proof obligation.
