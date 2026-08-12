# Reproducibility

The Ricci microstructure lane records `config_hash`, `data_sha256`, runtime `git_sha`, replay command, JSON artifact, data manifest and evidence bundle.

`REPRODUCIBILITY_CAPSULE.sh` performs:

```text
git clone -> checkout -> locked install -> ingest -> run -> verify -> SHA compare
```

Rules:

- no local absolute paths in committed config;
- no hardcoded git SHA;
- no silent fallback to synthetic data;
- no timestamp-dependent claim fields except documented `timestamp_utc`;
- no claim promotion without null-baseline statistical gate.

Licensed LOBSTER data must be supplied by the operator. The repository must not redistribute it or fake it, because apparently reality still has licensing terms.
