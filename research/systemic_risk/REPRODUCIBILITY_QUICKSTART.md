# Reproducibility Quick-Start (≤ 400 words)

> Closes audit task 26. External auditor: this is the minimum you
> need to reproduce a canonical-seven evaluation. The full
> contract is in [REPRODUCIBILITY.md](REPRODUCIBILITY.md).

## 1. Environment

```bash
git clone https://github.com/neuron7xLab/GeoSync.git
cd GeoSync
git checkout <commit_sha>          # frozen sha from RunManifest
python -m pip install -r requirements.txt
```

Python ≥ 3.11. NumPy ≥ 2.3. No JAX dependency.

## 2. Smoke test (synthetic, no real data)

```bash
python -m research.systemic_risk.cli evaluate \
    --claim-id CLAIM_AUDIT \
    --data synthetic \
    --seed 42 \
    --n-banks 30 \
    --n-days 60
```

Output is a single JSON document on stdout: `tier_name`,
`last_action`, and the eight firewall gate outcomes.

## 3. Replication contract

Every run promoted to ≥ `MEASURED` must:

1. Carry a `RunManifest` with `commit_sha`, `git_dirty=False`,
   `seed`, `config_hash`, `package_versions`.
2. Pass `compare_run_outputs(...)` against a fresh rerun on a
   clean checkout of the same `commit_sha`.
3. Record the comparison's `ReplicationOutcome` in the claim's
   evidence ledger.

`matched=False` → KILL → REJECTED (terminal).

## 4. Pre-registration

Copy `PRE_REGISTRATION_TEMPLATE.md` to `preregs/CLAIM_<id>.md`
**before** touching data. Sha256 it; the next
`RunManifest.config_hash` binds it. Post-hoc edits → INVALIDATE.

## 5. Test suite

```bash
python -m pytest tests/research/systemic_risk/ -q
```

Expected: 532+ passed, 0 failed. Property-based tests via
Hypothesis; ~30 s on first run.

## 6. Static analysis

```bash
python -m mypy --strict research/systemic_risk/
python -m ruff check research/systemic_risk/
python -m black --check research/systemic_risk/
```

All three must report zero diagnostics.

## 7. Reading order

`CANON.md` → `THEORY_PROOFS.md` → `PROTOCOL.md` →
`LIMITATIONS.md` → `REPRODUCIBILITY.md`. Order matches the
canonical seven pipeline (firewall → leakage → ladder → capsule
→ ledger → death → FSM).

## 8. Real data

The CLI's `--data real` path is **not yet wired**. e-MID / ECB
MMSR ingest is documented in `LIMITATIONS.md` § 4 (data licence
constraints, manifest schema requirements, daily SHA256
verification protocol).

---

Word count: ≈ 290 (target ≤ 400).
