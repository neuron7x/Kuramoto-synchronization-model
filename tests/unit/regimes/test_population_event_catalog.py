"""Tests for ``geosync_hpc.regimes.population_event_catalog`` (P1).

Contract under test:

  Catalog admission is NOT prediction. A cataloged event is an
  evidence-bearing record. The witness names the verdict and the reason
  with no prediction / signal / score / recommendation field.

This file ships the ten tests required by the PR-2 brief plus a small
group of structural assertions that protect the contract from drift:

  1.  valid event accepted
  2.  duplicate event rejected
  3.  empty asset universe rejected
  4.  invalid timestamp rejected (naive datetime)
  5.  invalid source window rejected (start >= end; or timestamp out of window)
  6.  NaN/inf feature rejected
  7.  unsupported evidence tier rejected
  8.  cataloging does not imply prediction
       (witness type carries no prediction-class field)
  9.  deterministic ordering by (timestamp, event_id)
  10. serialization round-trip preserves catalog content

Plus auxiliary structural tests that ensure the failure modes named in
the brief are individually catchable.
"""

from __future__ import annotations

import math
from copy import copy
from dataclasses import fields
from datetime import datetime, timedelta, timezone

import pytest

from geosync_hpc.regimes.population_event_catalog import (
    AdmissionWitness,
    EventInput,
    EvidenceTier,
    PopulationEventCatalog,
    SourceWindow,
)

UTC = timezone.utc


def _good_window() -> SourceWindow:
    return SourceWindow(
        start=datetime(2026, 4, 26, 0, 0, tzinfo=UTC),
        end=datetime(2026, 4, 26, 1, 0, tzinfo=UTC),
    )


def _good_event(
    *,
    event_id: str = "evt_001",
    timestamp: datetime | None = None,
    asset_universe: tuple[str, ...] = ("BTC-USD", "ETH-USD"),
    regime_label: str = "trend_up",
    event_features: dict[str, float] | None = None,
    evidence_tier: EvidenceTier = EvidenceTier.PRIMARY,
    source_window: SourceWindow | None = None,
    provenance: str = "ingest_pipeline:v1.2.3",
    falsifier_status: str = "OK",
) -> EventInput:
    return EventInput(
        event_id=event_id,
        timestamp=timestamp or datetime(2026, 4, 26, 0, 30, tzinfo=UTC),
        asset_universe=asset_universe,
        regime_label=regime_label,
        event_features=event_features or {"volatility": 0.18, "drawdown": -0.04},
        evidence_tier=evidence_tier,
        source_window=source_window or _good_window(),
        provenance=provenance,
        falsifier_status=falsifier_status,
    )


# ---------------------------------------------------------------------------
# 1. valid event accepted
# ---------------------------------------------------------------------------


def test_valid_event_is_accepted() -> None:
    catalog = PopulationEventCatalog()
    verdict = catalog.admit(_good_event())
    assert verdict.accepted is True
    assert verdict.event_id == "evt_001"
    assert verdict.reason == "OK"
    assert verdict.evidence_tier == EvidenceTier.PRIMARY
    assert verdict.falsifier_status == "OK"
    assert verdict.catalog_size_after == 1
    assert "evt_001" in catalog


# ---------------------------------------------------------------------------
# 2. duplicate event rejected
# ---------------------------------------------------------------------------


def test_duplicate_event_is_rejected_and_state_unchanged() -> None:
    catalog = PopulationEventCatalog()
    first = catalog.admit(_good_event(event_id="evt_dup"))
    assert first.accepted is True
    second = catalog.admit(_good_event(event_id="evt_dup"))
    assert second.accepted is False
    assert second.reason == "DUPLICATE_EVENT_ID"
    assert second.evidence_tier is None
    assert second.falsifier_status is None
    assert second.catalog_size_after == 1
    # Catalog state must not grow on rejection.
    assert len(catalog) == 1


# ---------------------------------------------------------------------------
# 3. empty asset universe rejected
# ---------------------------------------------------------------------------


def test_empty_asset_universe_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="asset_universe must be a non-empty"):
        _good_event(asset_universe=())


