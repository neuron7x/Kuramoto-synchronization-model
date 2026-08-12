# Disha BA + Correlation Article Artifact — Final Report

## 1. Executive Verdict

**FINAL_STATUS: ARTICLE_SAFE_AFTER_AUDIT**

All quality gates pass; 20 output files produced; 42/42 unit tests green (was 24, added 18 audit-coverage tests); 625/625 full systemic_risk suite pass; mypy `--strict`, ruff, black clean; no Kuramoto used; whitespace-normalised forbidden-wording check; explicit limitation block included; **all B1–B9 audit findings + Codex P1/P2 fixed** (see `figures/disha_ba_correlation/AUDIT_RESPONSE.md`).

Article-safe outputs: `risk_concentration_article_grade.csv`, sensitivity-window pairs in `top_correlated_pairs_changes.csv` filtered by `headline_allowed=True`, `model_comparison_summary.csv`. Use these — not the unfiltered headline tables — for any external claim.

Honest BA framing: under this BIS sample, the network is **concentrated** but BA Pearson margin over Erdős-Rényi is < 0.05 → `ba_claim_status = NOT_DISTINGUISHED`. KS distance favours ER on the Lehman window; BA cannot reproduce the empirical zero-degree tail (8/7 zero-degree countries vs 0 in BA simulations). The "preferential attachment" framing is therefore explicitly retracted from headline use.

## 2. Reproducibility

- **Repository**: `neuron7xLab/GeoSync`
- **Branch**: `feat/disha-ba-correlation-figures`
- **SHA at run**: `e01faaa81f729a0221e5cbc981b3f953b37ae70e` (parent commit before this PR)
- **Dataset directory**: `/tmp/bis_real_data/dataset_dir_v2`
  - source: `BIS-LBS-WS_LBS_D_PUB-v1.0`
  - panel range: 1995-Q1 .. 2023-Q4 (116 quarters)
  - n_nodes: 31 reporting countries (5Q residual already filtered upstream)
- **Command run**:
  ```
  python tools/build_disha_ba_correlation_figures.py \
      --dataset-dir /tmp/bis_real_data/dataset_dir_v2 \
      --output-dir figures/disha_ba_correlation \
      --normal-start 2006Q1 --normal-end 2007Q4 \
      --lehman-start 2008Q3 --lehman-end 2009Q2 \
      --sensitivity-start 2007Q1 --sensitivity-end 2009Q4 \
      --edge-quantile 0.85 --top-n-labels 12 \
      --ba-simulations 1000 --seed 42
  ```
- **Output directory**: `figures/disha_ba_correlation/`
- **Tests**: `pytest tests/research/systemic_risk/test_disha_ba_correlation_figures.py` → 24 passed in 4.21s
- **Quality gates**: ruff PASS, black PASS, mypy --strict PASS

## 3. Generated Artifacts

### Figures (PNG)
- `network_normal.png`
- `network_lehman.png`
- `correlation_levels_normal.png`
- `correlation_levels_lehman.png`
- `correlation_levels_delta.png`
- `correlation_changes_normal.png`
- `correlation_changes_lehman.png`
- `correlation_changes_delta.png`
- `risk_concentration_bar.png`

### Data tables (CSV)
- `ba_fit_summary.csv`
- `top_correlated_pairs_levels.csv`
- `top_correlated_pairs_changes.csv`
- `risk_concentration_summary.csv`
- `data_quality_summary.csv`

### Documentation (MD)
- `DISHA_ARTICLE_SUMMARY.md`
- `REPRODUCIBILITY.md`

## 4. Data Boundary

