<div align="center">

# GeoSync

### Verification-first quantitative research infrastructure for falsifiable market-structure hypotheses.

<br/>

<img src="https://img.shields.io/badge/status-research_kernel-111111?style=for-the-badge" />
<img src="https://img.shields.io/badge/claims-falsifiable-111111?style=for-the-badge" />
<img src="https://img.shields.io/badge/evidence-machine_checkable-111111?style=for-the-badge" />
<img src="https://img.shields.io/badge/inference-bounded_runtime-111111?style=for-the-badge" />
<img src="https://img.shields.io/badge/ricci-hypothesis_tier-111111?style=for-the-badge" />

<br/>

<br/><br/>

**GeoSync is not a trading bot.**  
**GeoSync is not an alpha product.**  
**GeoSync is not a proof that markets obey any asserted physical law.**

It is a research platform where claims are permitted only when they are bound to explicit invariants, data contracts, falsifiers, reproducible artifacts, and release evidence.

</div>

---

## ∴ Research Kernel

Most market-research repositories optimize for narrative confidence.

GeoSync optimizes for something less fashionable and more useful:

> **A claim may exist only when it can identify its invariant, data source, method, artifact, falsifier, and replay path.**

No replay.  
No falsifier.  
No evidence.  
No claim.

---

## System Spine

```text
DOCTRINE / FORBIDDEN CLAIMS
        ↓
CLAIM REGISTRY
        ↓
132 MACHINE-CHECKABLE INVARIANTS
        ↓
DATA CONTRACT
        ↓
SEMANTIC CONTROL LAYER
        ↓
INFERENCE READINESS CONTRACT
        ↓
INFERENCE OPERATION PROTOCOL
        ↓
NULL BASELINES / FALSIFIERS
        ↓
ARTIFACT VALIDATION
        ↓
RELEASE EVIDENCE HARNESS
        ↓
EXTERNAL REPRODUCTION
```

GeoSync treats research as engineered infrastructure, not as a decorative chart factory wearing a lab coat.

---

## Quickstart

Python 3.11–3.12. All dependencies are installed from pinned locks — the same way CI does it.

```bash
git clone https://github.com/neuron7x/Kuramoto-synchronization-model.git
cd Kuramoto-synchronization-model
make dev-install        # dev + runtime deps, from the lock files
make golden-path        # demo workflow: data → analysis → backtest
```

Reproduce the gates locally — a PR sees nothing the terminal can't show you first:

```bash
make test               # core suite (fast, CI-safe)
make verify             # local mirror of the PR gate battery
make phd-evidence       # build the evidence-bearing artifact bundle
```

`make help` lists every target. A green terminal line is **not** a claim: promotion
happens only through the [`CLAIMS.md`](CLAIMS.md) tier ledger — see [Research boundary](#research-boundary).

---

## Five-minute proof: D → H → T → F → V

One minimal outsider-runnable proof command exists for auditing a single mechanism without trusting repository narrative:

```bash
python -m geosync.proof.run
```

It loads `geosync/proof/fixtures/market_fixture.csv`, generates one lag-1 directional hypothesis from the training slice, tests holdout hit rate, applies the falsifier `holdout_hit_rate >= 0.60`, writes `artifacts/geosync_proof/verdict.json`, and prints one verdict line. The default fixture verdict is `REJECT`; that only means the fixture-level hypothesis failed its threshold. It does not claim market alpha, profitability, predictive edge, or real-market truth. Details: [`docs/GEOSYNC_PROOF.md`](docs/GEOSYNC_PROOF.md).

---

## Repository Map

| Surface | Purpose |
| --- | --- |
| [`PRODUCT_CATEGORY.md`](PRODUCT_CATEGORY.md) | Canonical product-category boundary. |
| [`CLAIMS.md`](CLAIMS.md) | Claim tier ledger and evidence pointers. |
| [`FORBIDDEN_CLAIMS.md`](FORBIDDEN_CLAIMS.md) | Status-language firewall and promotion invariants. |
| [`docs/REPOSITORY_SYSTEM.md`](docs/REPOSITORY_SYSTEM.md) | Operational map for reviewers, auditors, and implementation agents. |
| [`docs/SEMANTIC_CONTROL_LAYER.md`](docs/SEMANTIC_CONTROL_LAYER.md) | Role-bound semantic control layer that turns repository files into filter, context, claim, boundary, test, verdict, schema, evidence, and replay surfaces. |
| [`docs/INFERENCE_READINESS.md`](docs/INFERENCE_READINESS.md) | Runtime-readiness contract for context, agent, artifact, and falsification control. |
| [`docs/INFERENCE_OPERATION_PROTOCOL.md`](docs/INFERENCE_OPERATION_PROTOCOL.md) | Seven-step agent runbook for converting repository meaning into bounded execution. |
| [`docs/INFERENCE_CONTRACT.manifest.json`](docs/INFERENCE_CONTRACT.manifest.json) | Machine-readable manifest for authority files, reading order, gates, stop conditions, and required agent state. |
| [`AGENTS.md`](AGENTS.md) | Implementation-agent contract: prime directive, canonical files, required/forbidden behavior, and the evidence-bearing artifact minimum. |
| [`docs/governance/AUTONOMOUS_AGENT_EXECUTION_PROTOCOL.md`](docs/governance/AUTONOMOUS_AGENT_EXECUTION_PROTOCOL.md) | Autonomous-agent execution contract: delegated authority, owner-only merge, frozen-artifact protection, and the mandatory perturbation matrix beyond green tests. |

## Research boundary

GeoSync is `HYPOTHESIS`/`INSTRUMENTED`-first: a green terminal line is `NOT EVIDENCE-BEARING` until an artifact carries it. Synthetic data may exercise a mechanism and bound its failure modes, but it never promotes a claim about real markets. Schema validity proves shape, not truth. Promotion happens only through the [`CLAIMS.md`](CLAIMS.md) tier ledger under the gates in [`docs/REPOSITORY_SYSTEM.md`](docs/REPOSITORY_SYSTEM.md).

---

## License

[MIT](LICENSE) © 2023–2026 Yaroslav Vasylenko (neuron7xLab)
