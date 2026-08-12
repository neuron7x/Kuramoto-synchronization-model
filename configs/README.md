# Configuration Guide

This directory contains YAML configuration presets for GeoSync components.

- `default.yaml` – minimal dataset and execution defaults used by quick-start examples.
- `kuramoto_ricci_composite.yaml` – reference configuration for the Kuramoto–Ricci composite integration workflow.

## Kuramoto–Ricci composite structure

Configuration files consumed by `scripts/integrate_kuramoto_ricci.py` follow this structure:

```yaml
kuramoto:
  timeframes: ["M1", "M5", "M15", "H1"]
  adaptive_window:
    enabled: true
    base_window: 200
  min_samples_per_scale: 64
ricci:
  temporal:
    window_size: 100
    n_snapshots: 8
    retain_history: true
  graph:
    n_levels: 20
    connection_threshold: 0.10
composite:
  thresholds:
    R_strong_emergent: 0.80
    R_proto_emergent: 0.40
    coherence_min: 0.60
    ricci_negative: -0.30
    temporal_ricci: -0.20
    topological_transition: 0.70
  signals:
    min_confidence: 0.50
```

All values are validated before being passed to the analysis engine. Invalid or out-of-range
settings will raise a clear `ConfigError`, making it easier to troubleshoot malformed presets.

If the requested configuration file is missing, the loader transparently falls back to the
default values shown above.
