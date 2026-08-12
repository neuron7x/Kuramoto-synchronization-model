"""Zero-trust integration harness for substrate and OFI kernels."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from agent.substrate_oracle import evaluate_substrate
from core.io.parquet_compat import read_parquet_compat
from research.kernels.ofi_unity_live import ofi_unity_kernel


@dataclass
class AuditLog:
    entries: list[dict[str, Any]] = field(default_factory=list)

    def append(self, entry: dict[str, Any]) -> None:
        self.entries.append(entry)


class ZeroTrustOracle:
    def __init__(self) -> None:
        self.audit_log = AuditLog()

    def substrate_oracle(self, path: Path) -> dict[str, Any]:
        assert path.exists(), "INV-FILE-001 violated"
        frame = read_parquet_compat(path)
        decision = evaluate_substrate(frame)
        payload = decision.to_dict()
        self.audit_log.append(
            {
                "call": "substrate_oracle",
                "input_hash": hashlib.sha256(path.read_bytes()).hexdigest(),
                "output": payload,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
        return payload

    def ofi_unity(self, df: pd.DataFrame) -> pd.Series:
        cols = [c.lower() for c in df.columns]
        assert any("bid" in c for c in cols) and any(
            "ask" in c for c in cols
        ), "INV-OFI-001 violated"
        assert not df.isna().any().any(), "INV-NAN-001 violated"
        unity = ofi_unity_kernel(df)
        assert unity.index.is_monotonic_increasing, "Index contract failed"
        assert unity.notna().all(), "NaN contract failed"
        assert ((unity >= 0) & (unity <= 1)).all(), "Range contract failed"
        self.audit_log.append(
            {
                "call": "ofi_unity",
                "input_rows": int(len(df)),
                "output_rows": int(len(unity)),
                "output_hash": hashlib.sha256(unity.to_json().encode()).hexdigest(),
            }
        )
        return unity

    def export_audit(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.audit_log.entries, indent=2, sort_keys=True), encoding="utf-8"
        )
