# Reproducibility — Disha BA + Correlation Artefact

- Repository: `neuron7xLab/GeoSync`
- Git SHA: `725f3bf0993d3b65741a5704e63e1a54303d25e9`
- Dataset directory: `/tmp/bis_real_data/dataset_dir_v2`
- Manifest path: `/tmp/bis_real_data/dataset_dir_v2/manifest.json`
- Manifest source_id: `BIS-LBS-WS_LBS_D_PUB-v1.0`
- Manifest config_hash: `bis-lbs-claims-allsectors-cross-border-quarterly`
- Output directory: `figures/disha_ba_correlation`
- Python: `3.12.3 (main, Mar  3 2026, 12:15:18) [GCC 13.3.0]`

## Command

```
tools/build_disha_ba_correlation_figures.py --dataset-dir /tmp/bis_real_data/dataset_dir_v2 --output-dir figures/disha_ba_correlation --ba-simulations 200
```

Or programmatically equivalent:

```
python tools/build_disha_ba_correlation_figures.py \
    --dataset-dir /tmp/bis_real_data/dataset_dir_v2 \
    --output-dir figures/disha_ba_correlation \
    --normal-start 2006Q1 \
    --normal-end 2007Q4 \
    --lehman-start 2008Q3 \
    --lehman-end 2009Q2 \
    --sensitivity-start 2007Q1 \
    --sensitivity-end 2009Q4 \
    --edge-quantile 0.85 \
    --top-n-labels 12 \
    --ba-simulations 200 \
    --seed 42
```

## Generated files

- `network_normal.png`, `network_lehman.png`
- `correlation_levels_{normal,lehman,delta}.png`
- `correlation_changes_{normal,lehman,delta}.png`
- `risk_concentration_bar.png`
- `ba_fit_summary.csv`
- `top_correlated_pairs_levels.csv`
- `top_correlated_pairs_changes.csv`
- `risk_concentration_summary.csv`
- `data_quality_summary.csv`
- `DISHA_ARTICLE_SUMMARY.md`
- `REPRODUCIBILITY.md` (this file)

## Caveats

- Country-level aggregation; not bank-level.
- Edge threshold and BA m estimate are deterministic given `--seed` and `--edge-quantile`.
- Network layout uses `nx.spring_layout` with `seed=--seed`; minor matplotlib version drift
  may cause cosmetic differences but no metric changes.
- BA simulations use deterministic per-simulation seeds derived from `--seed`.

## Interpretation boundary

Allowed wording: country-level banking-system exposure network; macro banking-network
illustration; descriptive preferential-attachment-style comparison; correlation between
country banking-system exposure time series; public reproducible BIS baseline.

Forbidden wording (auto-checked at write time; see CLAIM_BOUNDARY.md for the
authoritative list).
