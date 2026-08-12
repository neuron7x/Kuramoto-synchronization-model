# POST_AUDIT_EXECUTION_REPORT.md

Execution of the post-audit hardening protocol (B1–B6 / T1–T10). Branch
`fix/honest-spine-and-truth-gates` on `main@e7709042`. Every gate below was run;
exact outcomes are recorded, including the honest negatives.

## 1. What was implemented

- **Semantic truth gate** — `scripts/ci/check_research_artifact_truth.py`. Scans
  `artifacts/runs/` and `research_lines/`; rejects schema-valid-but-fake
  artifacts (zero-hash + `PASS`, `HYPOTHESIS` + `PASS`, placeholder score + `PASS`,
  unmarked zero-data artifacts).
- **Semantic Ricci validator** — `validate_artifact_semantics()` in
  `tools/research/validate_ricci_artifact_schema.py` (schema **then** truth) plus a
  `--semantic` CLI flag.
- **Claim-to-artifact graph gate** — `scripts/ci/check_claim_artifact_graph.py`.
  Enforces that each contract's declared `state`/`tier` is backed by an artifact
  whose hashes and falsification status earn it, and that the referenced schema
  and artifact exist.
- **Non-vacuous manifest gate** — `--min-artifacts` / `--require-artifacts` on
  `scripts/ci/check_manifest_hashes.py`; a pass over 0 artifacts is `NOT_PROVEN`.
- **Release harness** — replaced the shape-only `ricci_schema` gate with
  `ricci_schema_semantic` and added a `research_artifact_truth` gate.
- **One-command proof** — `scripts/ci/prove_repo_integrity.sh`.
- **CI wiring** — the two new gates + semantic validation + gate tests run in
  `.github/workflows/research-integrity-gate.yml`.
- **Python matrix** — `pr-gate.yml` PyO3 `3.13 → 3.12` (inside `requires-python`).
- **Namespace policy** — three broken standalone shims repaired to
  fully-qualified local-src imports; `risk_factory` dropped its `TYPE_CHECKING`
  `src.*` import for `Any` (consistent with its importlib-only design).
- **Schema** — added an optional `artifact_role` (`evidence` | `placeholder`) so
  placeholders self-label honestly.

## 2. What was downgraded (honesty over fake completion)

- `ricci_microstructure_v1` stays **HYPOTHESIS / INSTRUMENTED**. No real L2 /
  order-book session exists, and the operationalised Ricci code runs on
  cross-asset return-correlation graphs, not microstructure. Promotion would
  require fabricating data — forbidden.
- The example artifact is an explicit `NOT_RUN`, `artifact_role: placeholder`
  with `score 0.0` (was a hand-typed `0.742` / `PASS` with a zero data hash).
- `MANIFEST_PROOF` is reported `NOT_PROVEN`: there is no real hash-pinned
  artifact graph yet.

## 3. Gates added (each fails-before / passes-after)

| Gate | Fails on |
| --- | --- |
| `check_research_artifact_truth.py` | a zero-hash artifact claiming `PASS` |
| `check_claim_artifact_graph.py` | a contract tier not backed by its artifact |
| `validate_artifact_semantics()` | schema-valid but semantically fake artifact |
| `check_manifest_hashes.py --min-artifacts 1` | proof mode over 0 artifacts |

## 4. Commands run

```
python scripts/ci/check_research_artifact_truth.py
python scripts/ci/check_claim_artifact_graph.py
python tools/research/validate_ricci_artifact_schema.py --semantic …
python scripts/ci/check_manifest_hashes.py            # default
python scripts/ci/check_manifest_hashes.py --min-artifacts 1
python scripts/check_python_matrix.py
python scripts/check_namespace_policy.py
python scripts/ci/check_claim_boundary.py
python scripts/count_invariants.py
pytest tests/ci tests/research_lines tests/unit/scripts/test_namespace_shims_importable.py
bash scripts/ci/prove_repo_integrity.sh
python tools/commit_acceptor/validate_commit_acceptor.py [--require-acceptor-for-code-change]
```

## 5. Commands that passed

- `check_research_artifact_truth.py` → exit 0 (after the artifact was marked a
  placeholder; it correctly exited 1 before).
- `check_claim_artifact_graph.py` → exit 0.
- `validate_ricci_artifact_schema.py --semantic` → exit 0 on the placeholder;
  exit 1 (9 violations) on a synthetic `0.742`/`PASS`/zero-hash fake.
- `check_python_matrix.py` → exit 0 (was exit 1).
- `check_namespace_policy.py` → exit 0 (was exit 1, 8 violations).
- `check_claim_boundary.py` → exit 0. `count_invariants.py` → `97`.
- `pytest` (truth + graph + manifest + ricci-schema + namespace-shim) → all pass.
- `bash scripts/ci/prove_repo_integrity.sh` → exit 0, `REPO_INTEGRITY: PROVEN`.
- `validate_commit_acceptor.py` schema + diff-binding → exit 0.

## 6. Commands that failed (by design or environment)

- `check_manifest_hashes.py --min-artifacts 1` → exit 1, `NOT_PROVEN`. **By
  design**: there is no real hash-pinned artifact yet. The proof script reports
  this honestly and still proves the rest.
- `tests/tools` (release-packaging harness) is **excluded** from the integrity
  proof. It needs `pydantic` / `cryptography` / `httpx`, so including it would
  break the clean-clone, one-command guarantee — and it is release machinery,
  not lie-prevention. It keeps its own CI job. The proof's `[8/8]` step runs
  only the integrity surface (`tests/ci` + `tests/research_lines`), which a fresh
  clone passes with the sci-core stack alone. Verified end-to-end:
  `git clone … && pip install numpy scipy pandas networkx pyyaml jsonschema pytest
  && bash scripts/ci/prove_repo_integrity.sh` → `REPO_INTEGRITY: PROVEN`, exit 0.

## 7. Remaining honest UNKNOWNs

- **Coverage gate** (`fail_under = 98`): not measured here; needs the full lock
  install (`torch`, `jax`). Status: UNKNOWN.
- **Real Ricci empirical validity**: UNKNOWN by construction — no committed L2
  data. The repo now *gates* against pretending otherwise.
- **CI wall-clock** for `research-integrity-gate` with the new steps: expected
  well under its 25-min budget, but only the live run on GitHub confirms it.

## 8. Final next command for the user

```bash
bash scripts/ci/prove_repo_integrity.sh
```

Expected: exit 0, ending with `REPO_INTEGRITY: PROVEN` and a single honest
`MANIFEST_PROOF: NOT_PROVEN` line. The repository is reproducibility- and
claim-integrity-proven; it is **not** claimed research-valid for
`ricci_microstructure_v1`, and will refuse to be until a real, hash-pinned,
falsified artifact exists.
