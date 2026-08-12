# GeoSync Productization Map

**Status:** map. Not a sales sheet.
**Schema source:** `docs/product/packages.yaml`.
**Lie blocked:** *"engineering depth = market value"*.

Every line below corresponds to an artifact already merged to `main`.
Where a deliverable is missing or thin, the entry is removed — never
softened. Each package has buyer pain, deliverables, timeline band,
price band, the **proof artifact** that buyers can inspect, the
**demo command** they can run before signing, and an explicit
**non-claims** list bounding what the package will not do.

---

## P_FALSE_CLAIM_AUDIT

- **Buyer pain:** confident claims (release notes, governance reports)
  cannot be mechanically verified.
- **Deliverables:** false-confidence audit + exemption manifest +
  regression detector wired into CI.
- **Timeline:** ~2 weeks. **Price band:** light.
- **Proof artifact:** `.claude/audit/false_confidence_exemptions.yaml`
- **Demo command:**
  `python tools/audit/false_confidence_detector.py --exit-on-finding`
- **Non-claims:** does not certify zero defects; does not replace
  human review; does not promise specific finding reductions.

## P_AI_RESEARCH_VERIFICATION

- **Buyer pain:** multi-model AI outputs cannot be evaluated against
  a uniform evidence gate.
- **Deliverables:** cross-agent review harness, forbidden-overclaim
  red-line set, falsifier forge from claim ledger.
- **Timeline:** ~3 weeks. **Price band:** medium.
- **Proof artifact:** `tools/agents/cross_agent_review_harness.py`
- **Demo command:** `python -m pytest tests/agents -q`
- **Non-claims:** does not rate models against each other; does not
  assert one model is more truthful; does not replace domain review.

## P_QUANT_GOVERNANCE_HARDENING

- **Buyer pain:** governance and release ledgers drift from underlying
  claims; releases cannot be replayed.
- **Deliverables:** proof-carrying PR manifest validator, replayable
  reality ledger, PR-level reality budget gate.
- **Timeline:** ~4 weeks. **Price band:** heavy.
- **Proof artifact:** `docs/releases/replay_manifest_2026_04_27.yaml`
- **Demo command:**
  `python tools/governance/replay_release_ledger.py --manifest docs/releases/replay_manifest_2026_04_27.yaml`
- **Non-claims:** does not promise alpha or edge; does not certify
  regulatory compliance; does not enforce business policy beyond the
  structural gates.

## P_DEPENDENCY_REACHABILITY_SECURITY

- **Buyer pain:** security reports show 'patched in lockfile' while
  Dockerfiles install a different manifest.
- **Deliverables:** dependency-truth unifier (D1..D7), reachability-
  graph integration test for GraphQL WS, scanner-path mismatch detector.
- **Timeline:** ~3 weeks. **Price band:** medium.
- **Proof artifact:** `tools/deps/validate_dependency_truth.py`
- **Demo command:** `python tools/deps/validate_dependency_truth.py`
- **Non-claims:** does not replace pip-audit or trivy; does not
  enumerate all CVEs; does not certify reachability of all transitive
  deps.

## P_FULL_REALITY_VALIDATION

- **Buyer pain:** the whole claim → evidence → witness → falsifier →
  restore → CI gate → regression lock loop, end to end.
- **Deliverables:** all four packages above + buyer demo harness +
  operator-session ingestion + claim-to-code provenance graph.
- **Timeline:** ~8 weeks. **Price band:** flagship.
- **Proof artifact:** `demos/reality_validation_demo/run_demo.py`
- **Demo command:** `python demos/reality_validation_demo/run_demo.py`
- **Non-claims:** does NOT claim "production-ready" or "fully
  verified"; does NOT replace code review, security review, or domain
  expertise; does NOT generalise beyond the reality-loop contract.

---

## Closure rule

A package's pitch may be exactly its buyer pain, deliverables,
timeline, price band, proof artifact, demo command, and non-claims.
Anything beyond these belongs in a contract, not in this map.
