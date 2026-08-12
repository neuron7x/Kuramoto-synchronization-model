# GeoSync fork decommission record

Status: `READY_FOR_DELETION`

Source: `https://github.com/neuron7x/GeoSync`

Canonical target: `https://github.com/neuron7x/Kuramoto-synchronization-model`

## Verified backup

- Bare mirror: `/home/neuro7/Desktop/COGNITIVE_LATTICE/backups/GeoSync-20260812.git`
- Portable bundle: `/home/neuro7/Desktop/COGNITIVE_LATTICE/backups/GeoSync-20260812.bundle`
- Bundle SHA-256: `87d3908259dbee3b5c582baca00b4065d19202db9e69b358cc4c4454d9bd5921`
- Bundle size: approximately 56 MiB
- Preserved refs: 30 branch heads and 2 tags
- Verification: `git fsck --full --no-dangling` passed; `git bundle verify` passed and reported complete history.

## Final path classification

After canonical integration, 42 fork paths were not activated under their old
names:

- 24 real-data paths are withheld because their license is not granted;
- 2 benchmark reports are generated output and were replaced by a replayable
  benchmark harness;
- 6 CLI, risk, security, and documentation paths have canonical replacements;
- 6 dashboard branding assets were superseded by the `neuron7xLab` variants;
- 2 secret/audit scanner outputs are historical, not active configuration;
- 1 pipeline-status CSV is a historical run artifact;
- 1 design-contract path was superseded by `neuron7xLab.md`.

The withheld data remain in the verified local mirror/bundle. Their individual
paths, blob SHA values, sizes, and license blocker are recorded in
`BLOCKED_DATA.tsv`. They must not be republished until the dataset-manifest gate
confirms a granted license.

## Restore command

```bash
git clone /home/neuro7/Desktop/COGNITIVE_LATTICE/backups/GeoSync-20260812.bundle GeoSync-restored
```

This record authorizes deletion only after it is committed and pushed to the
canonical target and the target SHA is verified remotely.
