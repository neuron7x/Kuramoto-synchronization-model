# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Data-reality firewall — eight-gate ingress contract tests."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import numpy as np

from research.systemic_risk.data_firewall import (
    FIREWALL_GATES,
    PROVENANCE_SCHEMA_VERSION,
    DataFirewallReport,
    Provenance,
    gate_diagonal,
    gate_finite,
    gate_monotonic_time,
    gate_provenance,
    gate_schema_type,
    gate_shape,
    gate_sign,
    gate_sparsity,
    run_data_firewall,
)


def _good_matrix(n: int = 3) -> np.ndarray:
    """A 3-node bilateral exposure matrix with zero diagonal and a finite,
    non-negative off-diagonal value pattern. Round-trip safe through every
    gate when paired with a complete provenance record."""
    m = np.array(
        [
            [0.0, 1.0, 2.0],
            [3.0, 0.0, 4.0],
            [5.0, 6.0, 0.0],
        ],
        dtype=np.float64,
    )
    assert m.shape == (n, n)
    return m


def _good_provenance(d: date) -> Provenance:
    return Provenance(
        source_id="e-MID-daily-snapshot",
        schema_version=PROVENANCE_SCHEMA_VERSION,
        capture_timestamp_utc=(
            datetime(d.year, d.month, d.day, 12, 0, tzinfo=timezone.utc).isoformat()
        ),
        payload_sha256="0" * 64,
    )


def _good_panel() -> tuple[dict[date, np.ndarray], dict[date, Provenance]]:
    base = date(2026, 5, 1)
    panel: dict[date, np.ndarray] = {}
    provs: dict[date, Provenance] = {}
    for offset in range(3):
        d = base + timedelta(days=offset)
        panel[d] = _good_matrix()
        provs[d] = _good_provenance(d)
    return panel, provs


_NODE_LABELS = ("BANK_A", "BANK_B", "BANK_C")


class TestFirewallGatesRoster:
    def test_gate_count(self) -> None:
        assert len(FIREWALL_GATES) == 8

    def test_gate_names_unique(self) -> None:
        assert len(set(FIREWALL_GATES)) == 8


class TestGateSchemaType:
    def test_clean_panel_passes(self) -> None:
        panel, _ = _good_panel()
        out = gate_schema_type(panel)
        assert out.passed
        assert out.name == "G1_schema_type"

    def test_empty_panel_fails(self) -> None:
        out = gate_schema_type({})
        assert not out.passed
        assert "empty" in out.reason

    def test_non_date_key_fails(self) -> None:
        panel: dict[object, np.ndarray] = {"2026-05-01": _good_matrix()}
        out = gate_schema_type(panel)  # type: ignore[arg-type]
        assert not out.passed

    def test_datetime_key_fails(self) -> None:
        # datetime is a subclass of date but the firewall demands date-only.
        panel: dict[date, np.ndarray] = {datetime(2026, 5, 1, 12, 0): _good_matrix()}
        out = gate_schema_type(panel)
        assert not out.passed

    def test_wrong_dtype_fails(self) -> None:
        panel = {date(2026, 5, 1): np.zeros((3, 3), dtype=np.int64)}
        out = gate_schema_type(panel)  # type: ignore[arg-type]
        assert not out.passed
        assert "dtype" in out.reason


class TestGateShape:
    def test_clean_passes(self) -> None:
        panel, _ = _good_panel()
        out = gate_shape(panel, n_nodes=3)
        assert out.passed

    def test_n_nodes_zero_fails(self) -> None:
        out = gate_shape({}, n_nodes=0)
        assert not out.passed

    def test_wrong_shape_fails(self) -> None:
        panel = {date(2026, 5, 1): np.zeros((3, 4), dtype=np.float64)}
        out = gate_shape(panel, n_nodes=3)
        assert not out.passed

    def test_wrong_n_fails(self) -> None:
        panel, _ = _good_panel()
        out = gate_shape(panel, n_nodes=5)
        assert not out.passed


class TestGateFinite:
    def test_clean_passes(self) -> None:
        panel, _ = _good_panel()
        out = gate_finite(panel)
        assert out.passed

    def test_nan_caught(self) -> None:
        m = _good_matrix()
        m[0, 1] = np.nan
        panel = {date(2026, 5, 1): m}
        out = gate_finite(panel)
        assert not out.passed
        assert "nan" in out.reason.lower()

    def test_inf_caught(self) -> None:
        m = _good_matrix()
        m[1, 0] = np.inf
        panel = {date(2026, 5, 1): m}
        out = gate_finite(panel)
        assert not out.passed


class TestGateSign:
    def test_clean_passes(self) -> None:
        panel, _ = _good_panel()
        out = gate_sign(panel)
        assert out.passed

    def test_negative_caught(self) -> None:
        m = _good_matrix()
        m[0, 1] = -1.0
        panel = {date(2026, 5, 1): m}
        out = gate_sign(panel)
        assert not out.passed
        assert "negative" in out.reason


class TestGateDiagonal:
    def test_clean_passes(self) -> None:
        panel, _ = _good_panel()
        out = gate_diagonal(panel)
        assert out.passed

    def test_self_loop_caught(self) -> None:
        m = _good_matrix()
        m[0, 0] = 0.5
        panel = {date(2026, 5, 1): m}
        out = gate_diagonal(panel)
        assert not out.passed
        assert "self-loops" in out.reason


class TestGateSparsity:
    def test_clean_passes(self) -> None:
        panel, _ = _good_panel()
        out = gate_sparsity(panel)
        assert out.passed

    def test_all_zero_matrix_caught(self) -> None:
        panel = {date(2026, 5, 1): np.zeros((3, 3), dtype=np.float64)}
        out = gate_sparsity(panel)
        assert not out.passed
        assert "all-zero" in out.reason


