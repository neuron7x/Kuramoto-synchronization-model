# Disha BA + Correlation — Article Summary (Audit-Hardened)

## 1. Plain-English summary

This analysis uses public BIS LBS country-level banking-system aggregate exposure data.
It builds a directed exposure network between national banking systems and compares its
thresholded topology with BOTH a Barabási-Albert preferential-attachment baseline AND an
Erdős-Rényi matched-density baseline. The BA result is reported only if it
**discriminates from the random-graph baseline**; otherwise the topology is described as
"concentrated, but not uniquely BA-like". Pearson correlations between country exposure
time series identify which banking systems co-moved most strongly during the Lehman
window. The result is a macro country-level exposure illustration; it is not
bank-to-bank evidence and it does not validate repo liquidity contagion.

## 2. Data

- Source: BIS Locational Banking Statistics (LBS), bulk feed `WS_LBS_D_PUB`.
- Aggregation: country-level reporting banking system → counterparty country (sector A).
- Filter: `L_PARENT_CTY=5J, L_CP_SECTOR=A` (the only public BIS slice with bilateral
  REP × CP-country cells).
- Residual node `5Q`: already filtered upstream; not present in the country list.

### Reporter-status caveat

Under this filter, some countries appear as **target-only** or with **zero out-strength**
across all windows — a BIS reporting/filter constraint, NOT economic absence. This is
material for any country-level comparison and is exposed in `reporter_status_summary.csv`.

- Target-only under filter:
  ES, HK, IT, PH, ZA
- Zero out-strength across all windows (reporting suppressed under this filter):
  ES, HK, IT, PH, ZA

## 3. BA-style comparison vs Erdős-Rényi baseline

We threshold each period's averaged exposure matrix at the top 15%
of positive weights and compare the thresholded undirected degree sequence to:

- 200 Barabási-Albert simulations (same N, m matched to edge density)
- 200 Erdős-Rényi simulations (same N, p matched to edge density)

For each, we compute (a) Pearson r of sorted-degree sequences and (b) Kolmogorov-Smirnov
distance between empirical and pooled-simulated degree distributions. The BA claim is
upgraded to `BA_DESCRIPTIVELY_BETTER` ONLY when:

- BA Pearson r exceeds ER Pearson r by ≥ 0.05, AND
- BA KS distance ≤ ER KS distance, AND
- BA can reproduce the empirical zero-degree tail.

Otherwise: `NOT_DISTINGUISHED`, `ER_KS_BETTER`, or `BA_STRUCTURAL_MISMATCH`.

  normal: BA r = 0.940, ER r = 0.941, BA−ER r = -0.001, KS_BA = 0.349, KS_ER = 0.422, winner_by_ks = BA, emp_zero_deg = 8, BA_zero_deg_mean = 0.0, status = NOT_DISTINGUISHED
  lehman: BA r = 0.945, ER r = 0.940, BA−ER r = +0.005, KS_BA = 0.414, KS_ER = 0.373, winner_by_ks = ER, emp_zero_deg = 7, BA_zero_deg_mean = 0.0, status = NOT_DISTINGUISHED

Honest framing: the network is **concentrated**, but this concentration is not uniquely
explained by a Barabási-Albert mechanism unless the status above is `BA_DESCRIPTIVELY_BETTER`.

## 4. Pearson correlation — what it measures

For each country we sum its outward exposure each quarter (out-strength). Two correlations:

- **LEVELS**: correlation of raw out-strength. Trend-sensitive — secular growth in claims
  inflates level correlations.
- **LOG-CHANGES** (main metric): quarter-over-quarter `log(x + 1)` differences. Removes
  the secular trend; isolates co-movement of shocks.

Pairs are headline-allowed only when (effective_n ≥ 8) AND
(|r| < 0.98). Near-perfect correlations on short windows are flagged as
saturation, not signal.

**LOW_SAMPLE_WARNING:** the Lehman window contains < 4 usable observations after the log-change transformation. Lehman-only top change-correlation pairs are saturated by construction and are excluded from the headline list. Use sensitivity window for ranking.

## 5. Headline correlation result — sensitivity window only

