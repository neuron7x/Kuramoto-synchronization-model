"""Auto-generated DTO models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SignalDto(BaseModel):
    id: str = Field(..., description="Signal identifier")
    metadata: dict[str, Any] | None = Field(default=None, description="Optional metadata")
    score: float = Field(..., description="Scoring value")
    symbol: str = Field(..., description="Ticker symbol")

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


__all__ = ["SignalDto"]
