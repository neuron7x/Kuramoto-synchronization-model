# Reproducible Capsule Contract

A **reproducible capsule** is the byte-deterministic output of a dependency-light
generator, hash-pinned for integrity and regenerable for reproducibility. It is
the mechanism by which `scripts/ci/prove_repo_integrity.sh` reports
`MANIFEST_PROOF: PROVEN` — a real hash-pinned artifact graph, not a vacuous pass.

> **Boundary.** A capsule proves *infrastructure reproducibility* only. It is
> **never** empirical market evidence. `is_empirical_evidence` is fixed `false`
> and `evidence_class` is fixed `REPRODUCIBLE_INFRASTRUCTURE_PROOF`. See
> `PRODUCT_CATEGORY.md`.

## Schema

The manifest contract is `schemas/reproducible_capsule.schema.json`
(JSON Schema draft 2020-12, `additionalProperties: false`). Unknown top-level
fields fail validation, so a capsule cannot be malformed silently.

| Field | Meaning |
|-------|---------|
| `schema_version` | Pinned schema identity (`geosync.reproducible_capsule.v1`). |
| `capsule_id` | Stable lowercase lineage id. |
| `artifact_role` | Fixed `instrumentation_capsule`. |
| `evidence_class` | Fixed `REPRODUCIBLE_INFRASTRUCTURE_PROOF`. |
| `is_empirical_evidence` | Fixed `false`. |
| `generator` | Exact command that regenerates the bundle bit-for-bit. |
| `git_sha` | Repository SHA the capsule was generated against (provenance). |
| `source_date_epoch` | Pinned `SOURCE_DATE_EPOCH` for byte-reproducibility. |
| `created_at_utc` | Deterministic UTC stamp derived from `source_date_epoch`. |
| `verify_command` | Command that proves on-disk bytes == fresh regeneration. |
| `artifacts` | Hash-pinned bundle files: `{path (relative), sha256, bytes}`. |
| `sha256_manifest` | SHA-256 of the bundle's own `SHA256SUMS` anchor. |
| `claim_boundary` | Plain-language non-evidence boundary statement. |

## Invariants (enforced)

1. `is_empirical_evidence` is `false`; `evidence_class` and `artifact_role` are
   their fixed constants.
2. Every artifact `path` is repo-relative (no leading `/`, no `..`).
3. Every digest is a 64-hex SHA-256; `git_sha` is 40-hex.
4. Unknown top-level fields fail validation.

## Verification layers

| Layer | Tool | Proves |
|-------|------|--------|
| Schema | `scripts/ci/check_capsule_schema.py` | Manifest matches the contract. |
| Reproduction | `scripts/reproduce/mfn_capsule.py --verify` | Bundle regenerates bit-for-bit; digests match; no untracked file; fails closed on every drift (negative tests: `tests/reproduce/test_mfn_capsule_negative.py`). |
| Secret boundary | `tools/security/validate_capsule_secret_boundary.py` | The capsule tree is text-only and carries no smuggled secret (replaces a detect-secrets exclude zone with deterministic structural validation). |

## CI

* **`reproducible-capsule.yml`** — clean-clone, minimal-install, foreign-cwd
  reproduction + schema + secret boundary; uploads a machine-readable JSON
  report. Required for PRs touching capsule / MFN / schema / manifest logic.
* **`repo-integrity-gate.yml`** — the holistic one-command proof, including the
  manifest-hash layer the capsule satisfies.
* **`security-deep.yml`** — weekly `capsule-secret-boundary` scan.

## Regenerate

```bash
python scripts/reproduce/mfn_capsule.py --build    # rewrite bundle + manifest
python scripts/reproduce/mfn_capsule.py --verify   # prove on-disk == regenerated
```

## One-command release proof

```bash
make evidence-gate         # full 13-layer proof (adds coverage)
make evidence-gate-core    # layers 1-11 (sci-core stack, no heavy coverage run)
```
