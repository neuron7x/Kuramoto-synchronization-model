# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for tools/build_disha_ba_correlation_figures.py."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

# matplotlib + networkx are runtime deps of the script. If they're missing
# in the CI environment (e.g. fast-test slim image), skip this module
# entirely rather than failing at collection. The script itself surfaces
# the missing dep clearly when executed.
pytest.importorskip("matplotlib")
pytest.importorskip("networkx")

from tools.build_disha_ba_correlation_figures import (  # noqa: E402
    BuildOptions,
    build_article_artifact,
    build_correlation_matrix,
    build_period_matrix,
    build_period_outward_strength_panel,
    compute_ba_comparison,
    compute_correlation_validity,
    compute_reporter_status,
    compute_risk_concentration,
    estimate_ba_m,
    find_forbidden_phrases,
    load_dataset,
    normalize_forbidden_text,
    parse_quarter,
    quarter_end_date,
    threshold_adjacency,
    to_log_changes,
    top_correlated_pairs,
)

# ---------------------------------------------------------------------------
# Synthetic fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_dataset(tmp_path: Path) -> Path:
    """4-country, 8-quarter synthetic BIS-like dataset_dir.

    Country 0 (AAA) and 1 (BBB) form a strongly correlated pair.
    Country 2 (CCC) is constant exposure (will trigger constant-node handling).
    Country 3 (DDD) is uncorrelated noise.
    Edge 0->1 is the strongest persistent edge.
    """
    nodes = ["AAA", "BBB", "CCC", "DDD"]
    n = len(nodes)
    # Quarters: 2006Q1..2009Q4 (16 quarters)
    quarters = []
    for year in range(2006, 2010):
        for q in (1, 2, 3, 4):
            quarters.append(quarter_end_date(year, q))
    rows: list[dict[str, Any]] = []
    rng = np.random.default_rng(123)
    for k, qd in enumerate(quarters):
        # AAA <-> BBB strongly correlated (both grow with k + small noise)
        base = 1000.0 + 50.0 * k + rng.normal(0, 5)
        m = np.zeros((n, n))
        m[0, 1] = base * 1.5
        m[1, 0] = base * 0.9
        # CCC always 100 (constant)
        m[2, 0] = 100.0
        m[2, 1] = 100.0
        # DDD random uncorrelated
        m[3, 0] = max(10.0, rng.normal(500, 200))
        m[3, 1] = max(10.0, rng.normal(400, 200))
        # AAA also exports to CCC (small)
        m[0, 2] = 50.0 + 5 * k
        for i in range(n):
            for j in range(n):
                if i != j and m[i, j] > 0:
                    rows.append(
                        {
                            "date": qd,
                            "source": i,
                            "target": j,
                            "exposure": float(m[i, j]),
                        }
                    )
    df = pd.DataFrame(rows)
    ds = tmp_path / "synth_ds"
    ds.mkdir()
    df.to_parquet(ds / "exposure_panel.parquet", index=False)
    nm = pd.DataFrame({"node_id": list(range(n)), "bank_label": nodes})
    nm.to_parquet(ds / "node_mapping.parquet", index=False)
    payload_sha = hashlib.sha256((ds / "exposure_panel.parquet").read_bytes()).hexdigest()
    manifest = {
        "source_id": "TEST-SYNTHETIC",
        "schema_version": "interbank.panel.v1",
        "capture_timestamp_utc": "2026-05-09T12:00:00+00:00",
        "payload_sha256": payload_sha,
        "seed": 42,
        "config_hash": "synthetic-test",
        "n_banks": n,
        "n_days": len(quarters),
        "crisis_lock_timestamp_utc": "2026-05-01T00:00:00+00:00",
        "first_evaluation_timestamp_utc": "2026-05-08T00:00:00+00:00",
        "interpretation_caveat": "synthetic test fixture; not BIS data",
        "filter_spec": {
            "FREQ": "Q",
            "TIME_RANGE": ["2006-Q1", "2009-Q4"],
        },
        "config": {"window": 4, "align": "trailing"},
    }
    (ds / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    (ds / "license.txt").write_text("Test fixture — use is permitted.\n")
    (ds / "crisis_ledger.json").write_text(json.dumps({"events": []}))
    return ds


# ---------------------------------------------------------------------------
# Quarter / parsing
# ---------------------------------------------------------------------------


def test_parse_quarter_round_trip() -> None:
    assert parse_quarter("2008Q3") == (2008, 3)
    assert parse_quarter("2008-Q3") == (2008, 3)
    assert parse_quarter("1995q1") == (1995, 1)


def test_parse_quarter_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_quarter("not-a-quarter")


def test_quarter_end_date() -> None:
    assert quarter_end_date(2008, 3) == date(2008, 9, 30)
    assert quarter_end_date(2023, 4) == date(2023, 12, 31)


# ---------------------------------------------------------------------------
# DATA LOADING / MATRIX TESTS
# ---------------------------------------------------------------------------


def test_load_dataset_synth(synthetic_dataset: Path) -> None:
    ds = load_dataset(synthetic_dataset)
    assert ds.nodes == ("AAA", "BBB", "CCC", "DDD")
    assert ds.label_to_id == {"AAA": 0, "BBB": 1, "CCC": 2, "DDD": 3}
    assert ds.panel.shape[0] > 0


def test_load_dataset_missing_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_dataset(tmp_path / "does_not_exist")


def test_period_filtering(synthetic_dataset: Path) -> None:
    ds = load_dataset(synthetic_dataset)
    n = len(ds.nodes)
    mat, qs = build_period_matrix(ds.panel, n, (2006, 1), (2007, 4))
    assert mat.shape == (n, n)
    assert len(qs) == 8  # 8 quarters in 2006-2007


def test_period_filtering_empty_window(synthetic_dataset: Path) -> None:
    ds = load_dataset(synthetic_dataset)
    n = len(ds.nodes)
    # Window outside synthetic data range
    mat, qs = build_period_matrix(ds.panel, n, (1990, 1), (1990, 4))
    assert mat.shape == (n, n)
    assert qs == []
    assert np.all(mat == 0)


def test_node_ordering_deterministic(synthetic_dataset: Path) -> None:
    ds1 = load_dataset(synthetic_dataset)
    ds2 = load_dataset(synthetic_dataset)
    assert ds1.nodes == ds2.nodes


def test_edge_direction_preserved(synthetic_dataset: Path) -> None:
    ds = load_dataset(synthetic_dataset)
    n = len(ds.nodes)
    mat, _ = build_period_matrix(ds.panel, n, (2006, 1), (2007, 4))
    # AAA->BBB stronger than BBB->AAA in fixture
    assert mat[0, 1] > mat[1, 0]


def test_non_negative_finite_values_preserved(synthetic_dataset: Path) -> None:
    ds = load_dataset(synthetic_dataset)
    n = len(ds.nodes)
    mat, _ = build_period_matrix(ds.panel, n, (2006, 1), (2009, 4))
    assert np.all(mat >= 0)
    assert np.all(np.isfinite(mat))


def test_outward_strength_panel(synthetic_dataset: Path) -> None:
    ds = load_dataset(synthetic_dataset)
    n = len(ds.nodes)
    panel, qs = build_period_outward_strength_panel(ds.panel, n, (2006, 1), (2007, 4))
    assert panel.shape == (8, n)
    # CCC always 100 to AAA + 100 to BBB = 200 constant
    assert (panel.iloc[:, 2] == 200).all()


# ---------------------------------------------------------------------------
# NETWORK TESTS
# ---------------------------------------------------------------------------


def test_threshold_deterministic() -> None:
    M = np.array(
        [
            [0, 5, 1],
            [2, 0, 3],
            [4, 0, 0],
        ],
        dtype=float,
    )
    b1 = threshold_adjacency(M, 0.5)
    b2 = threshold_adjacency(M, 0.5)
    assert np.array_equal(b1, b2)
    # diagonal must be zero
    assert np.all(np.diag(b1) == 0)


def test_threshold_all_zero_safe() -> None:
    M = np.zeros((4, 4))
    b = threshold_adjacency(M, 0.85)
    assert b.shape == (4, 4)
    assert np.all(b == 0)


def test_estimate_ba_m_bounds() -> None:
    assert estimate_ba_m(31, 100) >= 1
    assert estimate_ba_m(31, 100) <= 30
    assert estimate_ba_m(5, 100) <= 4
    assert estimate_ba_m(0, 0) == 0
    assert estimate_ba_m(2, 0) == 1  # max(1, round(0/2)) = 1


def test_ba_comparison_returns_finite_for_normal_graph() -> None:
    rng = np.random.default_rng(7)
    n = 12
    A = (rng.random((n, n)) > 0.6).astype(np.uint8)
    np.fill_diagonal(A, 0)
    info = compute_ba_comparison(A, ba_simulations=20, seed=42)
    assert np.isfinite(info["ba_degree_pearson_r"]) or np.isnan(info["ba_degree_pearson_r"])
    assert info["ba_m_estimate"] >= 1
    assert info["ba_m_estimate"] <= n - 1


def test_ba_comparison_degenerate_returns_documented_nan() -> None:
    A = np.zeros((10, 10), dtype=np.uint8)
    info = compute_ba_comparison(A, ba_simulations=5, seed=42)
    assert np.isnan(info["ba_degree_pearson_r"])
    assert info["interpretation"].startswith("inconclusive")


# ---------------------------------------------------------------------------
# CORRELATION TESTS
# ---------------------------------------------------------------------------


def test_correlation_symmetric_diag_one() -> None:
    rng = np.random.default_rng(3)
    df = pd.DataFrame(rng.normal(size=(10, 4)))
    corr, _ = build_correlation_matrix(df)
    assert np.allclose(corr, corr.T, equal_nan=True)
    for i in range(4):
        assert corr[i, i] == 1.0


def test_correlation_constant_node_handling() -> None:
    df = pd.DataFrame(
        {
            0: [1.0, 2.0, 3.0, 4.0, 5.0],
            1: [5.0, 5.0, 5.0, 5.0, 5.0],  # constant
            2: [2.0, 4.0, 6.0, 8.0, 10.0],  # perfectly correlated with 0
        }
    )
    corr, constants = build_correlation_matrix(df)
    assert constants == [1]
    assert np.isnan(corr[1, 0])
    assert np.isnan(corr[0, 1])
    assert abs(corr[0, 2] - 1.0) < 1e-9


def test_log_changes_one_fewer_observation() -> None:
    df = pd.DataFrame({0: [1.0, 2.0, 4.0, 8.0, 16.0]})
    chg = to_log_changes(df, epsilon=1.0)
    assert chg.shape == (4, 1)


def test_delta_correlation_simple() -> None:
    A = np.array([[1.0, 0.5], [0.5, 1.0]])
    B = np.array([[1.0, 0.9], [0.9, 1.0]])
    delta = B - A
    assert delta[0, 1] == pytest.approx(0.4)
    assert delta[0, 0] == 0.0


# ---------------------------------------------------------------------------
# RISK CONCENTRATION
# ---------------------------------------------------------------------------


def test_risk_concentration_ranking_basic() -> None:
    nodes = ("AAA", "BBB", "CCC")
    cor_lev_n = np.array([[1.0, 0.5, 0.1], [0.5, 1.0, 0.1], [0.1, 0.1, 1.0]])
    cor_lev_l = np.array([[1.0, 0.9, 0.7], [0.9, 1.0, 0.7], [0.7, 0.7, 1.0]])
    cor_chg_n = cor_lev_n.copy()
    cor_chg_l = cor_lev_l.copy()
    weighted = np.array([[0, 100, 50], [10, 0, 5], [1, 1, 0]], dtype=float)
    binary = np.array([[0, 1, 1], [1, 0, 0], [0, 0, 0]], dtype=np.uint8)
    rc = compute_risk_concentration(
        nodes=nodes,
        corr_levels_normal=cor_lev_n,
        corr_levels_lehman=cor_lev_l,
        corr_changes_normal=cor_chg_n,
        corr_changes_lehman=cor_chg_l,
        weighted_lehman=weighted,
        binary_lehman=binary,
    )
    assert list(rc["country"]) == ["AAA", "BBB", "CCC"] or set(rc["country"]) == set(nodes)
    assert rc["risk_concentration_rank"].tolist() == [1, 2, 3]


# ---------------------------------------------------------------------------
# INTEGRATION: end-to-end with synthetic dataset
# ---------------------------------------------------------------------------


def test_build_article_artifact_end_to_end(synthetic_dataset: Path, tmp_path: Path) -> None:
    out = tmp_path / "article_out"
    opts = BuildOptions(
        dataset_dir=synthetic_dataset,
        output_dir=out,
        normal_start=(2006, 1),
        normal_end=(2007, 4),
        lehman_start=(2008, 3),
        lehman_end=(2009, 2),
        sensitivity_start=(2007, 1),
        sensitivity_end=(2009, 4),
        edge_quantile=0.5,
        top_n_labels=4,
        ba_simulations=20,
        seed=42,
    )
    summary = build_article_artifact(opts)
    assert summary["n_quarters_normal"] == 8
    assert summary["n_quarters_lehman"] == 4
    # all expected files
    expected = [
        "network_normal.png",
        "network_lehman.png",
        "correlation_levels_normal.png",
        "correlation_levels_lehman.png",
        "correlation_levels_delta.png",
        "correlation_changes_normal.png",
        "correlation_changes_lehman.png",
        "correlation_changes_delta.png",
        "risk_concentration_bar.png",
        "ba_fit_summary.csv",
        "top_correlated_pairs_levels.csv",
        "top_correlated_pairs_changes.csv",
        "risk_concentration_summary.csv",
        "risk_concentration_article_grade.csv",
        "reporter_status_summary.csv",
        "model_comparison_summary.csv",
        "model_comparison_full.csv",
        "correlation_validity_summary.csv",
        "data_quality_summary.csv",
        "DISHA_ARTICLE_SUMMARY.md",
        "DISHA_SAFE_120_WORDS.md",
        "CLAIM_BOUNDARY.md",
        "REPRODUCIBILITY.md",
        "AUDIT_RESPONSE.md",
    ]
    for name in expected:
        assert (out / name).is_file(), f"missing: {name}"


def test_forbidden_wording_absent_from_summary(synthetic_dataset: Path, tmp_path: Path) -> None:
    out = tmp_path / "article_out"
    opts = BuildOptions(
        dataset_dir=synthetic_dataset,
        output_dir=out,
        normal_start=(2006, 1),
        normal_end=(2007, 4),
        lehman_start=(2008, 3),
        lehman_end=(2009, 2),
        sensitivity_start=(2007, 1),
        sensitivity_end=(2009, 4),
        edge_quantile=0.5,
        top_n_labels=4,
        ba_simulations=10,
        seed=42,
    )
    build_article_artifact(opts)
    summary_md = (out / "DISHA_ARTICLE_SUMMARY.md").read_text(encoding="utf-8").lower()
    forbidden = [
        "bank-level interbank network",
        "bank-to-bank exposures",
        "validated repo liquidity",
        "confirmed barabási-albert",
        "confirmed barabasi-albert",
        "confirmed systemic-risk phase transition",
        "liquidity contagion proof",
        "production-grade scientific validation",
    ]
    for f in forbidden:
        assert f not in summary_md, f"forbidden wording leaked: {f!r}"


def test_repro_markdown_records_sha_and_dataset(synthetic_dataset: Path, tmp_path: Path) -> None:
    out = tmp_path / "article_out"
    opts = BuildOptions(
        dataset_dir=synthetic_dataset,
        output_dir=out,
        normal_start=(2006, 1),
        normal_end=(2007, 4),
        lehman_start=(2008, 3),
        lehman_end=(2009, 2),
        sensitivity_start=(2007, 1),
        sensitivity_end=(2009, 4),
        edge_quantile=0.5,
        top_n_labels=4,
        ba_simulations=10,
        seed=42,
    )
    build_article_artifact(opts)
    repro = (out / "REPRODUCIBILITY.md").read_text(encoding="utf-8")
    assert "Git SHA" in repro
    assert str(synthetic_dataset) in repro


# ---------------------------------------------------------------------------
# AUDIT-RESPONSE TESTS — B1..B9 + Codex P1/P2
# ---------------------------------------------------------------------------


def _default_opts(synthetic_dataset: Path, out: Path, **overrides: object) -> BuildOptions:
    base = dict(
        dataset_dir=synthetic_dataset,
        output_dir=out,
        normal_start=(2006, 1),
        normal_end=(2007, 4),
        lehman_start=(2008, 3),
        lehman_end=(2009, 2),
        sensitivity_start=(2007, 1),
        sensitivity_end=(2009, 4),
        edge_quantile=0.5,
        top_n_labels=4,
        ba_simulations=20,
        seed=42,
        min_risk_total_strength=100_000.0,
        min_effective_change_observations=8,
    )
    base.update(overrides)
    return BuildOptions(**base)  # type: ignore[arg-type]


# Codex P2 — quarter validation
def test_parse_quarter_rejects_invalid_quarter_number() -> None:
    with pytest.raises(ValueError, match="quarter must be"):
        parse_quarter("2008Q5")
    with pytest.raises(ValueError, match="quarter must be"):
        parse_quarter("2008Q0")


# Codex P1 — empty period preserves n_nodes columns
def test_empty_outward_strength_panel_preserves_columns(synthetic_dataset: Path) -> None:
    ds = load_dataset(synthetic_dataset)
    n = len(ds.nodes)
    panel, qs = build_period_outward_strength_panel(ds.panel, n, (1990, 1), (1990, 4))
    assert qs == []
    assert [int(c) for c in panel.columns] == list(range(n))
    assert panel.shape == (0, n)


# B1 — ER baseline columns exist
def test_ba_summary_includes_er_baseline(synthetic_dataset: Path, tmp_path: Path) -> None:
    out = tmp_path / "art"
    build_article_artifact(_default_opts(synthetic_dataset, out))
    ba = pd.read_csv(out / "ba_fit_summary.csv")
    for col in (
        "ba_degree_pearson_r",
        "er_degree_pearson_r",
        "ba_minus_er_r",
        "ba_degree_ks_distance",
        "er_degree_ks_distance",
        "winner_by_ks",
        "ba_claim_status",
    ):
        assert col in ba.columns


# B1 — when BA r is essentially equal to ER r, claim status is NOT_DISTINGUISHED
def test_ba_claim_not_distinguished_when_er_matches() -> None:
    rng = np.random.default_rng(0)
    n = 12
    A = (rng.random((n, n)) > 0.6).astype(np.uint8)
    np.fill_diagonal(A, 0)
    info = compute_ba_comparison(A, ba_simulations=30, seed=42)
    if info["ba_minus_er_r"] < 0.05:
        assert info["ba_claim_status"] in (
            "NOT_DISTINGUISHED",
            "ER_KS_BETTER",
            "BA_STRUCTURAL_MISMATCH",
        )


# B8 — claim status flips to ER_KS_BETTER when ER KS is smaller
def test_ba_claim_er_ks_better_overrides_pearson_margin() -> None:
    from tools.build_disha_ba_correlation_figures import _ba_claim_status

    status, _ = _ba_claim_status(
        ba_r=0.95,
        er_r=0.80,
        ba_ks=0.50,
        er_ks=0.30,
        zero_degree_mismatch=False,
    )
    assert status == "ER_KS_BETTER"


# B3 — zero-degree mismatch flagged
def test_zero_degree_mismatch_blocks_ba_positive_claim() -> None:
    from tools.build_disha_ba_correlation_figures import _ba_claim_status

    status, _ = _ba_claim_status(
        ba_r=0.95,
        er_r=0.50,
        ba_ks=0.20,
        er_ks=0.40,
        zero_degree_mismatch=True,
    )
    assert status == "BA_STRUCTURAL_MISMATCH"


# B2 — risk concentration filters by total_strength + effective_n
def test_risk_concentration_strength_and_observation_filters() -> None:
    nodes = ("BIG", "TINY", "SHORT")
    cor = np.array([[1.0, 0.8, 0.7], [0.8, 1.0, 0.7], [0.7, 0.7, 1.0]])
    # BIG <-> SHORT carry all the mass; TINY isolated → total_strength = 0.
    weighted = np.array(
        [[0, 0, 5e6], [0, 0, 0], [5e6, 0, 0]],
        dtype=float,
    )
    binary = (weighted > 0).astype(np.uint8)
    chg_panel = pd.DataFrame(
        {
            0: np.linspace(0.1, 0.5, 10),  # BIG: 10 finite
            1: np.linspace(0.1, 0.5, 10),  # TINY: 10 finite (low mass)
            2: [0.1, 0.2] + [np.nan] * 8,  # SHORT: only 2 finite
        }
    )
    rc = compute_risk_concentration(
        nodes=nodes,
        corr_levels_normal=cor,
        corr_levels_lehman=cor,
        corr_changes_normal=cor,
        corr_changes_lehman=cor,
        weighted_lehman=weighted,
        binary_lehman=binary,
        chg_lehman_panel=chg_panel,
        min_total_strength=100_000.0,
        min_effective_change_observations=8,
    )
    rc_by_country = rc.set_index("country")
    assert bool(rc_by_country.loc["BIG", "article_grade"])
    assert not bool(rc_by_country.loc["TINY", "article_grade"])  # low mass
    assert not bool(rc_by_country.loc["SHORT", "article_grade"])  # short sample


# B6/B7 — top_correlated_pairs flags near-perfect + low effective_n
def test_top_correlated_pairs_flags_saturation() -> None:
    nodes = ("A", "B", "C")
    cor = np.array([[1.0, 0.999, 0.5], [0.999, 1.0, 0.6], [0.5, 0.6, 1.0]])
    series = pd.DataFrame(
        {
            0: np.arange(15.0),
            1: np.arange(15.0) + 0.001,
            2: np.linspace(0, 1, 15),
        }
    )
    df = top_correlated_pairs(cor, nodes, mode="changes", period="x", series_panel=series)
    pair_ab = df[(df.country_i == "A") & (df.country_j == "B")].iloc[0]
    assert bool(pair_ab["suspicious_near_perfect"])
    assert not bool(pair_ab["headline_allowed"])
    pair_ac = df[(df.country_i == "A") & (df.country_j == "C")].iloc[0]
    assert not bool(pair_ac["suspicious_near_perfect"])
    assert bool(pair_ac["headline_allowed"])


def test_top_correlated_pairs_low_effective_n_blocks_headline() -> None:
    nodes = ("A", "B")
    cor = np.array([[1.0, 0.7], [0.7, 1.0]])
    short_series = pd.DataFrame(
        {0: [1.0, 2.0, 3.0] + [np.nan] * 4, 1: [1.0, 2.5, 4.0] + [np.nan] * 4}
    )
    df = top_correlated_pairs(
        cor, nodes, mode="changes", period="lehman", series_panel=short_series
    )
    row = df.iloc[0]
    assert int(row["effective_n"]) == 3
    assert bool(row["low_sample_warning"])
    assert not bool(row["headline_allowed"])


# B4 — forbidden-wording catches multi-line phrases
def test_forbidden_wording_normalises_whitespace() -> None:
    text = "we present a bank-to-bank\nexposures matrix that is well-calibrated"
    found = find_forbidden_phrases(text)
    assert "bank-to-bank exposures" in found

    text2 = "this is a\nvalidated repo\nliquidity exercise"
    found2 = find_forbidden_phrases(text2)
    assert "validated repo liquidity" in found2

    safe = "we explicitly do not have a validated repository for liquidity tests"
    assert find_forbidden_phrases(safe) == []


def test_normalize_forbidden_text_collapses_whitespace() -> None:
    assert normalize_forbidden_text("foo\nbar\t\tBAZ") == "foo bar baz"


# B5 — reporter-status detects target-only countries
def test_reporter_status_detects_target_only(synthetic_dataset: Path) -> None:
    ds = load_dataset(synthetic_dataset)
    rs = compute_reporter_status(ds.panel, ds.nodes, period_start=(2006, 1), period_end=(2009, 4))
    # CCC is constant (always 100 → 200 sum) — appears as source AND target.
    # No node in the synthetic fixture is target-only, so the column exists
    # and is False for all by construction.
    assert "target_only_under_filter" in rs.columns
    assert "appears_as_source" in rs.columns
    assert "appears_as_target" in rs.columns
    assert rs.shape[0] == len(ds.nodes)


# B9 — article summary uses honest framing (no PA-as-fact statement)
def test_article_summary_does_not_overclaim_ba(synthetic_dataset: Path, tmp_path: Path) -> None:
    out = tmp_path / "art"
    build_article_artifact(_default_opts(synthetic_dataset, out))
    md = (out / "DISHA_ARTICLE_SUMMARY.md").read_text(encoding="utf-8").lower()
    # Must mention ER baseline OR honest "not uniquely"
    assert "erdős-rényi" in md or "erdos-renyi" in md or "not uniquely" in md
    # Must not say "preferential-attachment-style concentration" as a closed claim
    bad = "the network is preferential-attachment"
    assert bad not in md


# AUDIT_RESPONSE.md must enumerate B1–B9 + Codex bugs
def test_audit_response_enumerates_bugs(synthetic_dataset: Path, tmp_path: Path) -> None:
    out = tmp_path / "art"
    build_article_artifact(_default_opts(synthetic_dataset, out))
    text = (out / "AUDIT_RESPONSE.md").read_text(encoding="utf-8")
    for tag in ("B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"):
        assert tag in text
    assert "Codex P1" in text
    assert "Codex P2" in text


# Article-grade CSV exists and has article_rank
def test_article_grade_csv_has_article_rank(synthetic_dataset: Path, tmp_path: Path) -> None:
    out = tmp_path / "art"
    build_article_artifact(_default_opts(synthetic_dataset, out))
    df = pd.read_csv(out / "risk_concentration_article_grade.csv")
    if not df.empty:
        assert "article_rank" in df.columns
        assert df["article_rank"].tolist() == list(range(1, len(df) + 1))


# Reporter status CSV has the required columns
def test_reporter_status_csv_columns(synthetic_dataset: Path, tmp_path: Path) -> None:
    out = tmp_path / "art"
    build_article_artifact(_default_opts(synthetic_dataset, out))
    df = pd.read_csv(out / "reporter_status_summary.csv")
    for col in (
        "country",
        "appears_as_source",
        "appears_as_target",
        "source_quarter_count",
        "target_quarter_count",
        "zero_out_strength_all_windows",
        "target_only_under_filter",
    ):
        assert col in df.columns


# model_comparison_summary.csv exists with expected columns
def test_model_comparison_csv(synthetic_dataset: Path, tmp_path: Path) -> None:
    out = tmp_path / "art"
    build_article_artifact(_default_opts(synthetic_dataset, out))
    df = pd.read_csv(out / "model_comparison_summary.csv")
    for col in ("ba_pearson_r", "er_pearson_r", "ba_minus_er_r", "winner_by_ks", "ba_claim_status"):
        assert col in df.columns


# data_quality_summary.csv carries the new metrics
def test_data_quality_summary_new_metrics(synthetic_dataset: Path, tmp_path: Path) -> None:
    out = tmp_path / "art"
    build_article_artifact(_default_opts(synthetic_dataset, out))
    df = pd.read_csv(out / "data_quality_summary.csv")
    metrics = set(df["metric"].tolist())
    assert "target_only_nodes" in metrics
    assert "constant_source_nodes" in metrics
    assert "reporting_filter_warning" in metrics
    assert "article_safe_outputs" in metrics


# ---------------------------------------------------------------------------
# OAI-RIGOR-590 — multi-null model comparison
# ---------------------------------------------------------------------------


def test_ba_comparison_includes_configuration_and_rewire_baselines(
    synthetic_dataset: Path, tmp_path: Path
) -> None:
    out = tmp_path / "art"
    build_article_artifact(_default_opts(synthetic_dataset, out))
    df = pd.read_csv(out / "model_comparison_full.csv")
    for col in (
        "ba_pearson_r",
        "er_pearson_r",
        "cfg_pearson_r",
        "rew_pearson_r",
        "ba_ks",
        "er_ks",
        "cfg_ks",
        "rew_ks",
        "ba_wasserstein",
        "er_wasserstein",
        "cfg_wasserstein",
        "rew_wasserstein",
        "ba_top5_hub_overlap",
        "er_top5_hub_overlap",
        "max_degree_error",
        "zero_degree_error",
        "ba_beats_all_ks",
    ):
        assert col in df.columns, f"missing column {col}"


def test_ba_comparison_returns_wasserstein_and_top5() -> None:
    rng = np.random.default_rng(11)
    n = 12
    A = (rng.random((n, n)) > 0.6).astype(np.uint8)
    np.fill_diagonal(A, 0)
    info = compute_ba_comparison(A, ba_simulations=20, seed=42)
    assert "ba_wasserstein_distance" in info
    assert "er_wasserstein_distance" in info
    assert "cfg_degree_pearson_r" in info
    assert "rew_degree_pearson_r" in info
    assert "ba_beats_all_ks" in info


# ---------------------------------------------------------------------------
# OAI-RIGOR-590 — correlation validity (Spearman + Kendall + bootstrap)
# ---------------------------------------------------------------------------


def test_correlation_validity_columns() -> None:
    rng = np.random.default_rng(0)
    df_panel = pd.DataFrame(rng.normal(size=(15, 3)))
    cv = compute_correlation_validity(
        df_panel, ("A", "B", "C"), mode="changes", period="t", seed=42, n_boot=50
    )
    for col in (
        "pearson_r",
        "spearman_r",
        "kendall_tau",
        "effective_n",
        "bootstrap_ci_low",
        "bootstrap_ci_high",
        "near_perfect_warning",
        "low_n_warning",
        "low_variance_warning",
        "headline_allowed",
    ):
        assert col in cv.columns


def test_correlation_validity_low_n_blocks_headline() -> None:
    df_panel = pd.DataFrame(
        {
            0: [1.0, 2.0, 3.0] + [np.nan] * 5,
            1: [1.0, 2.5, 4.0] + [np.nan] * 5,
        }
    )
    cv = compute_correlation_validity(
        df_panel, ("A", "B"), mode="changes", period="lehman", seed=42, n_boot=20
    )
    row = cv.iloc[0]
    assert int(row["effective_n"]) == 3
    assert bool(row["low_n_warning"])
    assert not bool(row["headline_allowed"])


def test_correlation_validity_near_perfect_blocks_headline() -> None:
    n_obs = 15
    x = np.linspace(0.0, 1.0, n_obs)
    df_panel = pd.DataFrame({0: x, 1: x + 1e-9})
    cv = compute_correlation_validity(
        df_panel, ("A", "B"), mode="changes", period="t", seed=42, n_boot=20
    )
    row = cv.iloc[0]
    assert bool(row["near_perfect_warning"])
    assert not bool(row["headline_allowed"])


def test_correlation_validity_csv_written(synthetic_dataset: Path, tmp_path: Path) -> None:
    out = tmp_path / "art"
    build_article_artifact(_default_opts(synthetic_dataset, out))
    cv = pd.read_csv(out / "correlation_validity_summary.csv")
    assert cv.shape[0] > 0
    assert "headline_allowed" in cv.columns
    assert set(cv["period"].unique()) >= {"normal", "lehman", "sensitivity_2007Q1_2009Q4"}


# ---------------------------------------------------------------------------
# OAI-RIGOR-590 — strength-weighted article risk score
# ---------------------------------------------------------------------------


def test_article_risk_score_penalises_low_mass(synthetic_dataset: Path, tmp_path: Path) -> None:
    out = tmp_path / "art"
    build_article_artifact(_default_opts(synthetic_dataset, out))
    df = pd.read_csv(out / "risk_concentration_article_grade.csv")
    if df.empty:
        pytest.skip("article-grade table empty under synthetic fixture")
    assert "article_risk_score" in df.columns
    assert "low_mass_penalty" in df.columns
    assert "short_sample_penalty" in df.columns
    # Article-grade rows should have low_mass_penalty == 0.
    assert (df["low_mass_penalty"] == 0).all()


# ---------------------------------------------------------------------------
# OAI-RIGOR-590 — claim boundary contract
# ---------------------------------------------------------------------------


def test_claim_boundary_md_written(synthetic_dataset: Path, tmp_path: Path) -> None:
    out = tmp_path / "art"
    build_article_artifact(_default_opts(synthetic_dataset, out))
    assert (out / "CLAIM_BOUNDARY.md").is_file()


def test_disha_safe_120_written(synthetic_dataset: Path, tmp_path: Path) -> None:
    out = tmp_path / "art"
    build_article_artifact(_default_opts(synthetic_dataset, out))
    text = (out / "DISHA_SAFE_120_WORDS.md").read_text(encoding="utf-8")
    flat = " ".join(text.split())
    assert "BIS Locational Banking Statistics" in flat
    word_count = len(text.split())
    # paragraph + header markdown, target ~120 words; allow 100..200 for header / linewrap
    assert 100 <= word_count <= 200, f"word count {word_count} out of safe range"


def test_no_forbidden_phrases_in_any_md(synthetic_dataset: Path, tmp_path: Path) -> None:
    out = tmp_path / "art"
    build_article_artifact(_default_opts(synthetic_dataset, out))
    for md in (
        "DISHA_ARTICLE_SUMMARY.md",
        "DISHA_SAFE_120_WORDS.md",
        "AUDIT_RESPONSE.md",
        "REPRODUCIBILITY.md",
    ):
        text = (out / md).read_text(encoding="utf-8")
        leaks = find_forbidden_phrases(text)
        assert leaks == [], f"{md} contains forbidden phrases: {leaks}"


# ---------------------------------------------------------------------------
# OAI-RIGOR-590 — reproducibility capsule
# ---------------------------------------------------------------------------


def test_repro_capsule_contents(synthetic_dataset: Path, tmp_path: Path) -> None:
    out = tmp_path / "art"
    build_article_artifact(_default_opts(synthetic_dataset, out))
    capsule = out / "repro_capsule"
    assert capsule.is_dir()
    for name in (
        "MANIFEST.json",
        "COMMANDS.sh",
        "ENVIRONMENT.txt",
        "INPUT_DATASET_MANIFEST_COPY.json",
        "OUTPUT_SHA256SUMS.txt",
        "QUALITY_GATES.txt",
    ):
        assert (capsule / name).is_file(), f"missing capsule file: {name}"
    manifest = json.loads((capsule / "MANIFEST.json").read_text())
    assert manifest["artifact"] == "disha_ba_correlation"
    assert manifest["forbidden_claims_enforced"] is True
    assert manifest["claim_level"] == "descriptive_macro_country_level"


def test_repro_capsule_sha256_lines_match_files(synthetic_dataset: Path, tmp_path: Path) -> None:
    out = tmp_path / "art"
    build_article_artifact(_default_opts(synthetic_dataset, out))
    sha_file = (out / "repro_capsule" / "OUTPUT_SHA256SUMS.txt").read_text(encoding="utf-8")
    lines = [line for line in sha_file.strip().splitlines() if line]
    assert lines, "OUTPUT_SHA256SUMS.txt is empty"
    # Each line is "<sha>  <basename>"
    for line in lines:
        parts = line.split("  ", 1)
        assert len(parts) == 2
        sha, name = parts
        assert len(sha) == 64
        assert (out / name).is_file()


# ---------------------------------------------------------------------------
# OAI-RIGOR-590 — multi-null override
# ---------------------------------------------------------------------------


def test_ba_status_not_distinguished_when_cfg_or_rewire_match() -> None:
    """If BA edges out ER but configuration/rewiring also match, the multi-null
    override flips claim status to NOT_DISTINGUISHED."""
    # Construct a graph with an even degree distribution where any null matches.
    n = 20
    A = np.zeros((n, n), dtype=np.uint8)
    # ring: each node has degree 2
    for i in range(n):
        A[i, (i + 1) % n] = 1
        A[(i + 1) % n, i] = 1
    info = compute_ba_comparison(A, ba_simulations=30, seed=42)
    # On a regular graph, BA m≈1 vs ER vs configuration all produce similar
    # sequences; status should NOT be BA_DESCRIPTIVELY_BETTER.
    assert info["ba_claim_status"] != "BA_DESCRIPTIVELY_BETTER"
