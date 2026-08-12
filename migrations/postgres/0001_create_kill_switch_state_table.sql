-- SPDX-License-Identifier: MIT
-- Migration: Create kill_switch_state table for Postgres-backed kill-switch store.

BEGIN;

CREATE TABLE IF NOT EXISTS kill_switch_state (
    id SMALLINT PRIMARY KEY CHECK (id = 1),
    engaged BOOLEAN NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kill_switch_state_updated_at
    ON kill_switch_state (updated_at);

COMMIT;
