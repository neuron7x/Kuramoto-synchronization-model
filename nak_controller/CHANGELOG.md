# Changelog

## 2.1.0

- Initial open-source drop of the NaK neuro-energetic controller for TradePulse.
- Added deterministic RNG seeding and explicit `reset(seed=...)` support to keep
  runtime and tests reproducible.
- Hardened configuration loading with strict validation and YAML schema checks
  that reject unknown fields and invalid weight/risk ranges.
- Extended CLI tooling with a `--seed` flag and broadened unit coverage for
  seeding, hysteresis, rate limiting and noise generation. CI now publishes
  coverage and JUnit artefacts for observability.
