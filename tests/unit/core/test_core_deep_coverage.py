# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.data.fingerprint and core.kuramoto.phase_transition."""

from __future__ import annotations

import json

import numpy as np
import pytest

# ═══════════════════════════════════════════════════════════════════
# core.data.fingerprint
# ═══════════════════════════════════════════════════════════════════
from core.data.fingerprint import (
    _normalise_text_lines,
    _sha256,
    compute_dataset_fingerprint,
    fingerprint_rows,
    hash_csv_content,
    hash_schema,
    record_run_fingerprint,
    record_transformation_trace,
    write_fingerprint_artifact,
)


class TestSha256:
    def test_deterministic(self):
        assert _sha256(b"hello") == _sha256(b"hello")

    def test_different_input(self):
        assert _sha256(b"a") != _sha256(b"b")


class TestNormaliseTextLines:
    def test_strips_trailing_spaces(self):
        text = "a  \nb  \n"
        result = _normalise_text_lines(text)
        assert result == b"a\nb\n"

    def test_adds_trailing_newline(self):
        result = _normalise_text_lines("no newline")
        assert result.endswith(b"\n")


class TestHashSchema:
    def test_deterministic(self):
        h1 = hash_schema(["a", "b"], ["int", "str"])
        h2 = hash_schema(["a", "b"], ["int", "str"])
        assert h1 == h2

    def test_different_order(self):
        h1 = hash_schema(["a", "b"], ["int", "str"])
        h2 = hash_schema(["b", "a"], ["str", "int"])
        assert h1 != h2

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="must align"):
            hash_schema(["a"], ["int", "str"])


class TestHashCsvContent:
    def test_reads_file(self, tmp_path):
        p = tmp_path / "data.csv"
        p.write_text("a,b\n1,2\n", encoding="utf-8")
        h = hash_csv_content(p)
        assert isinstance(h, str) and len(h) == 64


class TestFingerprintRows:
    def test_list_of_lists(self):
        rows = [[1, 2], [3, 4]]
        fp = fingerprint_rows(rows, columns=["x", "y"])
        assert fp["rows"] == 2
        assert "content_hash" in fp

    def test_list_of_dicts(self):
        rows = [{"x": 1, "y": 2}, {"x": 3, "y": 4}]
        fp = fingerprint_rows(rows)
        assert fp["rows"] == 2

    def test_list_of_dicts_explicit_columns(self):
        rows = [{"x": 1, "y": 2}]
        fp = fingerprint_rows(rows, columns=["x"])
        assert fp["rows"] == 1

    def test_empty_rows_no_columns(self):
        fp = fingerprint_rows([], columns=None)
        assert fp["rows"] == 0

    def test_dataset_id_and_schema_version(self):
        fp = fingerprint_rows([[1]], columns=["v"], dataset_id="ds1", schema_version="1.0")
        assert fp["dataset_id"] == "ds1"
        assert fp["schema_version"] == "1.0"


class TestComputeDatasetFingerprint:
    def test_file_not_found(self, tmp_path):
        from core.data.dataset_contracts import DatasetContract

        contract = DatasetContract(
            dataset_id="test",
            path=tmp_path / "nope.csv",
            schema_version="1.0",
            columns=["a"],
            dtypes=["int"],
            origin="test",
            description="test",
            creation_method="test",
            temporal_coverage="test",
            intended_use="test",
            forbidden_use="test",
        )
        with pytest.raises(FileNotFoundError):
            compute_dataset_fingerprint(contract)

    def test_valid_contract(self, tmp_path):
        from core.data.dataset_contracts import DatasetContract

        csv_path = tmp_path / "data.csv"
        csv_path.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
        contract = DatasetContract(
            dataset_id="test",
            path=csv_path,
            schema_version="1.0",
            columns=["a", "b"],
            dtypes=["int", "int"],
            origin="test",
            description="test",
            creation_method="test",
            temporal_coverage="test",
            intended_use="test",
            forbidden_use="test",
        )
        fp = compute_dataset_fingerprint(contract)
        assert fp["dataset_id"] == "test"
        assert fp["rows"] == 2
        assert "content_hash" in fp
        assert "schema_hash" in fp


