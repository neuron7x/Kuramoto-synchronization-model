# Audit 1 — Topology of the 8-FX correlation graph

Generated UTC: `2026-04-21T21:02:22Z`
Panel: 8 FX majors, daily 21:00 UTC, inner-joined. Rolling window = **120** bars, threshold = **0.3**, max edges = **28** (= 8 choose 2).

## Hypothesis (ROOT_CAUSE §H1)

> The FX correlation graph saturates the 0.30 |corr| edge gate, so the variability combo_v1 relies on collapses into degree noise.

## Pre-committed label thresholds

| label | rule |
|---|---|
| SUPPORTED | P5(edge_density) ≥ 0.75 AND median ≥ 0.85 |
| NOT_SUPPORTED | median(edge_density) < 0.5 |
| WEAKLY_SUPPORTED | neither above |

## Global rolling-window stats (n = 5742 windows)

| metric | value |
|---|---:|
| `n_bars_total` | 5742 |
| `window` | 120 |
| `threshold` | 0.3 |
| `max_edges` | 28 |
| `mean_edge_density` | 0.6412 |
| `median_edge_density` | 0.6429 |
| `p5_edge_density` | 0.5 |
| `p95_edge_density` | 0.7857 |
| `std_edge_density` | 0.0888 |
| `mean_mean_abs_corr` | 0.4059 |
| `frac_fully_connected_one_component` | 0.9817 |
| `frac_at_max_edge_count` | 0.0 |

## Per-asset degree (over all windows)

| asset | mean_degree | median_degree | p5_degree | p95_degree | max_possible | frac_time_at_max_deg | frac_time_isolated |
|---|---|---|---|---|---|---|---|
| EURUSD | 5.9 | 6.0 | 5 | 7 | 7 | 0.2443 | 0.0 |
| GBPUSD | 5.4169 | 6.0 | 4 | 6 | 7 | 0.042 | 0.0 |
| USDJPY | 3.9925 | 4.0 | 1 | 6 | 7 | 0.0143 | 0.0 |
| AUDUSD | 4.7409 | 5.0 | 2 | 6 | 7 | 0.0084 | 0.0 |
| USDCAD | 4.4136 | 5.0 | 2 | 6 | 7 | 0.0132 | 0.0 |
| USDCHF | 4.9873 | 5.0 | 3 | 7 | 7 | 0.1118 | 0.0035 |
| EURGBP | 2.5425 | 3.0 | 1 | 5 | 7 | 0.0 | 0.0031 |
| EURJPY | 3.9115 | 4.0 | 1 | 7 | 7 | 0.0568 | 0.0 |

## Per-fold edge-density summary (head + tail)

First 5 folds:

| fold_id | test_start_ts | test_end_ts | in_2022 | n_bars | mean_edge_density | median_edge_density | p5_edge_density | p95_edge_density | mean_mean_abs_corr | mean_degree | mean_n_components |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2008-01-02 | 2008-03-28 | False | 63 | 0.6859 | 0.6786 | 0.6429 | 0.75 | 0.405 | 4.8016 | 1.0 |
| 2 | 2008-01-31 | 2008-04-28 | False | 63 | 0.712 | 0.7143 | 0.6786 | 0.75 | 0.3985 | 4.9841 | 1.0 |
| 3 | 2008-02-29 | 2008-05-27 | False | 63 | 0.7137 | 0.75 | 0.6429 | 0.75 | 0.3896 | 4.996 | 1.0 |
| 4 | 2008-03-31 | 2008-06-25 | False | 63 | 0.7012 | 0.6786 | 0.6429 | 0.75 | 0.3815 | 4.9087 | 1.0 |
| 5 | 2008-04-29 | 2008-07-24 | False | 63 | 0.6587 | 0.6786 | 0.5714 | 0.6786 | 0.3727 | 4.6111 | 1.0 |

Last 5 folds:

| fold_id | test_start_ts | test_end_ts | in_2022 | n_bars | mean_edge_density | median_edge_density | p5_edge_density | p95_edge_density | mean_mean_abs_corr | mean_degree | mean_n_components |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 218 | 2025-07-17 | 2025-10-13 | False | 63 | 0.6689 | 0.6786 | 0.6429 | 0.6786 | 0.4515 | 4.6825 | 1.0 |
| 219 | 2025-08-15 | 2025-11-11 | False | 63 | 0.6627 | 0.6786 | 0.6429 | 0.6786 | 0.4567 | 4.6389 | 1.0 |
| 220 | 2025-09-15 | 2025-12-10 | False | 63 | 0.6514 | 0.6429 | 0.6429 | 0.6786 | 0.4452 | 4.5595 | 1.0 |
| 221 | 2025-10-14 | 2026-01-09 | False | 63 | 0.6457 | 0.6429 | 0.6429 | 0.6786 | 0.4212 | 4.5198 | 1.0 |
| 222 | 2025-11-12 | 2026-02-09 | False | 63 | 0.6293 | 0.6429 | 0.5714 | 0.6786 | 0.4009 | 4.4048 | 1.0 |

## Label: **WEAKLY_SUPPORTED**

> P5(edge_density)=0.5000, median=0.6429 — partial saturation only

## Data artefacts

- `topology_rolling_metrics.csv` — per-bar rolling graph metrics
- `topology_per_fold.csv` — per-fold aggregates (222 rows)
- `topology_per_asset_degree.csv` — per-asset degree distribution
- `topology_audit.json` — machine-readable

## Interpretation contract

This audit answers one question: **is the FX correlation graph saturated at the 0.30 edge gate?** Saturation would explain why combo_v1's edge-toggle variable (Δ-Ricci vs Ricci_mean) collapses on this substrate. Supporting evidence is necessary but not sufficient to prove that saturation *caused* the FAIL — causal attribution requires Audits 2 and 3 jointly.
