"""Full test battery for the GeoSync Resurrection Agent.

Covers:
    1. invariants        — every INV_*_* fires on the right input
    2. schema auditor    — OHLC-only detection is exact
    3. feed sentinel     — SubstrateHealth computation end-to-end
    4. state machine     — transition table is a proper subset
    5. provider registry — unconfigured by default, env var flips flag
    6. policy            — RULE_01..RULE_15 deterministic selection
    7. filesystem adapter — real panel read + honest write refusal
    8. main loop         — emits DISCOVER_SOURCES on committed substrate
    9. reporter          — atomic write + replay hash determinism
"""

from __future__ import annotations

import dataclasses
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agent import invariants
from agent.adapters.filesystem import FileSystemSubstrateAdapter
from agent.main import run_once
from agent.models import (
    ActionKind,
    AgentState,
    AssetSchemaReport,
    Priority,
    SourceDescriptor,
    SubstrateHealth,
    SubstrateLabel,
    SubstrateStatus,
    ValidationStatus,
    ValidationVerdict,
)
from agent.modules import feed_sentinel, reporter, schema_auditor
from agent.policy import select_action
from agent.providers import (
    PROVIDER_REGISTRY,
    active_sources,
    all_sources,
    provider_manifest,
)
from agent.state_machine import (
    TRANSITIONS,
    is_legal_transition,
    legal_successors,
)

# ---------------------------------------------------------------- #
# fixtures
# ---------------------------------------------------------------- #


def _ohlc_only_schemas() -> list[AssetSchemaReport]:
    return schema_auditor.audit_panel(["XAUUSD", "USA_500_Index", "SPDR_S_P_500_ETF"])


def _microstructure_schemas() -> list[AssetSchemaReport]:
    """Fully-enriched microstructure: raw bid/ask plus pre-computed spread/ofi."""
    return [
        schema_auditor.audit_asset(
            "BTCUSDT",
            (
                "ts",
                "bid",
                "ask",
                "spread",
                "bid_depth",
                "ask_depth",
                "ofi",
                "trades",
            ),
        ),
        schema_auditor.audit_asset(
            "ETHUSDT",
            ("ts", "bid", "ask", "spread", "bid_depth", "ask_depth", "ofi", "trades"),
        ),
    ]


def _healthy_substrate() -> SubstrateHealth:
    return SubstrateHealth(
        ts=datetime.now(tz=timezone.utc),
        status=SubstrateStatus.LIVE,
        feed_live=True,
        heartbeat_ok=True,
        freshness_minutes=2.0,
        asset_coverage=20,
        gap_count=0,
        nan_rate=0.0,
        duplicate_rate=0.0,
        schema_complete=True,
        precursor_capable_assets=20,
        quality_score=0.95,
        substrate_label=SubstrateLabel.LIVE,
    )


def _configured_source(reachable: bool = True, auth_ok: bool = True) -> SourceDescriptor:
    return SourceDescriptor(
        source_id="fake_vendor",
        provider="synthetic",
        type="rest",
        assets=("BTCUSDT",),
        auth_ok=auth_ok,
        latency_ms=5.0,
        live=True,
        reachable=reachable,
        supports_bid_ask=True,
        supports_depth=True,
        supports_trades=True,
    )


# ---------------------------------------------------------------- #
# 1. invariants
# ---------------------------------------------------------------- #


def test_inv_001_blocks_ohlc_only() -> None:
    r = invariants.inv_001_ohlc_only_blocks_precursor(_ohlc_only_schemas())
    assert r.passed is False
    assert "precursor" in r.reason.lower()


def test_inv_001_passes_on_microstructure() -> None:
    r = invariants.inv_001_ohlc_only_blocks_precursor(_microstructure_schemas())
    assert r.passed is True


def test_inv_002_missing_all_microstructure() -> None:
    r = invariants.inv_002_missing_all_microstructure(_ohlc_only_schemas())
    assert r.passed is False


def test_inv_003_stale_freshness_fails() -> None:
    stale = dataclasses.replace(_healthy_substrate(), freshness_minutes=10000.0)
    assert not invariants.inv_003_freshness(stale).passed


def test_inv_004_nan_policy_strict() -> None:
    with_nan = dataclasses.replace(_healthy_substrate(), nan_rate=0.01)
    assert not invariants.inv_004_nan_policy(with_nan).passed


def test_inv_008_009_reject_on_weak_verdict() -> None:
    verdict = ValidationVerdict(
        IC=0.04,
        p_value=0.5,
        corr_momentum=0.0,
        corr_vol=0.1,
        corr_vix=0.0,
        corr_hyg=0.0,
        lead_capture=0.0,
        substrate_label=SubstrateLabel.LIVE,
        status=ValidationStatus.REJECT,
        reason="weak signal",
    )
    assert not invariants.inv_008_p_value_gate(verdict).passed
    assert not invariants.inv_009_ic_gate(verdict).passed