class TestWriteFingerprintArtifact:
    def test_writes_json(self, tmp_path):
        fp = {"dataset_id": "test", "content_hash": "abc123"}
        result = write_fingerprint_artifact(fp, output_dir=tmp_path)
        assert result.exists()
        data = json.loads(result.read_text(encoding="utf-8"))
        assert data["dataset_id"] == "test"


class TestRecordRunFingerprint:
    def test_writes_with_run_type(self, tmp_path):
        from core.data.dataset_contracts import DatasetContract

        csv_path = tmp_path / "data.csv"
        csv_path.write_text("a\n1\n", encoding="utf-8")
        contract = DatasetContract(
            dataset_id="run_test",
            path=csv_path,
            schema_version="1.0",
            columns=["a"],
            dtypes=["str"],
            origin="test",
            description="test",
            creation_method="test",
            temporal_coverage="test",
            intended_use="test",
            forbidden_use="test",
        )
        out_dir = tmp_path / "fingerprints"
        result = record_run_fingerprint(contract, run_type="backtest", output_dir=out_dir)
        assert result.exists()
        data = json.loads(result.read_text(encoding="utf-8"))
        assert data["run_type"] == "backtest"


class TestRecordTransformationTrace:
    def test_writes_trace(self, tmp_path):
        inp = {"dataset_id": "in", "content_hash": "aaa"}
        out = {"dataset_id": "out", "content_hash": "bbb"}
        result = record_transformation_trace(
            transformation_id="transform1",
            parameters={"scale": 2.0},
            input_fingerprint=inp,
            output_fingerprint=out,
            output_dir=tmp_path,
        )
        assert result.exists()
        data = json.loads(result.read_text(encoding="utf-8"))
        assert data["transformation_id"] == "transform1"
        assert data["parameters"]["scale"] == 2.0


# ═══════════════════════════════════════════════════════════════════
# core.kuramoto.phase_transition
# ═══════════════════════════════════════════════════════════════════

from core.kuramoto.phase_transition import (
    PhaseTransitionAnalyzer,
    PhaseTransitionReport,
)


class TestPhaseTransitionAnalyzer:
    def test_construction(self):
        analyzer = PhaseTransitionAnalyzer(N=10, seed=0, steps_per_point=50, dt=0.05)
        assert analyzer._N == 10

    def test_sweep_small(self):
        """Run a minimal sweep and verify report structure."""
        analyzer = PhaseTransitionAnalyzer(
            N=10,
            seed=42,
            steps_per_point=100,
            dt=0.05,
            warmup_fraction=0.3,
        )
        report = analyzer.sweep(K_range=(0.0, 3.0), n_points=5)
        assert isinstance(report, PhaseTransitionReport)
        assert report.N == 10
        assert len(report.K_values) == 5
        assert len(report.R_forward) == 5
        assert len(report.R_backward) == 5
        assert report.K_c >= 0
        assert report.hysteresis_width >= 0
        assert report.K_c_theoretical > 0
        assert "steps_per_point" in report.metadata
        assert report.metadata["seed"] == 42

    def test_find_critical_K_interpolation(self):
        K_vals = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        R_vals = np.array([0.1, 0.2, 0.35, 0.6, 0.8])
        Kc = PhaseTransitionAnalyzer._find_critical_K(K_vals, R_vals, threshold=0.3)
        assert 1.0 < Kc < 3.0

    def test_find_critical_K_fallback(self):
        """When threshold is never crossed, fallback to max gradient."""
        K_vals = np.array([0.0, 1.0, 2.0, 3.0])
        R_vals = np.array([0.01, 0.02, 0.03, 0.04])
        Kc = PhaseTransitionAnalyzer._find_critical_K(K_vals, R_vals, threshold=0.5)
        assert isinstance(Kc, float)

    def test_report_fields(self):
        report = PhaseTransitionReport(
            K_values=np.array([0.0, 1.0]),
            R_forward=np.array([0.1, 0.5]),
            R_backward=np.array([0.1, 0.4]),
            K_c_forward=0.8,
            K_c_backward=0.7,
            K_c=0.75,
            hysteresis_width=0.1,
            N=10,
            omega_std=1.0,
            K_c_theoretical=1.6,
        )
        assert report.K_c == 0.75
        assert report.metadata == {}