class TestGateMonotonicTime:
    def test_strictly_increasing_passes(self) -> None:
        panel, _ = _good_panel()
        out = gate_monotonic_time(panel)
        assert out.passed

    def test_single_snapshot_passes(self) -> None:
        panel = {date(2026, 5, 1): _good_matrix()}
        out = gate_monotonic_time(panel)
        assert out.passed

    def test_duplicate_date_via_unsorted_iteration_caught(self) -> None:
        # Reverse-order insertion gives non-monotonic iteration order.
        panel: dict[date, np.ndarray] = {}
        panel[date(2026, 5, 3)] = _good_matrix()
        panel[date(2026, 5, 1)] = _good_matrix()
        out = gate_monotonic_time(panel)
        assert not out.passed
        assert "strictly increasing" in out.reason


class TestGateProvenance:
    def test_clean_passes(self) -> None:
        panel, provs = _good_panel()
        out = gate_provenance(provs, panel_keys=tuple(panel.keys()))
        assert out.passed

    def test_missing_provenance_caught(self) -> None:
        panel, provs = _good_panel()
        d = next(iter(panel))
        del provs[d]
        out = gate_provenance(provs, panel_keys=tuple(panel.keys()))
        assert not out.passed
        assert "missing provenance" in out.reason

    def test_empty_source_id_caught(self) -> None:
        panel, provs = _good_panel()
        d = next(iter(panel))
        provs[d] = Provenance(
            source_id="   ",
            schema_version=PROVENANCE_SCHEMA_VERSION,
            capture_timestamp_utc=provs[d].capture_timestamp_utc,
            payload_sha256=provs[d].payload_sha256,
        )
        out = gate_provenance(provs, panel_keys=tuple(panel.keys()))
        assert not out.passed
        assert "source_id" in out.reason

    def test_wrong_schema_version_caught(self) -> None:
        panel, provs = _good_panel()
        d = next(iter(panel))
        provs[d] = Provenance(
            source_id=provs[d].source_id,
            schema_version="bogus.v0",
            capture_timestamp_utc=provs[d].capture_timestamp_utc,
            payload_sha256=provs[d].payload_sha256,
        )
        out = gate_provenance(provs, panel_keys=tuple(panel.keys()))
        assert not out.passed
        assert "schema_version" in out.reason

    def test_naive_timestamp_caught(self) -> None:
        panel, provs = _good_panel()
        d = next(iter(panel))
        provs[d] = Provenance(
            source_id=provs[d].source_id,
            schema_version=provs[d].schema_version,
            capture_timestamp_utc="2026-05-01T12:00:00",  # no offset
            payload_sha256=provs[d].payload_sha256,
        )
        out = gate_provenance(provs, panel_keys=tuple(panel.keys()))
        assert not out.passed
        assert "tz offset" in out.reason

    def test_unparseable_timestamp_caught(self) -> None:
        panel, provs = _good_panel()
        d = next(iter(panel))
        provs[d] = Provenance(
            source_id=provs[d].source_id,
            schema_version=provs[d].schema_version,
            capture_timestamp_utc="garbage",
            payload_sha256=provs[d].payload_sha256,
        )
        out = gate_provenance(provs, panel_keys=tuple(panel.keys()))
        assert not out.passed
        assert "unparseable" in out.reason

    def test_short_sha_caught(self) -> None:
        panel, provs = _good_panel()
        d = next(iter(panel))
        provs[d] = Provenance(
            source_id=provs[d].source_id,
            schema_version=provs[d].schema_version,
            capture_timestamp_utc=provs[d].capture_timestamp_utc,
            payload_sha256="abc",
        )
        out = gate_provenance(provs, panel_keys=tuple(panel.keys()))
        assert not out.passed
        assert "64-hex" in out.reason

    def test_uppercase_sha_caught(self) -> None:
        panel, provs = _good_panel()
        d = next(iter(panel))
        provs[d] = Provenance(
            source_id=provs[d].source_id,
            schema_version=provs[d].schema_version,
            capture_timestamp_utc=provs[d].capture_timestamp_utc,
            payload_sha256="A" * 64,
        )
        out = gate_provenance(provs, panel_keys=tuple(panel.keys()))
        assert not out.passed


class TestRunDataFirewall:
    def test_clean_panel_passes_all(self) -> None:
        panel, provs = _good_panel()
        report = run_data_firewall(panel, node_labels=_NODE_LABELS, provenances=provs)
        assert isinstance(report, DataFirewallReport)
        assert report.passed_all
        assert len(report.gate_outcomes) == 8
        assert all(o.passed for o in report.gate_outcomes)
        # Gate names are reported in canonical order.
        assert tuple(o.name for o in report.gate_outcomes) == FIREWALL_GATES

    def test_one_failure_propagates(self) -> None:
        panel, provs = _good_panel()
        # Inject a non-finite value: G3 fails, others still pass.
        d = next(iter(panel))
        bad = panel[d].copy()
        bad[0, 1] = np.nan
        panel[d] = bad
        report = run_data_firewall(panel, node_labels=_NODE_LABELS, provenances=provs)
        assert not report.passed_all
        failed = [o for o in report.gate_outcomes if not o.passed]
        assert len(failed) == 1
        assert failed[0].name == "G3_finite"

    def test_protocol_compatibility_with_death_conditions(self) -> None:
        """The report's ``passed_all`` field is the contract surface
        consumed by ``death_conditions.trigger_data_proxy_invalid``."""
        panel, provs = _good_panel()
        report = run_data_firewall(panel, node_labels=_NODE_LABELS, provenances=provs)
        # Mirrors DataFirewallResultLike protocol.
        assert hasattr(report, "passed_all")
        assert isinstance(report.passed_all, bool)
