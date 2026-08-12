# GitHub snapshot preservation record

This directory preserves every file from commit
`9e6e4792991c6b446dc940968c115bc21f531072` whose Git blob is not present
unchanged in the consolidated GeoSync commit
`8fee3d185c93eb4b430e5d38e21f895da2c06676`.

The snapshot is a preservation and compatibility source, not an active runtime
namespace. Files retain their original relative paths below this directory so
that provenance, design intent, tests, workflows, data contracts, and earlier
implementations remain reviewable without reactivating obsolete TradePulse
imports or legacy GitHub Actions.

## Integrity

- `MANIFEST.tsv` records the original path, Git blob SHA, byte size, and
  preservation classification for all 283 files.
- `INTEGRATION_MAP.tsv` records the full old-to-consolidated tree comparison,
  including detected renames and similarity percentages.
- The original commit remains an ancestor of `main`; this snapshot makes its
  unique source surfaces directly addressable from the current tree.

Verify a preserved file against the original Git object:

```bash
original_path='src/tradepulse/data/schema.py'
expected=$(awk -F '\t' -v p="$original_path" '$1 == p {print $2}' \
  archive_snapshots/github_9e6e4792_unique/MANIFEST.tsv)
actual=$(git hash-object \
  "archive_snapshots/github_9e6e4792_unique/$original_path")
test "$actual" = "$expected"
```

## Integration rule

Do not copy preserved code back into active namespaces wholesale. For each
component, first classify it as `renamed`, `superseded`, `compatibility`,
`historical evidence`, or `active restoration`; then bind active restorations
to the canonical `geosync`, `geosync_hpc`, `geosync_hydro`, or `geosync_pro`
surface and add focused tests. Historical workflows remain here unless their
gates are reconciled with the current claim and inference contracts.