Lehman 4-quarter log-change correlations are statistically fragile and are blocked from the
headline list (25 suspicious near-perfect pairs filtered out). The article
result uses the wider sensitivity window 2007Q1
– 2009Q4:

  2. DE–FR: r = +0.910 (n_eff = 11)
  3. DE–LU: r = +0.906 (n_eff = 11)
  4. GB–US: r = +0.872 (n_eff = 11)
  5. DE–GG: r = +0.869 (n_eff = 11)
  6. CH–GB: r = +0.865 (n_eff = 11)
  7. DE–GB: r = +0.850 (n_eff = 11)
  8. BR–GB: r = +0.846 (n_eff = 11)
  9. DE–IE: r = +0.845 (n_eff = 11)

## 6. Risk concentration — article-grade only

Filtered to nodes with total_strength_lehman ≥ 100,000 USD mn AND
effective_change_observations ≥ 8. Excludes small-mass
nodes whose high |r| is short-window saturation noise.

Top 10 article-grade countries:

  1. GB — Δ|r|_changes = +0.335, |r|_changes_lehman = 0.764, total_strength = 9,006,228
  2. DE — Δ|r|_changes = +0.479, |r|_changes_lehman = 0.775, total_strength = 4,428,127
  3. FR — Δ|r|_changes = +0.411, |r|_changes_lehman = 0.786, total_strength = 3,725,457
  4. LU — Δ|r|_changes = +0.469, |r|_changes_lehman = 0.789, total_strength = 1,687,001
  5. US — Δ|r|_changes = +0.149, |r|_changes_lehman = 0.573, total_strength = 5,247,551
  6. NL — Δ|r|_changes = +0.306, |r|_changes_lehman = 0.662, total_strength = 2,116,425
  7. BE — Δ|r|_changes = +0.386, |r|_changes_lehman = 0.701, total_strength = 1,363,849
  8. JP — Δ|r|_changes = +0.140, |r|_changes_lehman = 0.420, total_strength = 2,501,610
  9. IE — Δ|r|_changes = +0.385, |r|_changes_lehman = 0.786, total_strength = 1,991,685
  10. CH — Δ|r|_changes = +0.383, |r|_changes_lehman = 0.789, total_strength = 1,587,252

The full unfiltered ranking is in `risk_concentration_summary.csv`; the filtered ranking is in
`risk_concentration_article_grade.csv`. Use the latter for any external claim.

## 7. Limitations

1. Country-level aggregation, not bank-level interbank exposures.
2. Small N (~31 reporting countries); too small for strict heavy-tail estimation.
3. Edge thresholding is sensitive to `--edge-quantile`.
4. Pearson over short (~4-quarter) windows is statistically fragile (filtered out by default).
5. Level correlations are trend-sensitive.
6. Log-change correlations are better for shock co-movement but still descriptive — not causal.
7. Not a bank-level repo contagion model.
8. Not a causal model — these are descriptive co-movement statistics.
9. ES, IT, HK, PH, ZA-style countries are target-only or zero-out-strength under this filter
   (reporting/filter artefact, not economic absence).

## 8. Reproducibility

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
    --min-risk-total-strength 100000.0 \
    --min-effective-change-observations 8 \
    --seed 42
```

Git SHA: `725f3bf0993d3b65741a5704e63e1a54303d25e9`

## 9. Out of scope

This analysis does NOT use Kuramoto / phase-synchronisation modelling. The earlier X-9R
Kuramoto pipeline is unrelated to this artefact and was explicitly excluded per Disha's
request.

This analysis does NOT make bank-level claims. The BIS LBS bulk feed publishes bilateral
cells only at country level; bank-to-bank bilateral data requires supervisory access.

## 10. Suggested 100-word paragraph for Disha

> Using public BIS Locational Banking Statistics, we built a directed network of cross-border
> claims between national banking systems. We compared its thresholded topology against BOTH
> a Barabási-Albert and an Erdős-Rényi baseline; the network is **concentrated**, but this
> concentration is not uniquely explained by preferential attachment when matched-density
> Erdős-Rényi reproduces the same sorted-degree similarity. Pearson correlations of country
> exposure log-changes over the wider 2007Q1-2009Q4 window highlight economically plausible
> co-movement corridors among large continental European, UK and US banking systems. These
> figures illustrate macro country-level exposure structure; they are not bank-level
> evidence and do not validate liquidity contagion.
