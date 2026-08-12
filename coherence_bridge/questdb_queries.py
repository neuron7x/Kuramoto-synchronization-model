"""QuestDB query library for CoherenceBridge + OTS backtesting.

Provides pre-built SQL queries for:
  1. ASOF JOIN: orderbook snapshots ↔ regime signals (timestamp-aligned)
  2. Regime transition detection (state changes)
  3. Feature aggregation windows (for ML training)
  4. Risk analysis (drawdown per regime)
  5. Signal quality metrics (coverage, latency)

These queries assume:
  - coherence_signals table (written by QuestDBSignalWriter)
  - orderbook_snapshots table (written by Askar's CryptoFlowApp/OTP)
  - regime_ml_features table (written by RegimeFeatureExporter)

Execute via QuestDB PGWire (port 8812) or HTTP (port 9000/exec).
"""

from __future__ import annotations

# ── 1. ASOF JOIN: sync orderbook with regime signals ──────────────

ASOF_JOIN_SIGNALS_ORDERBOOK = """
SELECT
    ob.timestamp,
    ob.instrument,
    ob.bid_price, ob.ask_price,
    ob.bid_volume, ob.ask_volume,
    (ob.bid_volume - ob.ask_volume) / (ob.bid_volume + ob.ask_volume + 1e-12) AS obi,
    cs.gamma,
    cs.order_parameter_R,
    cs.ricci_curvature,
    cs.lyapunov_max,
    cs.regime,
    cs.regime_confidence,
    cs.signal_strength,
    cs.risk_scalar
FROM orderbook_snapshots ob
ASOF JOIN coherence_signals cs ON (ob.instrument = cs.instrument)
WHERE ob.timestamp BETWEEN '{start}' AND '{end}'
    AND ob.instrument = '{instrument}'
ORDER BY ob.timestamp
""".strip()

# ── 2. Regime transitions ─────────────────────────────────────────

REGIME_TRANSITIONS = """
WITH regimes AS (
    SELECT
        timestamp,
        instrument,
        regime,
        LAG(regime) OVER (PARTITION BY instrument ORDER BY timestamp) AS prev_regime
    FROM coherence_signals
    WHERE timestamp BETWEEN '{start}' AND '{end}'
        AND instrument = '{instrument}'
)
SELECT timestamp, instrument, prev_regime, regime
FROM regimes
WHERE regime != prev_regime
ORDER BY timestamp
""".strip()

# ── 3. Feature windows for ML training ────────────────────────────

FEATURE_WINDOW_STATS = """
SELECT
    instrument,
    regime,
    COUNT(*) AS n_samples,
    AVG(gamma) AS avg_gamma,
    AVG(order_parameter_R) AS avg_R,
    AVG(ricci_curvature) AS avg_ricci,
    AVG(lyapunov_max) AS avg_lyapunov,
    AVG(risk_scalar) AS avg_risk,
    MIN(risk_scalar) AS min_risk,
    MAX(risk_scalar) AS max_risk,
    AVG(regime_confidence) AS avg_confidence
FROM coherence_signals
WHERE timestamp BETWEEN '{start}' AND '{end}'
    AND instrument = '{instrument}'
GROUP BY instrument, regime
ORDER BY n_samples DESC
""".strip()

# ── 4. Drawdown analysis per regime ───────────────────────────────

REGIME_PERFORMANCE = """
SELECT
    cs.regime,
    COUNT(*) AS n_bars,
    AVG(cs.risk_scalar) AS avg_risk_scalar,
    AVG(cs.gamma) AS avg_gamma,
    AVG(ob.mid_return) AS avg_return,
    SUM(CASE WHEN ob.mid_return < 0 THEN ob.mid_return ELSE 0 END) AS total_drawdown,
    MAX(ob.mid_return) AS max_gain,
    MIN(ob.mid_return) AS max_loss
FROM coherence_signals cs
ASOF JOIN (
    SELECT
        timestamp,
        instrument,
        (ask_price + bid_price) / 2 AS mid,
        ((ask_price + bid_price) / 2 - LAG((ask_price + bid_price) / 2)
            OVER (PARTITION BY instrument ORDER BY timestamp))
            / LAG((ask_price + bid_price) / 2)
            OVER (PARTITION BY instrument ORDER BY timestamp) AS mid_return
    FROM orderbook_snapshots
) ob ON (cs.instrument = ob.instrument)
WHERE cs.timestamp BETWEEN '{start}' AND '{end}'
    AND cs.instrument = '{instrument}'
GROUP BY cs.regime
""".strip()

# ── 5. Signal quality metrics ─────────────────────────────────────

SIGNAL_COVERAGE = """
SELECT
    instrument,
    COUNT(*) AS total_signals,
    MIN(timestamp) AS first_signal,
    MAX(timestamp) AS last_signal,
    datediff('s', MIN(timestamp), MAX(timestamp)) / COUNT(*) AS avg_interval_s,
    COUNT(DISTINCT regime) AS regimes_seen,
    SUM(CASE WHEN risk_scalar = 0 THEN 1 ELSE 0 END) AS zero_risk_count,
    AVG(regime_confidence) AS avg_confidence
FROM coherence_signals
WHERE timestamp BETWEEN '{start}' AND '{end}'
GROUP BY instrument
""".strip()

# ── 6. ASOF JOIN with ML features ─────────────────────────────────

ASOF_JOIN_ML_FEATURES = """
SELECT
    ob.timestamp,
    ob.instrument,
    ob.bid_price, ob.ask_price,
    rf.gamma_distance,
    rf.r_coherence,
    rf.ricci_sign,
    rf.lyapunov_sign,
    rf.regime_encoded,
    rf.regime_confidence,
    rf.risk_scalar
FROM orderbook_snapshots ob
ASOF JOIN regime_ml_features rf ON (ob.instrument = rf.instrument)
WHERE ob.timestamp BETWEEN '{start}' AND '{end}'
    AND ob.instrument = '{instrument}'
ORDER BY ob.timestamp
""".strip()


def format_query(query: str, **kwargs: str) -> str:
    """Format a query template with parameters.

    Parameters are inserted via str.format() — NOT SQL injection safe
    for untrusted input. Use only with validated instrument names and dates.
    """
    return query.format(**kwargs)
