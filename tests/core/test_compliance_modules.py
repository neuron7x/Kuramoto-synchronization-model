# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.compliance modules."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from core.compat import utc_now

try:
    from core.compliance.models import ComplianceIssue, ComplianceReport
except ImportError:
    pytest.skip("module dependencies not available", allow_module_level=True)

try:
    from core.compliance.regulatory import RegulatoryComplianceValidator
except ImportError:
    pytest.skip("module dependencies not available", allow_module_level=True)

try:
    from core.compliance.mifid2 import (
        ComplianceSnapshot,
        MiFID2Reporter,
        MiFID2RetentionPolicy,
        OrderAuditTrail,
        TransactionReport,
    )
except ImportError:
    pytest.skip("module dependencies not available", allow_module_level=True)

pytestmark = pytest.mark.skipif(
    ComplianceIssue is None and RegulatoryComplianceValidator is None and MiFID2Reporter is None,
    reason="compliance modules not importable",
)


class TestComplianceModels:
    pytestmark = pytest.mark.skipif(ComplianceIssue is None, reason="models not importable")

    def test_issue_creation(self):
        i = ComplianceIssue(severity="error", message="bad")
        assert i.severity == "error"

    def test_report_creation(self):
        r = ComplianceReport(
            compliant=True,
            issues=(),
            metadata={"k": "v"},
        )
        assert r.compliant is True

    def test_report_with_issues(self):
        r = ComplianceReport(
            compliant=False,
            issues=(ComplianceIssue("warning", "w1"),),
            metadata={},
        )
        assert len(r.issues) == 1

    def test_frozen(self):
        i = ComplianceIssue("error", "msg")
        with pytest.raises(AttributeError):
            i.severity = "warning"


class TestRegulatoryComplianceValidator:
    pytestmark = pytest.mark.skipif(
        RegulatoryComplianceValidator is None, reason="regulatory not importable"
    )

    def test_validate_type_error(self):
        v = RegulatoryComplianceValidator()
        with pytest.raises(TypeError):
            v.validate("not a dict")

    def test_validate_empty_metadata(self):
        v = RegulatoryComplianceValidator()
        report = v.validate({})
        assert isinstance(report, ComplianceReport)

    def test_validate_gdpr_non_compliant(self):
        v = RegulatoryComplianceValidator()
        report = v.validate({"gdpr_compliant": False})
        assert not report.compliant
        assert any("gdpr" in i.message.lower() for i in report.issues)

    def test_validate_ccpa_non_compliant(self):
        v = RegulatoryComplianceValidator()
        report = v.validate({"ccpa_compliant": False})
        assert any("ccpa" in i.message.lower() for i in report.issues)

    def test_validate_with_privacy_frameworks(self):
        v = RegulatoryComplianceValidator()
        report = v.validate(
            {
                "privacy": {"frameworks": {"gdpr": True, "ccpa": True}},
                "iso_compliance": {"iso27001": True, "iso27701": True},
                "nist_compliance": {"nist-csf": True, "nist-800-53": True},
            }
        )
        assert isinstance(report, ComplianceReport)

    def test_custom_regimes(self):
        v = RegulatoryComplianceValidator(required_privacy_regimes=["hipaa"])
        report = v.validate({})
        assert isinstance(report, ComplianceReport)

    @pytest.mark.parametrize("bool_str", ["true", "yes", "1", "enabled", "compliant"])
    def test_normalise_bool_truthy(self, bool_str):
        v = RegulatoryComplianceValidator()
        report = v.validate({"gdpr_compliant": bool_str})
        gdpr_errors = [
            i
            for i in report.issues
            if "gdpr" in i.message.lower() and "non-compliant" in i.message.lower()
        ]
        assert gdpr_errors == []