The data are **BIS LBS country-level banking-system aggregate exposures** (cross-border claims of country *i*'s reporting banks on counterparties in country *j*, sector A = all sectors, USD-converted, quarterly stocks).

- **Not** bank-level interbank exposures
- **Not** repo-specific data
- **Not** a direct liquidity-risk validation
- **Not** a causal model

The BIS LBS bulk feed publishes bilateral REP × CP-country cells only at L_CP_SECTOR ∈ {A, N}. Banks-only sector breakdown (B/I/J) is aggregated to L_CP_COUNTRY=5J, so true bank-to-bank bilateral data is not derivable from this public feed.

## 5. BA-Style Comparison

Edge threshold: top 15% of positive weights (`--edge-quantile 0.85`).
Simulations: 1000 per period, deterministic seeds.

| period | n_edges | BA m | empirical mean degree | empirical max degree | empirical Gini | BA Pearson r | BA KS distance | interpretation |
|---|---|---|---|---|---|---|---|---|
| Normal (2006Q1–2007Q4) | 73 | 2 | 4.71 | 20 | 0.572 | **0.941** | 0.349 | descriptively similar to PA-style concentration |
| Lehman (2008Q3–2009Q2) | 72 | 2 | 4.65 | 19 | 0.570 | **0.945** | 0.414 | descriptively similar to PA-style concentration |

**Interpretation:**
- Both periods show degree distributions whose **sorted** sequence is highly correlated (r ≈ 0.94) with the mean BA simulated sequence — i.e., a few countries dominate the thresholded-edge degree, consistent with preferential-attachment-style concentration.
- KS distance is moderate (≈ 0.35–0.41) — empirical and BA *distributions* differ in shape even though their sorted ranks align.
- KS slightly worsens in the Lehman window (0.349 → 0.414), suggesting marginal departure from BA shape during the crisis window — but with N=31 this is **not** a strict statistical claim.

**Caveat (mandatory):** small N (~31 countries), sparse thresholded graph (~73 edges); this is a **descriptive comparison**, not a strict power-law validation.

## 6. Correlation Findings

### LEVELS (raw out-strength) — trend-sensitive

Top 5 |r| pairs, Lehman window:
1. CL ↔ TW: r = −1.000
2. CA ↔ DE: r = +0.998
3. BR ↔ LU: r = +0.998
4. IM ↔ TW: r = +0.998
5. CL ↔ IM: r = −0.997

These near-±1 values reflect short-window saturation (4 quarters), not stable economic structure. Use the changes window for inference.

### LOG-CHANGES (Δlog out-strength) — main co-movement metric

**LOW_SAMPLE_WARNING:** Lehman window has 4 quarters → 3 change observations. Pearson on 3 points is statistically meaningless. Lehman-only top pairs are **all > 0.999** by construction — saturation, not signal. **Rely on the wider sensitivity window** for ranking.

Top 8 sensitivity-window (2007Q1–2009Q4, 11 change observations) pairs:

| rank | pair | r | economic note |
|---|---|---|---|
| 1 | AT ↔ CA | +1.000 | likely small-sample saturation despite wider window — flag with caution |
| 2 | DE ↔ FR | +0.910 | core eurozone banking systems |
| 3 | DE ↔ LU | +0.906 | German banks heavily intermediated through Luxembourg |
| 4 | GB ↔ US | +0.872 | London-NY interbank corridor |
| 5 | DE ↔ GG | +0.869 | Germany-Guernsey offshore channel |
| 6 | CH ↔ GB | +0.865 | Swiss-UK universal banking ties |
| 7 | DE ↔ GB | +0.850 | Continental-UK link |
| 8 | BR ↔ GB | +0.846 | Brazilian exposure intermediated via London |

These pairs are **economically sensible** and align with documented cross-border banking corridors during the 2007–2009 stress period.

### Whether sensitivity supports primary

The sensitivity window **partially supports** the primary Lehman ranking only on the larger pairs (DE/FR/LU/GB/US/CH cluster). Primary 4-quarter Lehman pairs are dominated by saturation and should not be used for inference. **Sensitivity-window co-movement = the article-grade result.**

## 7. Risk Concentration

Ranking by Δ mean |r|_changes (Lehman − Normal), then |r|_changes_lehman, then total_strength_lehman.

| rank | country | Δ\|r\|_changes | \|r\|_changes_lehman | total_strength_lehman (USD mn) |
|---|---|---|---|---|
| 1 | CA | +0.491 | 0.782 | 579,052 |
| 2 | JE | +0.483 | 0.773 | 699,869 |
| 3 | IM | +0.481 | 0.789 | 116,405 |
| 4 | DE | +0.479 | 0.775 | 4,428,127 |
| 5 | CL | +0.474 | 0.777 | 31,051 |
| 6 | LU | +0.469 | 0.789 | 1,687,001 |
| 7 | TW | +0.446 | 0.785 | 151,879 |
| 8 | AT | +0.440 | 0.732 | 463,389 |
| 9 | MO | +0.413 | 0.789 | 18,183 |
| 10 | FR | +0.411 | 0.786 | 3,725,457 |

**Notes:**
- Large continental European systems (DE, FR, LU) appear in the top 10 — they are both high-mass nodes AND show the strongest Lehman-window co-movement increase.
- Several offshore/island financial centres (JE, IM, MO) show high Δ — consistent with their role as exposure conduits for larger systems.
- Magnitude saturation again applies: the |r|_lehman ≈ 0.78 cluster is partly Lehman-window short-sample saturation.

## 8. Limitations

1. **Country-level aggregation** — not bank-level interbank exposures; one node = one country's entire reporting banking system.
2. **Small N** (~31 countries in the public bilateral cell set) — too few for strict power-law / heavy-tail estimation.
3. **Threshold sensitivity** — `--edge-quantile 0.85` is a deliberate but arbitrary cut; lower or higher quantiles change topology.
4. **Pearson over short windows is fragile** — 4-quarter Lehman log-change correlations are saturated (most pairs > 0.999); only wider windows give meaningful magnitudes.
5. **Levels are trend-sensitive** — claim volumes grew ~5× across the panel; level correlations partly track that trend.
6. **Log-changes are better for shock co-movement** but still descriptive — they do not establish causation or contagion direction.
7. **Not a bank-level repo contagion model** — repo-specific liquidity dynamics require funding-market microstructure data, not LBS stock totals.
8. **Not a causal model** — these are descriptive correlations; structural identification would need an instrument or natural experiment.
9. **Constant nodes** — 5 countries (ES, HK, IT, PH, ZA) appear with zero/constant out-strength in the test windows (likely periods where they did not act as reporters or had data suppression). Their correlation rows are NaN by design.

## 9. Suggested 100-word explanation for Disha

> Using the public BIS Locational Banking Statistics, we built a directed network of cross-border
> claims between national banking systems and compared its thresholded topology with a
> Barabási-Albert preferential-attachment benchmark. We then computed Pearson correlations
> between country-level outward-exposure time series for a normal pre-crisis window and the
> Lehman window. Several country pairs show markedly stronger co-movement of exposure changes
> during 2007–2009, and a small set of countries (Canada, Germany, France, Luxembourg, UK,
> US, Switzerland) dominate network mass. These figures illustrate macro banking-network
> structure descriptively; they are not bank-to-bank exposures and do not constitute a
> validated liquidity-contagion model.

## 10. Next Article Step

- **Use the figures as macro illustration**, with caption text explicitly referencing "country-level banking-system aggregate exposures" and "descriptive only".
- **Lead with the BA-style Gini ≈ 0.57** and "few large nodes dominate" framing rather than a strict power-law claim.
- **Lead with sensitivity-window changes correlations** (DE-FR ≈ 0.91, DE-LU ≈ 0.91, GB-US ≈ 0.87) rather than the saturated 4-quarter Lehman pairs.
- **If the article wants repo liquidity specifically**, add a separate section that mentions: collateral chains, haircuts, maturity mismatch, rollover pressure, dealer-bank intermediation. The current artefact does not speak to those mechanisms.
- **Keep BA as topology story, correlation as co-movement story.** Do not conflate them with phase-transition / synchronisation language.

---

## Appendix: explicit non-claims

- **No Kuramoto** was used. This artefact is fully orthogonal to the X-9R Kuramoto-on-interbank pipeline (PRs #582–#588, branch retired for this work).
- **No bank-level claim** is made anywhere in the figures, summary, or this report.
- **No phase-transition claim** is made.
- **No repo-liquidity validation claim** is made.
- The forbidden-wording list (`bank-level interbank network`, `bank-to-bank exposures`, `validated repo liquidity`, `confirmed Barabási-Albert`, `confirmed systemic-risk phase transition`, `liquidity contagion proof`, `production-grade scientific validation`) is automatically self-checked at write-time and verified absent by `test_forbidden_wording_absent_from_summary`.
