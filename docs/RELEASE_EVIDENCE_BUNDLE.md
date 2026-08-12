# Release Evidence Bundle (REL-011)

A **single, schema-validated bundle** that says, for every evidence category a
1.1.0 release needs, exactly one thing: *where is the receipt, what is its
sha256, and is it present or absent.* It **references** the artifacts other
remediation waves already produced — it does not duplicate them.

- Bundle: `artifacts/releases/1.1.0/release_evidence.json`
- Checksums: `artifacts/releases/1.1.0/SHA256SUMS` (over the present referenced artifacts)
- Schema: `schemas/release_evidence.schema.json`
- Gate / generator: `scripts/ci/check_release_evidence.py`
- Tests: `tests/ci/test_release_evidence.py`

## Release-readiness verdict: NOT_READY (gate RED — by design)

The gate is **RED right now, and that is correct.** Five mandatory receipts do
not exist yet because their tasks are not done. Recording them as
`status: MISSING` (never fabricating a digest) makes the release-readiness
verdict `NOT_READY`. This is the same honest "not ready" signal a governance RED
gives — not a defect to be patched green.

| Category | Mandatory | Status | Backing artifact(s) |
|---|---|---|---|
| version | yes | PRESENT | `VERSION`, `CITATION.cff` (both 1.1.0) |
| commit_tree_tag | yes | PRESENT | `manifests/research/release_provenance.v2.json` (REL-005) |
| manifests | yes | PRESENT | `MANIFEST.sha256`, `artifacts/release/root_manifest_report.json` |
| sbom | yes | **MISSING** | `artifacts/release/sbom.spdx.json` (not produced) |
| tests | yes | **MISSING** | `artifacts/release/full_test_suite_report.json` (TST-001 canonical) |
| coverage | yes | **MISSING** | `artifacts/release/coverage_report.json` (TST-003) |
| mutation | yes | **MISSING** | `artifacts/release/mutation_report.json` (TST-010) |
| security_scan | yes | PRESENT | `artifacts/env/image_scan_report.json`, `artifacts/env/image_digest.json` (ENV-005) |
| wheel | yes | **MISSING** | `artifacts/release/wheel_manifest.json` (PKG-001) |
| docs | no | PRESENT | `docs/RELEASE_EVIDENCE_BUNDLE.md` |
| research_verdicts | yes | PRESENT | flagship comparison + power/UQ + selection-bias reports |
| cleanroom_reproducible_build | yes | PRESENT | `artifacts/release/reproducible_build_report.json` (REL-010), `artifacts/env/python312.json` |
| approvals | yes | PRESENT | `governance/remediation_ledger.v1.json` |

**Missing mandatory receipts (the blockers): `coverage`, `mutation`, `sbom`,
`tests`, `wheel`.** Until those exist and land in the bundle, the release stays
`NOT_READY`.

### Research verdicts are honestly INSUFFICIENT_EVIDENCE

The three research artifacts are *present* (they are recorded verdicts) and all
read `INSUFFICIENT_EVIDENCE` / non-supported. The bundle references the verdict
each carries; it does not upgrade or launder them.

## Determinism & tamper-evidence

`build_bundle()` in the gate is the **single source** of the bundle: it reads
artifact digests from disk and reads commit/tree/tag from the REL-005 provenance
manifest (**not** live `git`, so a later commit never perturbs the bytes). The
serialization is `sort_keys=True, indent=2` with a trailing newline and **no
timestamps**, so a rebuild is byte-for-byte identical. The committed
`release_evidence.json` is exactly that output.

The gate enforces four integrity properties, each RED on failure:

1. **Schema** — the committed bundle validates against `release_evidence.schema.json`.
2. **Digest match** — every PRESENT artifact's recorded sha256 is recomputed
   from disk; any drift is RED.
3. **Deterministic regen** — two rebuilds are byte-identical *and* equal the
   committed bundle; a stale/tampered bundle is RED.
4. **Readiness** — any mandatory category not fully PRESENT ⇒ `NOT_READY` ⇒ RED.

## Regenerate

```bash
python scripts/ci/check_release_evidence.py --emit   # rewrite bundle + SHA256SUMS
python scripts/ci/check_release_evidence.py          # verify (RED until receipts land)
python -m pytest tests/ci/test_release_evidence.py -q
```

## Residual (honest)

The RED is legitimate and expected. Closing it is **not** this task's job: it
requires the coverage (TST-003), mutation (TST-010), sbom, wheel (PKG-001), and
canonical full-suite (TST-001) receipts to actually be produced. When they are,
add them to `_CATEGORY_SPEC`, re-emit, and the readiness verdict flips to READY
on its own — no gate edit, no fabrication.
