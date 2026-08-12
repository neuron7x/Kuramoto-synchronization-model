# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The mutable-state registry must stay bound to real code + tests.

A covered system can still lie if state is stale, loses updates, or is served out
of order. ``artifacts/state/mutable_state_registry.json`` declares, for every
mutable runtime surface, its owner/key/ordering/write/read/conflict/staleness rule,
concurrency guard, and the tests that prove them. This gate keeps the declaration
honest: schema-valid, every source + test file exists, concurrent surfaces name a
real guard, cache surfaces name a stale-read policy, and the known-mutable
surfaces are all registered (so a new one cannot be added without a route here).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "artifacts" / "state" / "mutable_state_registry.json"
SCHEMA = ROOT / "audit" / "schema" / "mutable_state_registry.schema.json"

# Known mutable runtime surfaces that MUST be registered (route-or-fail). Adding a
# new mutable surface without registering it here should trip test #6.
REQUIRED_SOURCES = frozenset(
    {
        "core/features/realtime_store.py",
        "execution/risk/core.py",
        "core/messaging/event_bus.py",
        "execution/order_ledger.py",
        "core/idempotency/keys.py",
        "libs/db/session.py",
        "libs/db/repository.py",
        "modules/data_quality_monitor.py",
        "modules/strategy_scheduler.py",
    }
)

_CONCURRENT_GUARD_TOKENS = ("Lock", "RLock", "CAS", "event loop", "task")


def _registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_registry_validates_against_schema() -> None:
    registry = _registry()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert registry["schema"] == schema["$id"]
    assert registry["verdict"] == "BOUND"
    assert isinstance(registry["components"], list) and registry["components"]
    try:
        import jsonschema
    except ImportError:
        return
    jsonschema.validate(registry, schema)


def test_every_component_has_a_test() -> None:
    for comp in _registry()["components"]:
        assert comp["tests"], f"{comp['component']} has no test"


def test_ordering_states_declare_the_ordering_in_their_rules() -> None:
    for comp in _registry()["components"]:
        field = comp["ordering_field"]
        if field is None:
            continue
        blob = " ".join(
            [comp["write_rule"], comp["read_rule"], comp["conflict_rule"], comp["staleness_rule"]]
        )
        assert field in blob, (
            f"{comp['component']} declares ordering_field {field!r} but no rule references it"
        )


def test_concurrent_states_name_a_real_guard() -> None:
    for comp in _registry()["components"]:
        if not comp["concurrent"]:
            continue
        guard = comp["concurrency_guard"]
        assert any(tok in guard for tok in _CONCURRENT_GUARD_TOKENS), (
            f"{comp['component']} is concurrent but its guard names no mechanism: {guard!r}"
        )


def test_cache_states_have_a_stale_read_policy() -> None:
    for comp in _registry()["components"]:
        if not comp["is_cache"]:
            continue
        rule = comp["staleness_rule"].lower()
        assert "ttl" in rule or "stale" in rule or "older" in rule, (
            f"{comp['component']} is a cache but its staleness_rule is vacuous: {rule!r}"
        )


def test_every_source_and_test_file_exists() -> None:
    for comp in _registry()["components"]:
        assert (ROOT / comp["source"]).is_file(), f"missing source: {comp['source']}"
        for test_file in comp["tests"]:
            assert (ROOT / test_file).is_file(), f"missing test file: {test_file}"


def test_all_known_mutable_surfaces_are_registered() -> None:
    registered = {comp["source"] for comp in _registry()["components"]}
    missing = REQUIRED_SOURCES - registered
    assert not missing, f"mutable runtime surfaces not registered: {sorted(missing)}"


def test_state_owner_class_exists_in_source() -> None:
    for comp in _registry()["components"]:
        text = (ROOT / comp["source"]).read_text(encoding="utf-8")
        assert f"class {comp['state_owner']}" in text, (
            f"{comp['component']}: state_owner {comp['state_owner']!r} not a class in {comp['source']}"
        )
