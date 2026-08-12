# MFN Integration Capsule — `seed=7, points=256`

This directory is the repository's first **real hash-pinned artifact graph**. Its
existence is what flips `scripts/ci/prove_repo_integrity.sh` from
`MANIFEST_PROOF: NOT_PROVEN` to `MANIFEST_PROOF: PROVEN`.

## What this proves

- **Integrity** — every file under `bundle/` has a SHA-256 digest committed in
  `manifest.json` (the `artifacts` array). `scripts/ci/check_manifest_hashes.py
  --require-artifacts` verifies on-disk bytes against those digests.
- **Reproducibility** — the bundle regenerates **bit-for-bit** from its declared
  command. `scripts/reproduce/mfn_capsule.py --verify` re-runs the MFN gateway
  into a temp dir and fails closed on any digest drift. CI enforces this in
  `.github/workflows/reproducible-capsule.yml` (clean-clone, foreign-cwd).
- **Schema** — the manifest is validated against
  `schemas/reproducible_capsule.schema.json`; see
  `docs/REPRODUCIBLE_CAPSULE_CONTRACT.md`.

## What this does NOT prove

This is **not** empirical evidence and makes **no** falsifiable market claim. The
bundle is the byte-deterministic output of the dependency-light MFN integration
gateway over a synthetic seed. It self-labels honestly:

| field | value |
|-------|-------|
| `claim_tier` | `INSTRUMENTED` |
| `decision` | `OBSERVE` |
| `falsification_status` | `BLOCKED` |

`evidence_class` in `manifest.json` is `REPRODUCIBLE_INFRASTRUCTURE_PROOF`, and
`is_empirical_evidence` is `false`. Treating this capsule as proof of alpha,
inference, or scientific result would be a category error — the same kind the
repo's truth gates exist to prevent.

## Regenerate

```bash
python scripts/reproduce/mfn_capsule.py --build    # rewrite bundle + manifest
python scripts/reproduce/mfn_capsule.py --verify   # prove on-disk == regenerated
```

Pinned parameters: `seed=7`, `points=256`, `SOURCE_DATE_EPOCH=1700000000`
(matching `.github/workflows/mfn-release-gate.yml`).