def test_asset_universe_with_empty_string_rejected() -> None:
    with pytest.raises(ValueError, match="asset_universe entries"):
        _good_event(asset_universe=("BTC-USD", ""))


# ---------------------------------------------------------------------------
# 4. invalid timestamp rejected (naive datetime)
# ---------------------------------------------------------------------------


def test_naive_timestamp_rejected_at_construction() -> None:
    naive = datetime(2026, 4, 26, 0, 30)  # no tzinfo
    with pytest.raises(ValueError, match="timestamp must be timezone-aware"):
        _good_event(timestamp=naive)


def test_non_datetime_timestamp_rejected() -> None:
    with pytest.raises(TypeError, match="timestamp must be a datetime"):
        EventInput(
            event_id="x",
            timestamp="2026-04-26T00:30:00+00:00",  # type: ignore[arg-type]
            asset_universe=("BTC-USD",),
            regime_label="r",
            event_features={"x": 0.0},
            evidence_tier=EvidenceTier.PRIMARY,
            source_window=_good_window(),
            provenance="p",
            falsifier_status="OK",
        )


# ---------------------------------------------------------------------------
# 5. invalid source window rejected (start >= end; or timestamp out of window)
# ---------------------------------------------------------------------------


def test_source_window_with_start_after_end_rejected() -> None:
    start = datetime(2026, 4, 26, 1, 0, tzinfo=UTC)
    end = datetime(2026, 4, 26, 0, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="strictly before"):
        SourceWindow(start=start, end=end)


def test_source_window_with_naive_endpoints_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SourceWindow(
            start=datetime(2026, 4, 26, 0, 0),  # naive
            end=datetime(2026, 4, 26, 1, 0),  # naive
        )


def test_timestamp_outside_source_window_rejected() -> None:
    window = _good_window()
    out_of_window = window.end + timedelta(minutes=5)
    with pytest.raises(ValueError, match="timestamp must lie within source_window"):
        _good_event(timestamp=out_of_window, source_window=window)


# ---------------------------------------------------------------------------
# 6. NaN/inf feature rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_value",
    [float("nan"), float("inf"), float("-inf")],
)
def test_non_finite_feature_rejected(bad_value: float) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        _good_event(event_features={"vol": bad_value})


def test_non_numeric_feature_value_rejected() -> None:
    with pytest.raises(TypeError, match="finite numeric value"):
        _good_event(event_features={"vol": "0.18"})  # type: ignore[dict-item]


def test_boolean_feature_value_rejected() -> None:
    """Booleans are subclasses of int in Python; admit them on purpose
    surfaces a typo-class regression."""
    with pytest.raises(TypeError, match="finite numeric value"):
        _good_event(event_features={"flag": True})


# ---------------------------------------------------------------------------
# 7. unsupported evidence tier rejected
# ---------------------------------------------------------------------------


def test_unsupported_evidence_tier_string_rejected_via_enum_validator() -> None:
    """The dataclass requires an `EvidenceTier`; constructing one from a
    string outside the enum surfaces immediately."""
    with pytest.raises(ValueError):
        EvidenceTier("UNKNOWN_TIER")


def test_passing_raw_string_to_event_input_is_rejected() -> None:
    with pytest.raises(TypeError, match="evidence_tier must be a EvidenceTier"):
        EventInput(
            event_id="evt_bad_tier",
            timestamp=datetime(2026, 4, 26, 0, 30, tzinfo=UTC),
            asset_universe=("BTC-USD",),
            regime_label="trend_up",
            event_features={"v": 0.1},
            evidence_tier="PRIMARY",  # type: ignore[arg-type]
            source_window=_good_window(),
            provenance="p",
            falsifier_status="OK",
        )


def test_supported_evidence_tiers_are_admissible() -> None:
    catalog = PopulationEventCatalog()
    for i, tier in enumerate(EvidenceTier):
        verdict = catalog.admit(_good_event(event_id=f"evt_{i:03d}", evidence_tier=tier))
        assert verdict.accepted is True
        assert verdict.evidence_tier is tier


