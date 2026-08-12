<!-- SPDX-License-Identifier: MIT -->
# Descriptor-to-Physics Promotion Policy

GeoSync computes many **descriptors**: Ricci curvature over a *correlation
graph*, phase-coherence statistics, market *proxies*, simplicial-topology
features. A descriptor is a number computed over data. It carries no automatic
licence to be called a physical law, the physical phase of a system, market
consensus, a predictor, or alpha.

The danger this policy firewalls is **silent promotion**: prose (in docs or in
claim-bearing code docstrings) that quietly asserts a descriptor *is* — or
*measures*, *proves*, *predicts* — the physical / causal / consensual /
tradable thing it merely correlates with. Silent promotion is how a
descriptor-tier artifact leaks into a physics or prediction claim without
passing the evidence ladder.

## Where this sits in the claim machinery

This policy composes with — it does not duplicate — the existing gates:

| Gate | Firewalls | Surface |
| --- | --- | --- |
| `scripts/ci/check_claim_boundary.py` | product-category drift (re-selling GeoSync as a live-venue or alpha-generating product) | docs + indicator code |
| `FORBIDDEN_CLAIMS.md` + `scripts/ci/check_claims.py` | *status* wording and claim-registry evidence | `docs/CLAIMS.yaml` |
| `bibliography-claim-gate` | claim ↔ source ↔ tier matrix | `CLAIMS.md` / `BIBLIOGRAPHY.md` |
| **this policy** + `tools/claims/check_descriptor_promotion.py` | **ontological promotion** (descriptor → physics/prediction/trading) | docs + indicator code |

Provenance tiers use the canonical IERD vocabulary from `docs/CLAIMS.yaml`
(`ANCHORED` / `EXTRAPOLATED` / `SPECULATIVE` / `UNKNOWN`). A descriptor whose
evidence is `EXTRAPOLATED` may *not* be written as if it were the
`ANCHORED` physical quantity; this firewall enforces that at the sentence
level.

## The six forbidden promotions

A promotion fires only when a **descriptor token**, a **promotion verb**, and a
**target token** co-occur on one normalised line. Each rule has a stable
`rule_id` for `file:line` reporting.

### 1. `descriptor-to-physical-law`
A descriptor / metric / indicator / statistic / feature asserted to *be* a
physical law, a law of nature/physics/markets, or a fundamental law.

- Forbidden: *"This curvature descriptor **is a physical law** of markets."*
- Allowed: *"This curvature descriptor is **not** a physical law; it is an
  `EXTRAPOLATED` correlate."*

### 2. `proxy-phase-to-physical-phase`
A proxy / estimated / computed phase asserted to *be* (equal, measure) the
physical / true / real / actual phase of a system.

- Forbidden: *"The proxy phase **equals the physical phase** of the asset."*
- Allowed: *"The proxy phase is **not** the physical phase; it is a Hilbert
  estimate over a price descriptor."*

### 3. `correlation-ricci-to-microstructure-ricci`
Ricci curvature on a *correlation graph* asserted to *be* the L2 /
order-book / microstructure Ricci curvature. These are different objects:
one is geometry over a sample-correlation matrix, the other is geometry over a
limit-order-book microstructure. Conflating them is the canonical Ricci
promotion error.

- Forbidden: *"Correlation-graph Ricci **is the L2 microstructure Ricci**."*
- Allowed: *"Correlation-graph Ricci is a descriptor, **not** L2
  microstructure Ricci; the microstructure result lives in a separate
  `EXTRAPOLATED` claim."*

### 4. `coherence-to-market-consensus`
A coherence descriptor (phase coherence, PLV, Kuramoto order parameter)
asserted to *be* / *measure* market consensus, collective belief, or market
agreement.

- Forbidden: *"Phase coherence **measures market consensus** directly."*
- Allowed: *"Phase coherence **does not imply** market consensus; it is a
  synchronisation statistic over price phases."*

### 5. `topology-to-predictive-validity`
A topology descriptor (topology, simplicial feature/complex, persistent
homology, Betti numbers) asserted to have predictive validity, or to predict /
forecast price / market / return / direction, or to be an out-of-sample edge.

- Forbidden: *"This topology feature **predicts the price** next bar."*
- Allowed: *"This topology feature **does not predict** the price; predictive
  validity is `UNKNOWN`."*

### 6. `feature-to-alpha`
A feature / descriptor / indicator asserted to *be* alpha, a tradable/trading
edge, excess return, or a profitable strategy.

- Forbidden: *"Each feature **is alpha** you can trade."*
- Allowed: *"A feature is **not** alpha; promotion to a tradable edge requires
  the multi-session real-data ladder in `FORBIDDEN_CLAIMS.md`."*

## What is explicitly *not* a promotion

The checker's negation guard demotes any line carrying a negation or
proxy-disclosure cue (`not`, `never`, `cannot`, `does not`, `without`,
`proxy for`, `surrogate for`, `descriptor for`, `not a claim`, …) from
promotion to **descriptor discipline**. Honest negations and proxy disclosures
are the *desired* style and always pass. Provenance-tiered hedges
(`EXTRAPOLATED`, `SPECULATIVE`) on the same line as a descriptor are not a
promotion.

## Scope, exclusions, and the allowlist

- **Scanned surface**: top-level `*.md`, the `docs/**` tree, and the
  claim-bearing indicator modules in `CODE_SURFACE_FILES`.
- **Excluded records** (they quote banned phrasing by design):
  `docs/archive/`, `docs/audit/`, `docs/adr/`, `docs/releases/`,
  `docs/claims/` (this policy), and the ledger files `FORBIDDEN_CLAIMS.md`,
  `CLAIMS.md`, `PRODUCT_CATEGORY.md`.
- **Allowlist**: `.github/descriptor_promotion_allow.json`. A line that
  pattern-matches a promotion but is genuinely mechanism or a quotation gets a
  reasoned entry. Stale entries (no longer matching anything) fail the gate so
  the allowlist stays an honest ledger.

## Relaxation discipline

If a forbidden promotion pattern must ever be relaxed, the reason is documented
**in this file** (not in a commit message): add a dated subsection under a
`## Relaxations` heading naming the `rule_id`, the evidence that justifies the
relaxation, and the provenance tier that now backs the previously-forbidden
phrasing. A relaxation without recorded evidence is itself a silent promotion.

## Running locally

```sh
python tools/claims/check_descriptor_promotion.py
pytest -q tests/tools/test_descriptor_promotion_firewall.py
```

Exit `0` means no unreviewed promotions on the canonical surface; exit `1`
prints each offending `file:line` with its `rule_id`.
