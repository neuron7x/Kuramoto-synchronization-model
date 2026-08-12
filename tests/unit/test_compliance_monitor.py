# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import pytest

from execution.compliance import ComplianceMonitor, ComplianceViolation
from execution.normalization import SymbolNormalizer, SymbolSpecification


@pytest.fixture
def normalizer():
    specs = {
        "BTCUSDT": SymbolSpecification(
            symbol="BTCUSDT",
            min_qty=0.001,
            min_notional=5.0,
            step_size=0.001,
            tick_size=0.1,
        )
    }
    return SymbolNormalizer(specifications=specs)


def test_compliance_monitor_blocks_invalid(normalizer):
    monitor = ComplianceMonitor(normalizer, strict=True, auto_round=False)
    with pytest.raises(ComplianceViolation):
        monitor.check("BTCUSDT", quantity=0.0005, price=10000.0)


def test_compliance_monitor_blocks_tick_misalignment(normalizer):
    monitor = ComplianceMonitor(normalizer, strict=True, auto_round=False)
    with pytest.raises(ComplianceViolation):
        monitor.check("BTCUSDT", quantity=0.001, price=10000.03)


def test_compliance_monitor_reports(normalizer):
    monitor = ComplianceMonitor(normalizer, strict=False, auto_round=True)
    report = monitor.check("BTCUSDT", quantity=0.0012, price=10000.0)
    assert report.normalized_quantity == pytest.approx(0.001)
    assert report.is_clean()


def test_compliance_monitor_flags_notional(normalizer):
    monitor = ComplianceMonitor(normalizer, strict=False, auto_round=False)
    report = monitor.check("BTCUSDT", quantity=0.001, price=1000.0)
    assert not report.is_clean()
    assert "Notional" in report.violations[0]
