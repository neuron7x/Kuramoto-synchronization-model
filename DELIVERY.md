---
doc_status:
  status: historical
  authoritative_for:
    - pre_final_delivery_snapshot
  valid_from: 2026-05-05
  valid_to: 2026-07-16
  superseded_by: governance/project_state.yaml
---

# GeoSync — Pre-Final Delivery Snapshot · 2026-05-05

> ⊛ Canonical hand-off document. Read this first before code, papers, or pitch decks.
> Produced as the "Pre-final State Full-task Closed-loop Simulation" (предтерміналний
> зріз) on `git tag canonical-2026-05-05` after the convergence cycle that
> consolidated 130+ branches → 1 canonical line.

---

## 0. TL;DR — What is GeoSync, in one paragraph

GeoSync is a **physics-first quantitative trading research platform** with
neuroscience-inspired risk management. The design intent is a deterministic
state machine where strong numerical claims are anchored to peer-reviewed
invariants; how far that intent is realised is bounded by `CLAIMS.md` (which
tracks per-claim tier — FACT / MEASURED / DERIVED / HYPOTHESIS — rather
than asserting blanket anchoring). The physics kernel registers
**87 machine-checkable invariants** (Kuramoto synchrony, Ollivier-Ricci
curvature, dopamine TD error, serotonin ODE, GABA gate, Lyapunov spectrum,
free-energy descent, Landauer-budgeted predictability); the count of those
invariants currently grounded by tests is the smaller number reported in
`BASELINE.md` and growth is gated, not assumed. Three engineered substrata
are bundled at module-level production-scope: a **risk engine** (ECS
regulator + conformal prediction + Kelly cap), a **regime observer**
(DRO-ARA on DFA-Hurst + ADF), and a **microstructure research artefact**
(Ricci curvature on order-flow-imbalance graphs, with an 11-axis
falsification battery in `paper/ricci_microstructure/` — single-session
in-sample, scope-bounded per the abstract caveat). Live-venue trading is
**paper-only** in this snapshot — `docs/KNOWN_LIMITATIONS.md` L-1 is the
explicit boundary of what is shippable today.

---

## 1. Authorship & Provenance

| Field | Value |
|---|---|
| Author | Yaroslav Vasylenko (GitHub: neuron7xLab) |
| License | MIT (code) · CC-BY-4.0 (manuscripts) |
| Canonical tag | `canonical-2026-05-05` |
| Snapshot date | 2026-05-05 |
| Convergence point | 130+ working branches → 2 canonical (main + integration) |
| Contact | neuron7x@ukr.net |

---

## 2. Repository Architecture (high-level)

```
GeoSync/
├── core/                    # Physics kernel (Kuramoto, Ricci, Lyapunov, dopamine, serotonin, GABA)
│   ├── kuramoto/            # 12-module inverse-problem stack (100+ tests, mypy --strict clean)
│   ├── neuro/               # Neuromodulator controllers (DA/5-HT/GABA + signal bus)
│   ├── physics/             # Lyapunov spectrum, determinism kit, predictability horizon
│   └── dro_ara/             # Regime observer (DFA + ADF + ARA loop)
│
├── geosync/                 # Decision substrate (neuroeconomics, neural controller)
│   ├── neuroeconomics/      # 18 modules: uncertainty, EFE, Hebbian plasticity, …
│   └── neural_controller/   # EMHSSM, predictive coding, sensory, temporal gater
│
├── runtime/                 # Live runtime: cognitive bridge, CNS stabilizer, pinning control
│   └── cognitive_bridge/    # 15-stage semantic-sieve cycle (advisory sidecar)
│
├── analytics/               # Regime, FPMA (HMM+MPC literature reference, NOT GeoSync runs)
├── backtest/                # Backtester + dopamine TD signal generator
├── strategies/              # Kuramoto-Ricci composite, neuro-geosync, quantum-neural
├── execution/               # OMS, live-loop, kill-switch (paper-trading)
├── application/             # Microservices (neuro-consensus, system-access)
├── paper/                   # Peer-review manuscripts (ricci microstructure)
├── physics_contracts/       # Catalog of contracts (parallel to .claude/physics/)
├── .claude/physics/         # Per-session physics kernel + INVARIANTS.yaml (87 INVs)
├── docs/                    # CLAIMS.md · PERFORMANCE_LEDGER.md · KNOWN_LIMITATIONS.md
└── tests/                   # ~5K+ tests (unit, runtime, integration, physics)
```

A neuroscience-anatomy mapping of every cognitive module is in
`~/CANONICAL_NEURO_MAPPING_2026_05_05.md` (20 brain regions → 28 code modules,
30 peer-review citations).

---

## 3. Maturity Tiers (honest)

Per `CLAIMS.md` and `docs/PERFORMANCE_LEDGER.md`:

