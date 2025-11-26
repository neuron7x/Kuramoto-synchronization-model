from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from execution import (
    ComplianceMonitor,
    OrderRequest,
    RiskComplianceWorkflow,
    RiskLimits,
    RiskManager,
    SymbolNormalizer,
    SymbolSpecification,
)
from observability.release_gates import ReleaseGateEvaluator

DATASET = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "recordings"
    / "coinbase_btcusd.jsonl"
)


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def test_recorded_exchange_replay_validates_release_gates() -> None:
    raw_records = [
        json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines()
    ]
    latencies = [
        (_parse(record["ingest_ts"]) - _parse(record["exchange_ts"])).total_seconds()
        * 1000.0
        for record in raw_records
    ]

    spec = SymbolSpecification(
        symbol="BTC-USD",
        min_qty=0.0001,
        min_notional=10.0,
        step_size=0.0001,
        tick_size=0.01,
    )
    normalizer = SymbolNormalizer(specifications={spec.symbol: spec})
    compliance_monitor = ComplianceMonitor(normalizer, strict=True, auto_round=True)
    limits = RiskLimits(
        max_notional=1_000_000.0,
        max_position=5.0,
        max_orders_per_interval=100,
        interval_seconds=1.0,
    )
    workflow = RiskComplianceWorkflow(RiskManager(limits), compliance_monitor)

    orders = []
    for idx, record in enumerate(raw_records):
        side = "buy" if idx % 2 == 0 else "sell"
        quantity = round(float(record["volume"]), 4)
        orders.append(
            OrderRequest(
                symbol="BTC-USD",
                side=side,
                quantity=quantity,
                price=float(record["last"]),
            )
        )

    assessment = workflow.evaluate(orders)
    assert assessment.passed is True
    assert len(assessment.accepted) == len(orders)

    evaluator = ReleaseGateEvaluator(
        latency_median_target_ms=60.0,
        latency_p95_target_ms=90.0,
        latency_max_target_ms=120.0,
    )
    latency_result = evaluator.evaluate_latency(latencies)
    compliance_result = evaluator.evaluate_compliance(assessment.compliance_reports)
    checklist_result = evaluator.evaluate_checklist_from_path(
        Path("configs/production_readiness.json")
    )
    aggregate = evaluator.aggregate_results(
        [latency_result, compliance_result, checklist_result]
    )

    assert latency_result.passed is True
    assert compliance_result.passed is True
    assert checklist_result.passed is True
    assert aggregate.passed is True
    assert aggregate.metrics["latency_passed"] == 1.0
    assert aggregate.metrics["compliance_passed"] == 1.0
    assert aggregate.metrics["production_checklist_passed"] == 1.0
