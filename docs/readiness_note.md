# GeoSync Readiness Advancement Contract

GeoSync is treated here as a strong research-engineering system, not as a finished production-critical system. This note defines the next maturity layer as an evidence problem, not as a branding exercise.

## First principles

1. A claim is allowed only when its evidence tier is explicit.
2. A stronger claim requires stronger evidence, not stronger prose.
3. Synthetic evidence can validate mechanics, but it cannot validate real-world deployment claims.
4. Review gates must fail closed when evidence is missing.
5. The repository should preserve negative findings as governance memory.

## Current boundary

Current level: L4-minus institutional research-engineering platform.

Target direction: L5 candidate readiness.

This document does not promote the repository. It opens the path by making the remaining gaps explicit and reviewable.

## Readiness gaps

| ID | Gap | Required closure signal |
|----|-----|--------------------------|
| RD-001 | Real-data validation is incomplete for promoted market-facing research claims. | Dataset provenance, content hashes, pre-registered evaluation windows, and reproducible result artifacts. |
| QA-001 | Content-aware PR checks do not prove full repository cleanliness. | Scheduled or merge-queue whole-repository quality lane with retained evidence. |
| GOV-001 | Report-only review surfaces must become blocking where they protect promoted claims. | Blocking check, explicit waiver protocol, and expiry-bound exceptions. |
| OPS-001 | Operational readiness evidence is not complete. | Runbooks, recovery drills, runtime safety checks, and retained execution evidence. |
| EXT-001 | Independent review must be tied to remediation evidence. | Finding-to-commit map and post-remediation verification artifacts. |

## Integration ladder

1. Boundary: keep the current claim level explicit.
2. Register: keep each readiness gap named and tracked.
3. Evidence: require structured artifact records for any resolved entry.
4. Gate: run the readiness checker in CI.
5. Review: map external findings to committed remediation artifacts.

## Non-goals for this PR

- No claim promotion.
- No performance claim reactivation.
- No production-readiness badge.
- No replacement of existing claims governance.

## Immediate next step

Add a machine-checkable readiness register and a validator that prevents silent closure of a readiness gap without evidence.