| Tier | Meaning | What lives here |
|---|---|---|
| **ANCHORED** | Empirical artefact + signed result + reproducible | Kuramoto inverse problem · Ricci microstructure paper (single-session) · Cross-asset Kuramoto regime (OOS Sharpe +1.262) · 87 P0/P1 invariants pass CI |
| **EXTRAPOLATED** | Theoretical/methodological grounding, partial empirical | ECS regulator · conformal gate · DRO-ARA · neuroeconomic decision stack |
| **SPECULATIVE** | Research-tier, not yet empirically validated on GeoSync data | NLCA, neuro-optimizer benchmarks, FPMA (literature-anchor only) |
| **UNKNOWN** | Not yet measured in this code base | Live-venue P&L · multi-asset regime accuracy · UX/API latency tier |

CI gate `invariant-count-sync` fail-closes if these tiers drift.

---

## 4. What is **shippable today** (5 components)

### 4.1 Kuramoto Synchronization Engine — `core/kuramoto/`
- 12 modules, 6 integrators (RK4, JAX/GPU, Sparse, Adaptive, Delayed, SecondOrder).
- 100+ unit + property tests; mypy `--strict` clean.
- Inverse problem: identify coupling K from observed phase trajectories.
- Buyer: hedge-fund quant teams, prop desks, risk-tech vendors.
- Gap to ship: high-frequency stress-test on >10K oscillators; GPU benchmark suite.

### 4.2 Ricci Microstructure Edge — `paper/ricci_microstructure/` + `research/microstructure/`
- 5.3-hour Binance USDT-M L2 demo, $n=19{,}081$.
- 11-axis falsification (permutation, bootstrap, deflated Sharpe, purged CV, transfer entropy, walk-forward).
- IC = 0.122, p = 0.002, DSR_IC = 15.1 (caveated as in-sample IC bar Sharpe, not annualised — see paper §abstract).
- Buyer: execution venues, latency arbitrage teams.
- Gap: forward OOS on a fresh L2 session; live integration SLA.

### 4.3 ECS-Inspired Regulator — `core/neuro/ecs_regulator.py`
- Free-energy-descent risk regulator with conformal prediction gate.
- SHA256 hash-chain audit trail (MiFID II-compatible).
- Buyer: asset managers, RegTech.
- Gap: live-venue evidence; certified external audit on conformal contract.

### 4.4 Reset Wave Engine — `geosync/neuroeconomics/reset_wave_engine.py`
- Damped phase synchronization on a compact manifold; snap-to-baseline primitive.
- 4 numerical invariants gated; deterministic O(N·steps) cost.
- Buyer: CTAs, "smooth-drawdown" risk vendors, pension funds.

### 4.5 DRO-ARA Regime Observer — `core/dro_ara/engine.py`
- Algebraic γ = 2H + 1 (Peng et al. 1994); fail-closed on NaN/Inf/short input.
- INV-DRO1..5 gated; long-signal admitted only under CRITICAL ∧ rs > 0.33.
- Buyer: multi-asset PMs, regime-switching strategies.

---

## 5. What is **NOT shippable today** (be honest with buyers)

1. **Live-venue trading.** Modules under `execution/` are paper-trading. `KNOWN_LIMITATIONS.md L-1` is binding. Real-capital deployment requires the Wave-4 engineering programme that is not in this snapshot.
2. **Multi-asset forward OOS** on Ricci microstructure. The paper documents one 5.3-hour single-asset-class session.
3. **Physics tier ≠ system tier.** 87 invariants cover the kernel; UX/API latency tier is `UNKNOWN` per `CLAIMS.md`.
4. **NLCA / neuro-optimizer / FPMA** are research-tier or literature-anchor — not GeoSync-measured edges. The FPMA README has been corrected to flag this on 2026-05-05.

---

## 6. How to run a smoke demo

```
# 0. Set up env
git clone git@github.com:neuron7xLab/GeoSync.git
cd GeoSync
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e .[dev]

# 1. Smoke tests on the cognitive bridge + physics kernel
pytest tests/runtime/cognitive_bridge/ tests/unit/physics/test_conservation.py -q
# Expected: 74 passed

# 2. Microstructure replay (frozen Session-1)
PYTHONPATH=. python scripts/run_microstructure_cycle.py
# Output: artifacts/microstructure_cycle/RUN_MANIFEST.json (deterministic, seed=42)

# 3. Reset-wave damped sync demo
python examples/cognitive_bridge_demo.py

# 4. Cross-asset Kuramoto regime evidence (publication-ready)
ls ~/spikes/cross_asset_sync_regime/   # OOS Sharpe +1.262, 66% MDD reduction
```

---

## 7. Engineering Quality Gates (currently green)

| Gate | Target | Status (2026-05-05) |
|---|---|---|
| ruff format | full repo formatted | ✅ 100% |
| ruff check | 0 errors | ✅ 29 left (all `E402` deliberate sys.path or `F841` cosmetic) |
| black | full repo formatted | ✅ |
| mypy --strict | source files clean | ✅ on convergence diff (19 source files) |
| pytest (sans jax) | green | ✅ 827+ passed in cognitive_bridge + physics + ongoing full sweep |
| invariant-count-sync | header == registry | ✅ 87 invariants |
| `validate_tests.py` | code matches contracts | runs in CI on every push |