# ---------------------------------------------------------------------------
# 8. cataloging does not imply prediction
# ---------------------------------------------------------------------------


def test_admission_witness_has_no_prediction_class_field() -> None:
    """The admission contract: a catalogue entry is evidence, not a
    prediction. The witness MUST NOT carry any field name that would let
    a downstream consumer mistake admission for a trading signal."""
    forbidden_field_names = {
        "prediction",
        "predicted",
        "signal",
        "forecast",
        "score",
        "direction",
        "recommendation",
        "side",
        "trade",
        "trade_signal",
        "buy",
        "sell",
        "alpha",
        "expected_return",
    }
    actual = {f.name for f in fields(AdmissionWitness)}
    overlap = actual & forbidden_field_names
    assert not overlap, f"AdmissionWitness leaks prediction-class fields: {overlap}"


def test_catalog_exposes_no_prediction_method() -> None:
    forbidden_method_names = {
        "predict",
        "forecast",
        "trade_signal",
        "score",
        "recommend",
        "advise",
        "expected_return",
    }
    catalog = PopulationEventCatalog()
    actual = {name for name in dir(catalog) if not name.startswith("_")}
    overlap = actual & forbidden_method_names
    assert not overlap, f"catalog leaks prediction-class methods: {overlap}"


# ---------------------------------------------------------------------------
# 9. deterministic ordering by (timestamp, event_id)
# ---------------------------------------------------------------------------


def test_events_returned_in_timestamp_then_id_order() -> None:
    catalog = PopulationEventCatalog()
    base = datetime(2026, 4, 26, 0, 30, tzinfo=UTC)
    # Admit in a non-sorted order; expect deterministic readback.
    catalog.admit(_good_event(event_id="evt_C", timestamp=base + timedelta(seconds=2)))
    catalog.admit(_good_event(event_id="evt_A", timestamp=base + timedelta(seconds=1)))
    catalog.admit(_good_event(event_id="evt_B", timestamp=base + timedelta(seconds=1)))

    ids_in_order = [e.event_id for e in catalog.events()]
    assert ids_in_order == ["evt_A", "evt_B", "evt_C"]


def test_catalog_iteration_is_deterministic_across_runs() -> None:
    """Two independent catalog instances built from the same input set
    yield byte-identical event sequences."""
    inputs = [
        _good_event(
            event_id=f"evt_{i:03d}",
            timestamp=datetime(2026, 4, 26, 0, 30, i, tzinfo=UTC),
        )
        for i in (5, 1, 7, 3)
    ]
    a = PopulationEventCatalog()
    b = PopulationEventCatalog()
    for ev in inputs:
        a.admit(ev)
    for ev in reversed(inputs):
        b.admit(ev)
    assert a.events() == b.events()


# ---------------------------------------------------------------------------
# 10. serialization round-trip preserves catalog content
# ---------------------------------------------------------------------------


def test_catalog_round_trips_via_dict() -> None:
    catalog = PopulationEventCatalog()
    base = datetime(2026, 4, 26, 0, 30, tzinfo=UTC)
    for i, tier in enumerate([EvidenceTier.PRIMARY, EvidenceTier.SECONDARY]):
        catalog.admit(
            _good_event(
                event_id=f"evt_{i:03d}",
                timestamp=base + timedelta(seconds=i),
                evidence_tier=tier,
            )
        )
    payload = catalog.to_dict()
    rebuilt = PopulationEventCatalog.from_dict(payload)
    assert rebuilt.to_dict() == payload
    assert rebuilt.events() == catalog.events()


def test_round_trip_rejects_unsupported_schema_version() -> None:
    with pytest.raises(ValueError, match="unsupported schema_version"):
        PopulationEventCatalog.from_dict({"schema_version": 99, "events": []})


