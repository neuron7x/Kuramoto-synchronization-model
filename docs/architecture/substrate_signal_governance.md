# Substrate Signal Governance — Formal Specification v1.1

> **Design Thesis:** a signal is admissible only when its error witnesses remain independent under adversarial audit.

## 1. Scope

This specification formalizes the behavior of:

- `agent/substrate_oracle.py`
- `core/io/parquet_compat.py`
- `research/askar/production_readiness_checkpoint.py`
- `research/askar/sentiment_node_ricci_graph.py`

It defines invariants, value function, state semantics, and deterministic artifacts.

---

## 2. Value Function (Функція цінностей)

Let `S` be a candidate signal process and `A` the audit process.

\[
\mathcal{V}(S) = \begin{cases}
1, & \text{if } \text{truthful}(S) \land \text{replayable}(A) \land \text{non-fabricated}(S)\\
0, & \text{otherwise}
\end{cases}
\]

Where:

- **truthful**: failures are explicit (`REJECT`, `DORMANT`, `ABORT`) and never masked.
- **replayable**: decisions are serialized and hashed (`SHA256`) deterministically.
- **non-fabricated**: no fallback path can emit a synthetic positive verdict.

---

## 3. Formal Invariants

| ID | Invariant | Enforcement |
|---|---|---|
| INV-PQ-001 | If no parquet engine exists, execution must fail deterministically | `ParquetEngineUnavailable` |
| INV-SO-001 | Any NaN in substrate payload => immediate `ABORT` | `evaluate_substrate` |
| INV-SO-002 | Stale feed (`>30m`) => `BLOCK` | `evaluate_substrate` |
| INV-SO-003 | Unknown schema => `QUARANTINE` | `evaluate_substrate` |
| INV-SO-004 | `OHLC_ONLY` cannot claim precursor status | `SUBSTRATE_DEAD_OHLC_ONLY` |
| INV-SR-001 | Sentiment orthogonality gate must pass before graph usage | `orthogonality_gate` |
| INV-SR-002 | Sentiment must use train-frozen z-score | `build_sentiment_node` |
| INV-SR-003 | Randomized validation uses fixed `seed=42` | permutation test |

---

## 4. Deterministic Artifact Contract

### 4.1 Substrate Oracle

- Output: `action_intent.json`
- Digest: `action_intent.sha256`
- Exit codes:
  - `0` healthy transition / non-fatal block
  - `1` fatal invariant violation (`NAN_ABORT`)
  - `2` dead substrate / unrecoverable gating

### 4.2 Sentiment Ricci

- Output: `results/sentiment_node_verdict.json`
- If parquet backend missing: output must still be produced with `FINAL = REJECT`.

### 4.3 Production Readiness Checkpoint

- Output trio:
  - `results/prod/validation_verdict.json`
  - `results/prod/action_intent.json`
  - `audit/prod/run_hash.sha256`

---

## 5. Operational Semantics

### 5.1 Substrate Type Classifier

Header features are mapped to substrate classes:

1. If `ofi` or any depth/book-level key exists => `MICROSTRUCTURE`
2. Else if `bid` and `ask` are both present => `BID_ASK`
3. Else if OHLC keys exist => `OHLC_ONLY`
4. Else => `UNKNOWN`

### 5.2 Governance Decision

`decision := f(schema, freshness, NaN)` with strict priority:

1. `NaN` check
2. `stale` check
3. `schema` check
4. capability check (`OHLC_ONLY` vs microstructure)

This ordering is non-commutative by design.

---

## 6. Aesthetic Principles (Естетика та елегантність)

1. **Single-source invariants**: one meaning per rule.
2. **Symmetric failure semantics**: every failure has reason code + artifact.
3. **Minimal surprise**: deterministic defaults, fixed seed, explicit rejection.
4. **Audit-first style**: machine-readable outputs before narrative interpretation.

---

## 7. Extension Surface

Future tasks (OFI, regime, lifecycle, gamma-oracle) must integrate by implementing:

- `deterministic_artifact()`
- `invariant_registry()`
- `reason_code_taxonomy()`
- `replay_hash()`

No module can be promoted to production without these four interfaces.

---

## 8. Review Checklist

- [ ] Does module emit deterministic JSON artifacts?
- [ ] Are failures explicit and non-fabricating?
- [ ] Is SHA256 replay hash generated from sorted JSON?
- [ ] Are orthogonality and leakage gates measurable?
- [ ] Can reviewer reproduce verdict from same input?

If any checkbox fails => module remains `DORMANT`.