class TestMiFID2Reporter:
    pytestmark = pytest.mark.skipif(MiFID2Reporter is None, reason="mifid2 not importable")

    @pytest.fixture
    def reporter(self, tmp_path):
        return MiFID2Reporter(storage_path=tmp_path / "mifid2")

    def test_record_order(self, reporter):
        reporter.record_order(
            order_id="O1",
            payload={"action": "buy", "size": 100},
            venue="NYSE",
            actor="trader1",
        )
        assert len(reporter._audit_trail) == 1

    def test_record_execution(self, reporter):
        reporter.record_execution(
            order_id="O1",
            instrument="AAPL",
            quantity=100,
            price=150.0,
            side="buy",
            buyer="B",
            seller="S",
            venue="NYSE",
            benchmark_price=149.5,
            latency_ms=5.0,
        )
        assert len(reporter._reports) == 1
        assert len(reporter._execution_quality) == 1

    def test_best_execution_breaches(self, reporter):
        reporter.record_execution(
            order_id="O1",
            instrument="AAPL",
            quantity=100,
            price=200.0,
            side="buy",
            buyer="B",
            seller="S",
            venue="NYSE",
            benchmark_price=100.0,
            latency_ms=5.0,
        )
        breaches = reporter.best_execution_breaches(threshold_bps=5.0)
        assert len(breaches) >= 1

    def test_position_limit_breaches(self, reporter):
        breaches = reporter.position_limit_breaches(
            positions={"AAPL": 200.0},
            limits={"AAPL": 100.0},
        )
        assert "AAPL" in breaches

    def test_position_limit_no_breach(self, reporter):
        breaches = reporter.position_limit_breaches(
            positions={"AAPL": 50.0},
            limits={"AAPL": 100.0},
        )
        assert breaches == {}

    def test_market_abuse_large_cancel(self, reporter):
        reporter.record_order(
            order_id="O2",
            payload={"action": "cancel", "size": 2_000_000},
            venue="NYSE",
            actor="trader1",
        )
        signals = reporter.market_abuse_signals()
        assert len(signals) >= 1
        assert signals[0].reason == "suspicious large cancellation"

    def test_market_abuse_small_cancel_ok(self, reporter):
        reporter.record_order(
            order_id="O3",
            payload={"action": "cancel", "size": 100},
            venue="NYSE",
            actor="trader1",
        )
        assert reporter.market_abuse_signals() == []

    def test_health_summary(self, reporter):
        summary = reporter.health_summary()
        assert "reports" in summary
        assert "audit_trail" in summary

    def test_snapshot(self, reporter):
        snap = reporter.snapshot()
        assert isinstance(snap, ComplianceSnapshot)

    def test_export(self, reporter):
        reporter.record_order(order_id="O1", payload={"size": 10}, venue="V", actor="A")
        path = reporter.export()
        assert path.exists()
        data = json.loads(path.read_text())
        assert "audit_trail" in data

    def test_synchronise_clock(self, reporter):
        reporter.synchronise_clock(ntp_offset_ms=1.5)
        assert reporter._synchronised_at is not None

    def test_retention_policy(self):
        p = MiFID2RetentionPolicy(retention_years=5)
        assert p.retention_delta() == timedelta(days=365 * 5)

    def test_order_audit_trail_to_dict(self):
        t = OrderAuditTrail(
            order_id="O1",
            timestamp=utc_now(),
            payload={"k": "v"},
            venue="V",
            actor="A",
        )
        d = t.to_dict()
        assert d["order_id"] == "O1"

    def test_transaction_report_to_dict(self):
        r = TransactionReport(
            order_id="O1",
            instrument="AAPL",
            quantity=100.0,
            price=150.0,
            side="buy",
            execution_time=utc_now(),
            buyer="B",
            seller="S",
        )
        d = r.to_dict()
        assert d["instrument"] == "AAPL"

    def test_generate_regulatory_report(self, reporter):
        report = reporter.generate_regulatory_report()
        assert "health" in report
        assert "best_execution_breaches" in report