def test_round_trip_replays_admission_rules() -> None:
    """If a payload contains a duplicate event_id, the round trip must
    raise — not silently accept the second copy."""
    base = datetime(2026, 4, 26, 0, 30, tzinfo=UTC)
    payload = {
        "schema_version": 1,
        "events": [
            _good_event(event_id="evt_dup", timestamp=base).to_dict(),
            _good_event(
                event_id="evt_dup",
                timestamp=base + timedelta(seconds=1),
            ).to_dict(),
        ],
    }
    with pytest.raises(ValueError, match="rejected admission"):
        PopulationEventCatalog.from_dict(payload)


# ---------------------------------------------------------------------------
# Auxiliary structural tests for the brief's other failure modes
# ---------------------------------------------------------------------------


def test_missing_event_id_rejected() -> None:
    with pytest.raises(ValueError, match="event_id must be a non-empty"):
        _good_event(event_id="")


def test_missing_provenance_rejected() -> None:
    with pytest.raises(ValueError, match="provenance must be a non-empty"):
        _good_event(provenance="")


def test_missing_falsifier_status_rejected() -> None:
    with pytest.raises(ValueError, match="falsifier_status must be a non-empty"):
        _good_event(falsifier_status="")


def test_event_input_features_are_immutable_after_construction() -> None:
    event = _good_event()
    with pytest.raises(TypeError):
        event.event_features["new_feature"] = 0.0  # type: ignore[index]


def test_event_input_is_frozen_dataclass() -> None:
    event = _good_event()
    with pytest.raises(Exception):
        event.event_id = "mutated"  # type: ignore[misc]


def test_admission_is_pure_under_rejection() -> None:
    """A rejected admission must not mutate the catalogue's state in
    any visible way."""
    catalog = PopulationEventCatalog()
    catalog.admit(_good_event(event_id="evt_a"))
    snapshot_events = catalog.events()
    snapshot_size = len(catalog)
    rejected = catalog.admit(_good_event(event_id="evt_a"))
    assert rejected.accepted is False
    assert catalog.events() == snapshot_events
    assert len(catalog) == snapshot_size


def test_event_input_to_dict_round_trip_individual() -> None:
    event = _good_event()
    rebuilt = EventInput.from_dict(event.to_dict())
    assert rebuilt.event_id == event.event_id
    assert rebuilt.timestamp == event.timestamp
    assert rebuilt.asset_universe == event.asset_universe
    assert dict(rebuilt.event_features) == dict(event.event_features)
    assert rebuilt.evidence_tier is event.evidence_tier


def test_catalog_does_not_mutate_input_event_features() -> None:
    """Defensive copy: feeding a mutable dict and mutating it later
    must not corrupt the cataloged record."""
    features = {"vol": 0.18}
    catalog = PopulationEventCatalog()
    catalog.admit(_good_event(event_features=features))
    features["vol"] = math.nan  # post-admit mutation
    stored = next(iter(catalog.events()))
    assert dict(stored.event_features) == {"vol": 0.18}


def test_catalog_size_after_reflects_state_after_admission() -> None:
    catalog = PopulationEventCatalog()
    v1 = catalog.admit(_good_event(event_id="evt_1"))
    v2 = catalog.admit(_good_event(event_id="evt_2"))
    v3 = catalog.admit(_good_event(event_id="evt_1"))  # duplicate
    assert v1.catalog_size_after == 1
    assert v2.catalog_size_after == 2
    assert v3.catalog_size_after == 2  # unchanged


def test_catalog_get_returns_admitted_event() -> None:
    catalog = PopulationEventCatalog()
    catalog.admit(_good_event(event_id="evt_g"))
    fetched = catalog.get("evt_g")
    assert fetched is not None
    assert fetched.event_id == "evt_g"
    assert catalog.get("does_not_exist") is None


def test_copying_catalog_preserves_events_under_independent_admission() -> None:
    """A shallow copy must NOT share state with the original; verifies
    admission to the copy does not leak back."""
    catalog = PopulationEventCatalog()
    catalog.admit(_good_event(event_id="evt_x"))
    other = copy(catalog)
    # Make `other` independently grow.
    other._events = dict(other._events)  # decouple internal map
    other.admit(_good_event(event_id="evt_y"))
    assert "evt_y" in other
    assert "evt_y" not in catalog
