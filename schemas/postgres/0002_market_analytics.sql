-- Trading analytics, indicator, and logging schema extensions
-- This script is idempotent and can be re-applied safely.

BEGIN;

-- Enumerated types ----------------------------------------------------------

CREATE TYPE IF NOT EXISTS candle_interval AS ENUM (
    '1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1mo'
);

CREATE TYPE IF NOT EXISTS log_level AS ENUM (
    'trace', 'debug', 'info', 'warn', 'error', 'fatal'
);

-- Trade history -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS trade_history_candle (
    candle_id          BIGSERIAL PRIMARY KEY,
    instrument_id      BIGINT NOT NULL REFERENCES instrument(instrument_id) DEFERRABLE INITIALLY IMMEDIATE,
    interval           candle_interval NOT NULL,
    open_time          TIMESTAMPTZ NOT NULL,
    close_time         TIMESTAMPTZ NOT NULL,
    open_price         NUMERIC(28,10) NOT NULL CHECK (open_price > 0),
    high_price         NUMERIC(28,10) NOT NULL CHECK (high_price > 0),
    low_price          NUMERIC(28,10) NOT NULL CHECK (low_price > 0),
    close_price        NUMERIC(28,10) NOT NULL CHECK (close_price > 0),
    volume             NUMERIC(28,10) NOT NULL DEFAULT 0 CHECK (volume >= 0),
    trade_count        BIGINT NOT NULL DEFAULT 0 CHECK (trade_count >= 0),
    vwap               NUMERIC(28,10),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (open_time < close_time),
    CHECK (
        (close_time - open_time) =
            CASE interval
                WHEN '1m' THEN INTERVAL '1 minute'
                WHEN '5m' THEN INTERVAL '5 minutes'
                WHEN '15m' THEN INTERVAL '15 minutes'
                WHEN '30m' THEN INTERVAL '30 minutes'
                WHEN '1h' THEN INTERVAL '1 hour'
                WHEN '4h' THEN INTERVAL '4 hours'
                WHEN '1d' THEN INTERVAL '1 day'
                WHEN '1w' THEN INTERVAL '1 week'
                WHEN '1mo' THEN INTERVAL '1 month'
            END
    ),
    CHECK (low_price <= high_price),
    CHECK (high_price >= GREATEST(open_price, close_price)),
    CHECK (low_price <= LEAST(open_price, close_price)),
    CHECK (vwap IS NULL OR vwap > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS trade_history_candle_unique
    ON trade_history_candle (instrument_id, interval, open_time);

CREATE INDEX IF NOT EXISTS trade_history_candle_interval_time_idx
    ON trade_history_candle (interval, open_time DESC);

-- Indicator data ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS indicator_series (
    indicator_id       BIGSERIAL PRIMARY KEY,
    instrument_id      BIGINT NOT NULL REFERENCES instrument(instrument_id) DEFERRABLE INITIALLY IMMEDIATE,
    indicator_name     TEXT NOT NULL,
    interval           candle_interval,
    parameters         JSONB NOT NULL DEFAULT '{}'::jsonb,
    description        TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (instrument_id, indicator_name, interval, parameters)
);

CREATE TABLE IF NOT EXISTS indicator_datapoint (
    indicator_id       BIGINT NOT NULL REFERENCES indicator_series(indicator_id) ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE,
    as_of              TIMESTAMPTZ NOT NULL,
    value              JSONB NOT NULL,
    calculated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (indicator_id, as_of)
);

CREATE INDEX IF NOT EXISTS indicator_datapoint_recent_idx
    ON indicator_datapoint (indicator_id, calculated_at DESC);

-- Logging -------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS system_log (
    log_id             BIGSERIAL PRIMARY KEY,
    source_component   TEXT NOT NULL,
    log_level          log_level NOT NULL,
    message            TEXT NOT NULL,
    context            JSONB,
    account_id         BIGINT REFERENCES trading_account(account_id) DEFERRABLE INITIALLY IMMEDIATE,
    instrument_id      BIGINT REFERENCES instrument(instrument_id) DEFERRABLE INITIALLY IMMEDIATE,
    correlation_id     UUID,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS system_log_level_time_idx
    ON system_log (log_level, created_at DESC);

CREATE INDEX IF NOT EXISTS system_log_account_time_idx
    ON system_log (account_id, created_at DESC) WHERE account_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS system_log_instrument_time_idx
    ON system_log (instrument_id, created_at DESC) WHERE instrument_id IS NOT NULL;

COMMIT;
