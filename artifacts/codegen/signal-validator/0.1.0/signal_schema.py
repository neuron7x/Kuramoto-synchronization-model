"""Auto-generated Pandera schema."""

from __future__ import annotations

import pandera as pa


class SignalFrameSchema(pa.DataFrameModel):
    id: pa.String = pa.Field(
        nullable=False,
        checks=[],
        description="Signal identifier",
    )
    metadata: pa.Object = pa.Field(
        nullable=True,
        checks=[],
        description="Optional metadata",
    )
    score: pa.Float64 = pa.Field(
        nullable=False,
        checks=[pa.Check.ge(-1.0), pa.Check.le(1.0)],
        description="Scoring value",
    )
    symbol: pa.String = pa.Field(
        nullable=False,
        checks=[],
        description="Ticker symbol",
    )


__all__ = ["SignalFrameSchema"]