def test_inv_012_always_passes() -> None:
    r = invariants.inv_012_protectors_override_generators()
    assert r.passed is True
    assert "maintenance" in r.reason.lower()


def test_check_all_composes_full_battery() -> None:
    results = invariants.check_all(
        health=_healthy_substrate(),
        schemas=_microstructure_schemas(),
        verdict=None,
    )
    # Each INV_* gets exactly one result in the returned list.
    names = {r.name for r in results}
    assert len(names) == len(results)
    assert "INV_012_protectors_override_generators" in names


# ---------------------------------------------------------------- #
# 2. schema auditor
# ---------------------------------------------------------------- #


def test_audit_panel_marks_ohlc_close_only() -> None:
    schemas = schema_auditor.audit_panel(["XAUUSD", "USA_500_Index"])
    assert schema_auditor.is_ohlc_close_only(schemas)
    assert all(not s.precursor_capable for s in schemas)


def test_audit_asset_with_real_microstructure() -> None:
    s = schema_auditor.audit_asset(
        "BTCUSDT",
        ("ts", "bid", "ask", "bid_depth", "ask_depth", "trades"),
    )
    assert s.has_bid and s.has_ask and s.has_trades
    assert s.can_derive_spread and s.can_derive_ofi
    assert s.precursor_capable is True


# ---------------------------------------------------------------- #
# 3. feed sentinel / SubstrateHealth
# ---------------------------------------------------------------- #


def test_feed_sentinel_on_close_only_panel() -> None:
    idx = pd.date_range("2024-01-01", periods=120, freq="h", tz="UTC")
    panel = pd.DataFrame(
        np.random.default_rng(0).normal(size=(120, 53)),
        index=idx,
        columns=[f"A{i}" for i in range(53)],
    )
    health = feed_sentinel.compute_health(
        panel, wall_clock_now=idx[-1].to_pydatetime() + timedelta(minutes=5)
    )
    assert health.nan_rate == 0.0
    assert health.asset_coverage == 53
    assert health.substrate_label == SubstrateLabel.LATE_GEOMETRY_ONLY
    assert health.schema_complete is False
    assert health.status in {SubstrateStatus.DEGRADED, SubstrateStatus.DEAD}


def test_feed_sentinel_marks_stale_panel_dead() -> None:
    idx = pd.date_range("2000-01-01", periods=10, freq="D", tz="UTC")
    panel = pd.DataFrame(
        np.arange(10, dtype=float)[:, None] + np.zeros((10, 3)),
        index=idx,
        columns=["A", "B", "C"],
    )
    health = feed_sentinel.compute_health(panel)
    assert health.status == SubstrateStatus.DEAD
    assert health.feed_live is False


# ---------------------------------------------------------------- #
# 4. state machine
# ---------------------------------------------------------------- #


def test_state_machine_has_every_state() -> None:
    # Every AgentState must appear as a key OR as a target of some transition.
    values = set(TRANSITIONS.keys())
    for targets in TRANSITIONS.values():
        values.update(targets)
    assert {s for s in AgentState} <= values


def test_state_machine_no_self_loops_except_dormant_to_abort() -> None:
    # Invariant: a state may re-enter itself ONLY via DEGRADED→DORMANT bounce.
    for src, dsts in TRANSITIONS.items():
        assert src not in dsts, f"self-loop not allowed on {src}"


def test_state_machine_transition_helpers() -> None:
    assert is_legal_transition(AgentState.BOOT, AgentState.DISCOVER_SOURCES)
    assert not is_legal_transition(AgentState.BOOT, AgentState.VALIDATE)
    succ = legal_successors(AgentState.REPORT)
    assert AgentState.CHECK_LIVENESS in succ


# ---------------------------------------------------------------- #
# 5. provider registry
# ---------------------------------------------------------------- #


def test_provider_registry_has_seven_candidates() -> None:
    assert len(PROVIDER_REGISTRY) == 7
    ids = {p.source_id for p in PROVIDER_REGISTRY}
    expected = {
        "dukascopy_historical",
        "oanda_v20",
        "databento",
        "polygon_io",
        "interactive_brokers",
        "binance_futures",
        "askar_ots_raw_l2",
    }
    assert ids == expected


def test_provider_registry_default_unconfigured() -> None:
    for env_var in (
        "DUKASCOPY_DOWNLOAD_DIR",
        "OANDA_API_TOKEN",
        "DATABENTO_API_KEY",
        "POLYGON_API_KEY",
        "IBKR_GATEWAY_HOST",
        "BINANCE_WS_ENDPOINT",
        "ASKAR_L2_ENDPOINT",
    ):
        os.environ.pop(env_var, None)
    assert len(active_sources()) == 0
    manifest = provider_manifest()
    assert manifest["total"] == 7
    assert manifest["configured"] == 0


