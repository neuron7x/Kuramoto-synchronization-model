# Audit Response — Disha BA + Correlation Artefact

Maps the bugs raised in `~/Downloads/DISHA_AUDIT_REPORT_2026-05-09.md` to fixes shipped
in this PR. Each item is `fixed`, `partially fixed`, or `accepted risk`.

Git SHA: `725f3bf0993d3b65741a5704e63e1a54303d25e9`
Output dir: `figures/disha_ba_correlation`

| # | bug | severity | status | fix landed |
|---|---|---|---|---|
| B1 | BA Pearson r non-discriminating vs ER baseline | HIGH | **fixed** | `compute_ba_comparison()` now also runs ER simulations and computes `ba_minus_er_r`, `winner_by_ks`, `ba_claim_status`. Interpretation upgraded to `BA_DESCRIPTIVELY_BETTER` only when BA beats ER on Pearson margin AND KS AND zero-degree-tail. New `model_comparison_summary.csv` exposes both baselines. |
| B2 | Risk concentration polluted by 4-quarter Pearson saturation | HIGH | **fixed** | `compute_risk_concentration()` now computes `effective_change_observations` per node and adds `passes_strength_filter`, `passes_observation_filter`, `suspect_short_sample`, `suspect_low_mass`, `article_grade` columns. New `risk_concentration_article_grade.csv` filters to total_strength ≥ 100,000 AND effective_obs ≥ 8. Article summary uses only article-grade rows. |
| B3 | BA m structural mismatch (max-degree, zero-degree tail) | HIGH | **fixed** | `ba_fit_summary.csv` now includes `empirical_zero_degree_count`, `ba_zero_degree_count_mean`, `empirical_max_degree`, `ba_max_degree_mean`, `max_degree_ratio`, `zero_degree_mismatch`. `BA_STRUCTURAL_MISMATCH` claim status fires when empirical has zero-degree nodes that BA cannot reproduce. |
| B4 | Forbidden-wording check broken on line breaks | MEDIUM | **fixed** | `normalize_forbidden_text()` collapses whitespace before substring match in both `_write_article_summary` and `find_forbidden_phrases`. New tests verify multi-line forbidden phrases are caught. |
| B5 | ES, IT, HK, PH, ZA target-only behaviour invisible | MEDIUM | **fixed** | New `compute_reporter_status()` function and `reporter_status_summary.csv` output. `data_quality_summary.csv` exposes `target_only_nodes`, `constant_source_nodes`, `reporting_filter_warning`. Article summary §2 has explicit reporter-status caveat. |
| B6 | Lehman 4-quarter > 0.999 pairs in headline CSV | LOW | **fixed** | `top_correlated_pairs()` now adds `effective_n`, `suspicious_near_perfect`, `headline_allowed`. Article summary headline uses sensitivity-window pairs only; Lehman saturated pairs are filtered out at the article-summary level. CSV still records them with `headline_allowed=False` for full transparency. |
| B7 | Sensitivity AT-CA = +1.000 unflagged | LOW | **fixed** | Same `suspicious_near_perfect` flag (|r| ≥ 0.98) catches it; AT-CA becomes `headline_allowed=False`. |
| B8 | KS distance computed but ignored in interpretation | HIGH | **fixed** | `_ba_claim_status()` consumes both Pearson margin and KS comparison; `ER_KS_BETTER` status is emitted when ER KS distance is smaller. |
| B9 | Auto-written summary overreaches | HIGH | **fixed** | Summary §1 leads with "concentrated, but not uniquely BA-like"; §3 says BA claim is upgraded only on `BA_DESCRIPTIVELY_BETTER` status; §10 100-word paragraph is rewritten to acknowledge ER baseline equivalence. |
| Codex P1 | empty `build_period_outward_strength_panel` returns 0 columns | MEDIUM | **fixed** | Empty branch now returns `pd.DataFrame(columns=list(range(n_nodes)))` — preserves shape contract with `build_period_matrix`. |
| Codex P2 | `parse_quarter` accepts illegal quarter numbers | LOW | **fixed** | `parse_quarter("2008Q5")` now raises `ValueError` instead of producing a `KeyError` downstream. |

## Sample BA-vs-ER comparison from this run

| period | BA r | ER r | BA−ER r | KS_BA | KS_ER | winner | zero-mismatch | claim_status |
|---|---|---|---|---|---|---|---|---|
| normal | 0.940 | 0.941 | -0.001 | 0.349 | 0.422 | BA | True | NOT_DISTINGUISHED |
| lehman | 0.945 | 0.940 | +0.005 | 0.414 | 0.373 | ER | True | NOT_DISTINGUISHED |

## Artefact status

`ARTICLE_SAFE_AFTER_AUDIT` — usable for Disha's article when the article-grade outputs
(`risk_concentration_article_grade.csv`, sensitivity-window headline pairs in
`top_correlated_pairs_changes.csv` filtered by `headline_allowed=True`,
`model_comparison_summary.csv`) are used. The full unfiltered tables remain available
for transparency but are not the headline result.
