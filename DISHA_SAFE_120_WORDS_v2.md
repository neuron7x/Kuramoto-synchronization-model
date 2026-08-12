# DISHA — 120-word safe paragraph (v2)

> **TODO**: hand-written by Yaroslav Vasylenko before merge.

The PR #592 spec mandates that this 120-word paragraph is NOT auto-generated.
The instrument is now claim-bounded; the wording for Disha must be authored
by a human anchored to:

* the validated findings ledger in
  `tools/disha_artifact/summary_compiler.py::VALIDATED_FINDINGS`
* the four claim-tier categories in
  `instrument_validation/verdict.py::{ClaimTier, ClaimType}`
* the explicit forbidden phrases in
  `instrument_validation/claim_boundary.py::FORBIDDEN_UNLESS_CERTIFIED`

Anchor each sentence to a `F-*` finding ID or the `[EXPLORATORY]` tag.
Do NOT use any phrase from `FORBIDDEN_UNLESS_CERTIFIED` without a matching
certificate (none are obtainable at N=31 under this scope — see G2).