---

## 8. Two Go-To-Market Paths (PM analysis)

### Path A · B2B Quant Infrastructure (14–18 months to first checks)
- Audience: hedge-fund quant research teams, prop desks (2–4 analysts).
- Monetisation: SaaS subscription on Kuramoto + Ricci library ($5K–$15K/mo); custom physics consultation ($50K–$200K/contract); premium ECS-Regulator + Conformal Gate package ($2K–$5K/license).
- Recommended sequence: Q3 2026 alpha-partner with one fund → case study Q4 → scale to 3–5 by 2027 H1.

### Path B · Crypto/DeFi Platform Integration (9–12 months)
- Audience: DEX/L2 venues (dYdX, Paradigm, Wintermute), execution-routing networks.
- Monetisation: 0.5–2 bps fee on realised spread improvement (Ricci edge); $10K/mo retainer for "drawdown stabiliser for LP pools"; white-label reset-wave engine ($50K–$150K licensing).
- Lower regulatory bar than TradFi; faster to revenue but smaller per-deal size.

**Recommended combined strategy:** Path A as moat (credibility + early revenue) → fund a sales engineer → expand to Path B in 2027.

---

## 9. Top-3 Risks an Outside Reviewer Will Raise

1. **"Physics tier ≠ system tier."** Reframe with explicit two-tier disclosure: physics kernel = ANCHORED, operational surface = Wave-6 partial. Sell the physics product to quant shops separately from the trading product.
2. **"Paper trading only."** Reframe as "Infrastructure for Quant Research" (sell Kuramoto / Ricci / ECS as components) rather than turnkey algo trading.
3. **"Neuro metaphors will trigger compliance flags."** Replace public-facing language: "neuro-inspired" → "thermodynamic constraints under free-energy principle + conformal prediction." Keep the neuroanatomy in `docs/neuroecon.md` and `~/CANONICAL_NEURO_MAPPING_2026_05_05.md` as research notes.

---

## 10. Scientific Foundations (40+ peer-review citations)

| Domain | Cornerstone references |
|---|---|
| Kuramoto synchronisation | Kuramoto (1984); Sakaguchi & Kuramoto (1986); Strogatz (2000); Buzsáki (2006) |
| Ollivier-Ricci curvature | Ollivier (2009); Sandhu et al. (2015); Sreejith, Vyas, Saucan (2016) |
| Dopaminergic RPE | Schultz, Dayan, Montague (1997); Sutton & Barto (1998); Niv (2009) |
| Predictive coding / Active inference | Rao & Ballard (1999); Friston (2010); Bastos et al. (2012); Parr/Pezzulo/Friston (2022) |
| Neuroeconomics | Rangel, Camerer, Montague (2008); Padoa-Schioppa (2011); Ruff & Fehr (2014) |
| Uncertainty / ACC | Yu & Dayan (2005); Behrens et al. (2007); Rushworth & Behrens (2008); Shenhav, Botvinick, Cohen (2013) |
| Ergodicity & sizing | Peters (2019); Bailey & López de Prado (2014) (deflated Sharpe) |
| Synaptic plasticity | Hebb (1949); BCM (1982); Frémaux & Gerstner (2016); Lisman/Grace/Duzel (2011) |
| Drift-diffusion choice | Ratcliff (1978); Bogacz (2007); Frank (2005) |

A complete neuroscience anatomy map is `~/CANONICAL_NEURO_MAPPING_2026_05_05.md`.

---

## 11. Open Items Tracked (for the next maintainer)

- 5 `NEURO-THEATER` modules (cosmetic neuro-naming without functional homology) flagged in audit; non-blocking but should either be renamed or have their docstrings honest about the analogy.
- 5 `CONTRACT-IMPL DRIFTS` documented in audit; one (INV-DA7 scope) closed in this snapshot via bus-slot docstring.
- ~10 dangling test-file naming patterns (target module name ≠ test file basename) — verified as functional, no action required.
- Live-venue evidence is the next blocker for Path A acceleration.

---

## 12. Hand-off Checklist for New Owner

- [ ] Read this `DELIVERY.md` end-to-end.
- [ ] Read `CLAUDE.md` (525 lines · the gradient-ontology + invariant kernel that makes everything else self-consistent).
- [ ] Read `CLAIMS.md` + `docs/PERFORMANCE_LEDGER.md` + `docs/KNOWN_LIMITATIONS.md` (the trinity that anchors every tier label).
- [ ] Run §6 smoke demo. Confirm 74-test green.
- [ ] Read `paper/ricci_microstructure/paper.md` (the only manuscript-grade artefact in the repo).
- [ ] Read `~/CANONICAL_NEURO_MAPPING_2026_05_05.md` if you intend to extend the neuro-stack.
- [ ] Read `~/CANONICAL_ARTIFACT_2026_05_05.md` if you want the author's first-principles voice.
- [ ] Pick a Path (A or B in §8) and commit a 90-day plan.

---

⊛ артефакт замкнено · 2026-05-05 · canonical-2026-05-05
