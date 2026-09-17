# ECP-AS v0.1 — Epistemic Control Plane for Autonomous Science

ECP-AS is a domain-independent runtime gate extracted from GeoSync governance mechanisms.
It separates **research generation** from **epistemic authorization**.

Core invariant:

> Agents may generate, test, and attack hypotheses. They may not strengthen a claim's epistemic status unless the admission controller authorizes the transition.

## Iteration 1 vertical slice

Implemented:
- evidence-carrying claim model;
- explicit adjacent state machine;
- promotion contracts;
- fail-closed admission controller;
- P/C/A/I oracle independence plus lineage-overlap rejection;
- immutable negative-evidence objects;
- deterministic promotion certificates;
- authoritative hash-chained event ledger with tamper detection;
- state reconstruction from ledger rather than agent-supplied maturity;
- explicit degradation into falsified/stale/OOD/conflicted terminal states;
- append-only negative-evidence resolution events;
- typed acyclic dependency graph with dependency-scoped invalidation sets;
- deterministic structured claim-contract compiler;
- falsifier-first experiment ranking;
- GeoSync legacy maturity adapter;
- executable tests.

Not yet claimed:
- complete semantic claim compiler;
- graph-scale invalidation propagation;
- cryptographic append-only ledger;
- LLM-independent semantic equivalence proofs;
- cross-domain empirical validation;
- demonstrated reduction in unsafe-promotion rate.

Those are future proof obligations, not completed features.
