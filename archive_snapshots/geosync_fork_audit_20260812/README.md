# GeoSync fork integration audit

Source repository: `https://github.com/neuron7x/GeoSync`

Target repository: `https://github.com/neuron7x/Kuramoto-synchronization-model`

Audit date: `2026-08-12`

This record captures the read-only comparison used to consolidate the archived
GeoSync fork into the canonical repository. It is an integration manifest, not
a scientific result and not evidence for promotion of any claim tier.

## Files

- `BRANCHES.tsv` records all 30 audited fork branch tips, their commit SHA,
  ancestry relation to the target, and commit-count divergence at audit time.
- `MISSING_PATHS.txt` records paths present on at least one fork branch but not
  tracked by the target commit at the start of this integration cycle.
- `BLOCKED_DATA.tsv` records the Git blob SHA and byte size of local/fork data
  withheld from the public target because the corresponding manifests declare
  `UNKNOWN` or `PUBLIC_NO_LICENSE`. The files remain available locally and in
  the archived source fork; they must not enter the target until the dataset
  manifest gate confirms a granted license.

## Integration decisions

- Canonical `src/geosync/data` code, fail-closed leakage guards, valid dataset
  manifests, contradiction-ledger evidence, tests, and research benchmark code
  are integrated into the target.
- Existing canonical replacements under `geosync/`, `application/`,
  `devtools/`, and `src/geosync/` take precedence over duplicate legacy paths.
- Historical screenshots, stale generated reports, secret-scan baselines, and
  unlicensed datasets are not activated as current runtime or evidence.
- The fork remains a provenance source until every branch-specific surface has
  been classified; no branch is treated as authoritative merely because it is
  newer or contains more files.
