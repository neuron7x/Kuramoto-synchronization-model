"""Substrate Revival Engine (Task 1).

Deterministic gatekeeper that classifies substrate capability and emits
ActionIntent with immutable audit hash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from core.io.parquet_compat import ParquetEngineUnavailable, read_parquet_compat


@dataclass(frozen=True)
class OracleDecision:
    substrate_type: str
    status: str
    reason_code: str
    reasons: list[str]
    stale_minutes: float | None
    schema_drift: bool
    nan_detected: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "substrate_type": self.substrate_type,
            "status": self.status,
            "reason_code": self.reason_code,
            "reasons": self.reasons,
            "stale_minutes": self.stale_minutes,
            "schema_drift": self.schema_drift,
            "nan_detected": self.nan_detected,
        }


def classify_columns(columns: list[str]) -> str:
    has_price = False
    has_bid = False
    has_ask = False
    has_depth = False
    has_ofi = False
    for raw in columns:
        c = raw.lower()
        if c in {"close", "open", "high", "low"}:
            has_price = True
        if "bid" in c:
            has_bid = True
        if "ask" in c:
            has_ask = True
        if "depth" in c or "level" in c or "book" in c:
            has_depth = True
        if "ofi" in c:
            has_ofi = True

    if has_ofi or has_depth:
        return "MICROSTRUCTURE"
    if has_bid and has_ask:
        return "BID_ASK"
    if has_price:
        return "OHLC_ONLY"
    return "UNKNOWN"


def _extract_timestamp_index(df: pd.DataFrame) -> pd.DatetimeIndex | None:
    if isinstance(df.index, pd.DatetimeIndex):
        return df.index
    for candidate in ("ts", "timestamp", "time", "datetime"):
        if candidate in df.columns:
            out = pd.to_datetime(df[candidate], utc=True, errors="coerce")
            if out.notna().any():
                return pd.DatetimeIndex(out.dropna())
    return None


def _staleness_minutes(df: pd.DataFrame, now_utc: datetime) -> float | None:
    idx = _extract_timestamp_index(df)
    if idx is None or len(idx) == 0:
        return None
    last_ts = idx.max()
    if last_ts.tzinfo is None:
        last_ts = last_ts.tz_localize(timezone.utc)
    stale = float((now_utc - last_ts.to_pydatetime()).total_seconds() / 60.0)
    # Guard against clock skew / future bars; treat as fresh instead of stale.
    return max(0.0, stale)


def evaluate_substrate(df: pd.DataFrame, now_utc: datetime | None = None) -> OracleDecision:
    now = now_utc or datetime.now(timezone.utc)

    if df.isna().any().any():
        return OracleDecision(
            substrate_type=classify_columns(list(df.columns)),
            status="ABORT",
            reason_code="NAN_ABORT",
            reasons=["NaN detected in payload"],
            stale_minutes=None,
            schema_drift=False,
            nan_detected=True,
        )

    substrate_type = classify_columns(list(df.columns))
    stale_m = _staleness_minutes(df, now)
    if stale_m is not None and stale_m > 30.0:
        return OracleDecision(
            substrate_type=substrate_type,
            status="BLOCK",
            reason_code="STALE_FEED",
            reasons=[f"Feed stale: {stale_m:.2f} minutes > 30"],
            stale_minutes=stale_m,
            schema_drift=False,
            nan_detected=False,
        )

    if substrate_type == "UNKNOWN":
        return OracleDecision(
            substrate_type=substrate_type,
            status="QUARANTINE",
            reason_code="SCHEMA_DRIFT",
            reasons=["Unknown header schema; quarantine required"],
            stale_minutes=stale_m,
            schema_drift=True,
            nan_detected=False,
        )

    if substrate_type == "OHLC_ONLY":
        return OracleDecision(
            substrate_type=substrate_type,
            status="DORMANT",
            reason_code="SUBSTRATE_DEAD_OHLC_ONLY",
            reasons=["OHLC-only substrate cannot support precursor claims"],
            stale_minutes=stale_m,
            schema_drift=False,
            nan_detected=False,
        )

    return OracleDecision(
        substrate_type=substrate_type,
        status="GO",
        reason_code="SUBSTRATE_LIVE",
        reasons=["Microstructure-capable substrate detected"],
        stale_minutes=stale_m,
        schema_drift=False,
        nan_detected=False,
    )


def _exit_code(decision: OracleDecision) -> int:
    if decision.reason_code == "NAN_ABORT":
        return 1
    if decision.reason_code in {"SUBSTRATE_DEAD_OHLC_ONLY", "SCHEMA_DRIFT"}:
        return 2
    return 0


def _make_action_intent(decision: OracleDecision) -> dict[str, Any]:
    action = "VALIDATE" if decision.status == "GO" else "DORMANT"
    return {
        "state": "REPORT",
        "substrate_status": "LIVE" if decision.status == "GO" else "DEAD",
        "action": action,
        "priority": "P0" if decision.status != "GO" else "P1",
        "target": "trading_desk",
        "why": decision.reasons,
        "blocking_conditions": [] if decision.status == "GO" else [decision.reason_code],
        "next_required_artifact": (
            "validation_verdict.json" if decision.status == "GO" else "abort_log.json"
        ),
        "admissible": True,
        "decision": decision.to_dict(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def run(input_path: Path, output_path: Path, now_utc: datetime | None = None) -> int:
    try:
        df = read_parquet_compat(input_path)
    except ParquetEngineUnavailable as exc:
        intent = {
            "state": "REPORT",
            "substrate_status": "DEAD",
            "action": "DORMANT",
            "priority": "P0",
            "target": "trading_desk",
            "why": [str(exc)],
            "blocking_conditions": ["PARQUET_ENGINE_MISSING"],
            "next_required_artifact": "abort_log.json",
            "admissible": True,
        }
        payload = json.dumps(intent, sort_keys=True)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        intent["hash"] = digest
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(intent, indent=2), encoding="utf-8")
        (output_path.parent / "action_intent.sha256").write_text(digest, encoding="utf-8")
        return 2
    decision = evaluate_substrate(df, now_utc=now_utc)
    intent = _make_action_intent(decision)
    payload = json.dumps(intent, sort_keys=True)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    intent["hash"] = digest

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(intent, indent=2), encoding="utf-8")
    (output_path.parent / "action_intent.sha256").write_text(digest, encoding="utf-8")
    return _exit_code(decision)


def main() -> int:
    parser = argparse.ArgumentParser(description="Substrate Revival Oracle")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return run(args.input, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
