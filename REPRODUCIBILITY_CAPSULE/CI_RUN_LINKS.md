# CI Run Links

> Pointers to GitHub Actions runs at the SHA referenced in
> `MANIFEST.json::repository`. Reviewers should verify the runs
> are green before signing off.

## How to find the matching CI runs

```bash
gh run list --branch feat/research-integrity-9-9 --limit 30
gh pr list --state merged --search "feat/research-integrity-9-9"
```

## Workflows that must be green

| Workflow | Where |
|---|---|
| `Physics Invariants` | `.github/workflows/physics-invariants*.yml` |
| `Physics Kernel Gate` | `.github/workflows/physics-kernel-self-check*.yml` |
| `Schemathesis Contract` | `.github/workflows/schemathesis-contract.yml` |
| `Latency Budget — server_compute` | `.github/workflows/latency-budget*.yml` |
| `Governance Schema Export Sync` | `.github/workflows/governance-schema-export-sync.yml` |
| `Invariant Count Sync` | `.github/workflows/invariant-count-sync.yml` |
| `Main Validation` | `.github/workflows/main-validation.yml` |
| `CodeQL` | `.github/workflows/codeql.yml` |
| **`Research Integrity Gate`** | `.github/workflows/research-integrity-gate.yml` (new) |

The new `research-integrity-gate` runs the canonical-seven test
suite, the metamorphic + negative-control packs, and the
`tools/check_public_symbol_matrix.py` + `tools/compile_claims.py`
audits.
