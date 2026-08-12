"""Tests for QuestDB query library."""

from coherence_bridge.questdb_queries import (
    ASOF_JOIN_ML_FEATURES,
    ASOF_JOIN_SIGNALS_ORDERBOOK,
    FEATURE_WINDOW_STATS,
    REGIME_PERFORMANCE,
    REGIME_TRANSITIONS,
    SIGNAL_COVERAGE,
    format_query,
)


def test_asof_join_formats_correctly() -> None:
    q = format_query(
        ASOF_JOIN_SIGNALS_ORDERBOOK,
        start="2024-01-01",
        end="2024-12-31",
        instrument="EURUSD",
    )
    assert "EURUSD" in q
    assert "2024-01-01" in q
    assert "ASOF JOIN" in q


def test_regime_transitions_has_lag() -> None:
    q = format_query(
        REGIME_TRANSITIONS,
        start="2024-01-01",
        end="2024-12-31",
        instrument="EURUSD",
    )
    assert "LAG" in q
    assert "prev_regime" in q


def test_all_queries_are_non_empty_strings() -> None:
    for name, query in [
        ("ASOF_JOIN_SIGNALS_ORDERBOOK", ASOF_JOIN_SIGNALS_ORDERBOOK),
        ("REGIME_TRANSITIONS", REGIME_TRANSITIONS),
        ("FEATURE_WINDOW_STATS", FEATURE_WINDOW_STATS),
        ("REGIME_PERFORMANCE", REGIME_PERFORMANCE),
        ("SIGNAL_COVERAGE", SIGNAL_COVERAGE),
        ("ASOF_JOIN_ML_FEATURES", ASOF_JOIN_ML_FEATURES),
    ]:
        assert len(query) > 50, f"{name} is too short"
        assert "SELECT" in query, f"{name} missing SELECT"


def test_ml_features_query_has_correct_columns() -> None:
    q = format_query(
        ASOF_JOIN_ML_FEATURES,
        start="2024-01-01",
        end="2024-12-31",
        instrument="EURUSD",
    )
    for col in [
        "gamma_distance",
        "r_coherence",
        "ricci_sign",
        "lyapunov_sign",
        "regime_encoded",
    ]:
        assert col in q, f"Missing ML feature column: {col}"