def test_provider_registry_env_var_flips_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUKASCOPY_DOWNLOAD_DIR", "/tmp/duk")
    sources = active_sources()
    assert any(s.source_id == "dukascopy_historical" for s in sources)
    all_s = all_sources()
    duk = next(s for s in all_s if s.source_id == "dukascopy_historical")
    assert duk.auth_ok is True


# ---------------------------------------------------------------- #
# 6. policy
# ---------------------------------------------------------------- #


def test_policy_emits_discover_when_no_sources() -> None:
    intent = select_action(
        sources=[],
        health=None,
        schemas=_ohlc_only_schemas(),
    )
    assert intent.action == ActionKind.DISCOVER_SOURCES
    assert intent.priority == Priority.P0
    assert intent.substrate_status == SubstrateStatus.DEAD
    assert any("DUKASCOPY_DOWNLOAD_DIR" in c for c in intent.blocking_conditions)


def test_policy_emits_check_connectivity_when_unreachable() -> None:
    intent = select_action(
        sources=[_configured_source(reachable=False)],
        health=None,
        schemas=_ohlc_only_schemas(),
    )
    assert intent.action == ActionKind.CHECK_CONNECTIVITY


def test_policy_emits_discover_on_ohlc_only_even_with_source() -> None:
    intent = select_action(
        sources=[_configured_source()],
        health=_healthy_substrate(),
        schemas=_ohlc_only_schemas(),
    )
    # schema_complete was True on the fake health, but schemas themselves are
    # OHLC-only → policy must route back to DISCOVER_SOURCES for precursor feeds
    assert intent.action == ActionKind.DISCOVER_SOURCES
    assert "LATE_GEOMETRY_ONLY" not in intent.target  # target = "precursor_feeds"
    assert "OHLC" in " ".join(intent.why) or "close" in " ".join(intent.why).lower()


def test_policy_emits_report_review_ready_on_full_pass() -> None:
    verdict = ValidationVerdict(
        IC=0.12,
        p_value=0.01,
        corr_momentum=0.02,
        corr_vol=0.05,
        corr_vix=0.01,
        corr_hyg=0.01,
        lead_capture=0.7,
        substrate_label=SubstrateLabel.LIVE,
        status=ValidationStatus.PASS,
        reason="all gates green",
    )
    intent = select_action(
        sources=[_configured_source()],
        health=_healthy_substrate(),
        schemas=_microstructure_schemas(),
        verdict=verdict,
    )
    assert intent.action == ActionKind.REPORT
    assert intent.diagnostics.get("status_note") == "REVIEW_READY"


def test_policy_dormant_when_invariants_fail_even_with_pass_verdict() -> None:
    # Stale health + passing verdict → must NOT upgrade, must DORMANT
    stale_health = dataclasses.replace(_healthy_substrate(), nan_rate=0.05)  # INV_004 violation
    verdict = ValidationVerdict(
        IC=0.20,
        p_value=0.001,
        corr_momentum=0.0,
        corr_vol=0.0,
        corr_vix=0.0,
        corr_hyg=0.0,
        lead_capture=0.8,
        substrate_label=SubstrateLabel.LIVE,
        status=ValidationStatus.PASS,
        reason="ok",
    )
    intent = select_action(
        sources=[_configured_source()],
        health=stale_health,
        schemas=_microstructure_schemas(),
        verdict=verdict,
    )
    assert intent.action == ActionKind.DORMANT
    assert intent.admissible is False


# ---------------------------------------------------------------- #
# 7. filesystem adapter
# ---------------------------------------------------------------- #


def test_filesystem_adapter_refuses_writes() -> None:
    adapter = FileSystemSubstrateAdapter(Path("/tmp/nonexistent.parquet"))
    with pytest.raises(NotImplementedError):
        adapter.collect()
    with pytest.raises(NotImplementedError):
        adapter.backfill()
    with pytest.raises(NotImplementedError):
        adapter.enrich()


def test_filesystem_adapter_handles_missing_panel() -> None:
    adapter = FileSystemSubstrateAdapter(Path("/tmp/definitely_missing.parquet"))
    health = adapter.get_health()
    # Empty panel → asset_coverage 0, schema incomplete, status DEAD
    # (freshness uses DEAD_FRESHNESS_SENTINEL — finite, JSON-safe)
    assert health.asset_coverage == 0
    assert health.status == SubstrateStatus.DEAD


# ---------------------------------------------------------------- #
# Codex P1 — hard-stop invariants short-circuit BEFORE any rule
# ---------------------------------------------------------------- #


