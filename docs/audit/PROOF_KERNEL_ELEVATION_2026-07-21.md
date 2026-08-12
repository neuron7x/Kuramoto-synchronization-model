# Executable claims-governance kernel — elevation to leading-industrial quality

The strongest, most original part of GeoSync is the **executable governance of scientific claims**:
`claim → evidence-tier → source → method → artifact → falsifier → verdict`, where an external
auditor can run the pipeline and get a `REJECT` **without trusting the author**. This document is
the honest assessment + roadmap to take that kernel to a leading-industrial bar, and records the
first increment.

## Honest current state (verified, not described)
| component | state |
|---|---|
| `python -m geosync.proof.run` (D→H→T→F→V) | **works** — deterministic, self-contained, emits a machine-readable `verdict.json`; the fixture mechanism honestly returns `REJECT` (holdout 0.0 < 0.60). |
| `docs/CLAIMS.yaml` (27 claims) | real registry: `id / tier(ANCHORED) / evidence_paths / falsifier.test_id`. |
| `FORBIDDEN_CLAIMS.md` + `check_cff_claims`/`check_claims` | marketing-overreach blocked. |
| falsifier→node binding | **enforced** (`check_falsifier_nodes.py`, MR!37): every `falsifier.test_id` must resolve to a collectible pytest node. |
| scattered ecosystem | `geosync/verdict.py`, `scripts/claims_lifecycle.py`, `tools/compile_claims.py`, `application/governance/claim_ledger.py`, claim hashes — powerful but not unified behind one auditor API. |

## Gap to leading-industrial
1. **Provenance** — the verdict bound neither the code nor the data it verified (`code_version="unknown"`). ✅ **CLOSED by this increment.**
2. **Claim-driven proof** — `proof.run` proves ONE fixture mechanism; it is not yet driven by `CLAIMS.yaml` (run any claim → verdict). *(next)*
3. **Unified auditor CLI** — one entrypoint that runs a claim (or all), enforces FORBIDDEN_CLAIMS, resolves falsifiers, and emits a signed verdict set. *(next)*
4. **Promotion lifecycle** — HYPOTHESIS→ANCHORED→RETIRED with machine-checked promotion criteria (ledger RES-020). *(next)*
5. **Packaging/semver/external-reviewer packet** (DOC-009) so the kernel is reusable for AI-safety / model-eval / medical / financial-audit / agent-governance. *(later)*

## Increment 1 (this change) — auditor-grade provenance + tamper-evidence
An external auditor's `REJECT` is only trustworthy if the verdict binds exactly what it verified.
`geosync/proof/run.py` now emits:
- `code_version` — env-pin → **real git commit** (`git:<sha>`) → `unknown` (honest last resort, never a silent blank).
- `dataset_sha256` — sha256 of the input dataset bytes; the auditor can confirm the data.
- `content_digest` — a tamper-evident sha256 over **every other field**; a single flipped byte changes it.
- `python -m geosync.proof.run --verify <verdict.json>` — **auditor mode**: recompute the digest + re-hash the named dataset, exit 1 (`TAMPERED`) on any mismatch, 0 (`ok`) otherwise. Trusts only the bytes on disk.

Teeth (`tests/test_geosync_proof.py`): verdict is provenance-bound (`code_version != unknown`, both hashes present); `content_digest` is deterministic under a pinned substrate and self-recomputes; `verify_verdict` returns TAMPERED when the `verdict` field is flipped. Determinism, hygiene, and security-regression gates stay green (git resolution is `subprocess.run` list-argv, not ambient nondeterminism / shell).

This is step 1 of the roadmap; the remaining gaps (2–5) are stated as open, not claimed done.