def test_policy_hard_stops_on_nan_invariant_without_verdict() -> None:
    """INV_004 (nan_rate > 0) must DORMANT the agent even with no verdict
    and otherwise-healthy substrate, sources, and microstructure schemas."""
    nan_health = dataclasses.replace(_healthy_substrate(), nan_rate=0.001)
    intent = select_action(
        sources=[_configured_source()],
        health=nan_health,
        schemas=_microstructure_schemas(),
        verdict=None,
    )
    assert intent.action == ActionKind.DORMANT
    assert intent.admissible is False
    assert intent.priority == Priority.P0
    assert any("INV_004" in w for w in intent.why)


def test_policy_hard_stops_on_missing_audit_artifact() -> None:
    """INV_010 (missing audit artefacts) must DORMANT regardless of verdict."""
    intent = select_action(
        sources=[_configured_source()],
        health=_healthy_substrate(),
        schemas=_microstructure_schemas(),
        verdict=None,
        missing_artifacts=["validation_verdict.json"],
    )
    assert intent.action == ActionKind.DORMANT
    assert intent.admissible is False
    assert "INV_010" in " ".join(intent.why)


def test_policy_does_not_hard_stop_when_only_verdict_invariants_fail() -> None:
    """Verdict-only invariants (006/007/008/009) must NOT trigger the
    hard-stop pre-check when verdict is None — they only matter inside
    the verdict-handling branch."""
    intent = select_action(
        sources=[_configured_source()],
        health=_healthy_substrate(),
        schemas=_microstructure_schemas(),
        verdict=None,
    )
    # No hard stop → policy advances to BUILD_FEATURES (RULE_08).
    assert intent.action == ActionKind.BUILD_FEATURES
    assert intent.admissible is True


# ---------------------------------------------------------------- #
# Codex P2 — JSON-safe freshness sentinel (no float('inf'))
# ---------------------------------------------------------------- #


def test_empty_panel_freshness_is_json_safe() -> None:
    """compute_health on an empty panel must NOT produce float('inf')."""
    empty = pd.DataFrame()
    health = feed_sentinel.compute_health(empty)
    assert np.isfinite(health.freshness_minutes)
    assert health.freshness_minutes > 0
    assert health.status == SubstrateStatus.DEAD
    # Round-trip through stdlib json: would raise on Infinity if present.
    payload = health.to_dict()
    encoded = json.dumps(payload, allow_nan=False)
    decoded = json.loads(encoded)
    assert decoded["status"] == "DEAD"
    assert np.isfinite(decoded["freshness_minutes"])


# ---------------------------------------------------------------- #
# 8. main loop
# ---------------------------------------------------------------- #


def test_main_run_once_on_committed_panel_emits_discover_sources() -> None:
    panel = Path("data/askar_full/panel_hourly.parquet")
    if not panel.exists():
        pytest.skip("committed panel not staged")
    for env_var in (
        "DUKASCOPY_DOWNLOAD_DIR",
        "OANDA_API_TOKEN",
        "DATABENTO_API_KEY",
        "POLYGON_API_KEY",
        "IBKR_GATEWAY_HOST",
        "BINANCE_WS_ENDPOINT",
        "ASKAR_L2_ENDPOINT",
    ):
        os.environ.pop(env_var, None)

    intent = run_once(panel_path=panel)
    assert intent.action == ActionKind.DISCOVER_SOURCES
    assert intent.substrate_status == SubstrateStatus.DEAD
    assert intent.priority == Priority.P0

    # Sidecar audit artefacts must exist after the run.
    for name in (
        "provider_manifest.json",
        "substrate_health.json",
        "schema_audit.json",
        "action_intent.json",
        "replay_hash.sha256",
    ):
        assert (Path("agent/reports") / name).exists()


# ---------------------------------------------------------------- #
# 9. reporter
# ---------------------------------------------------------------- #


def test_reporter_hash_is_deterministic(tmp_path: Path) -> None:
    payload_a = {"action": "REPORT", "state": "REPORT"}
    payload_b = {"state": "REPORT", "action": "REPORT"}  # reordered keys
    h1 = reporter.emit_replay_hash(payload_a)
    h2 = reporter.emit_replay_hash(payload_b)
    assert h1 == h2  # JSON is dumped sort_keys=True
    assert len(h1) == 64


def test_reporter_write_report_roundtrip(tmp_path: Path) -> None:
    # write_report writes into the fixed REPORTS_DIR; round-trip check.
    reporter.write_report("_roundtrip_test.json", {"ok": True})
    out = reporter.REPORTS_DIR / "_roundtrip_test.json"
    assert out.exists()
    loaded = json.loads(out.read_text())
    assert loaded == {"ok": True}
    out.unlink()
