"""Persistence layer for cortex memory constructs."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..models import MarketRegime, PortfolioExposure


class MemoryRepository:
    """Handles persistence of exposures and regime state."""

    def __init__(self, session: Session):
        self._session = session

    def store_exposures(self, exposures: Iterable[PortfolioExposure]) -> None:
        payload = [
            {
                "portfolio_id": exposure.portfolio_id,
                "instrument": exposure.instrument,
                "exposure": exposure.exposure,
                "leverage": exposure.leverage,
                "as_of": exposure.as_of,
            }
            for exposure in exposures
        ]
        if not payload:
            return
        bind = self._session.bind
        if bind is None:
            raise RuntimeError("Session has no bound engine")
        dialect = bind.dialect.name
        if dialect == "postgresql":
            statement = insert(PortfolioExposure).values(payload)
            update_columns = {
                "exposure": statement.excluded.exposure,
                "leverage": statement.excluded.leverage,
                "as_of": statement.excluded.as_of,
            }
            self._session.execute(
                statement.on_conflict_do_update(
                    index_elements=[
                        PortfolioExposure.portfolio_id,
                        PortfolioExposure.instrument,
                        PortfolioExposure.as_of,
                    ],
                    set_=update_columns,
                )
            )
        else:
            for row in payload:
                existing = (
                    self._session.query(PortfolioExposure)
                    .filter_by(
                        portfolio_id=row["portfolio_id"],
                        instrument=row["instrument"],
                        as_of=row["as_of"],
                    )
                    .one_or_none()
                )
                if existing:
                    exposure_val: float = row["exposure"]  # type: ignore[assignment]
                    leverage_val: float = row["leverage"]  # type: ignore[assignment]
                    existing.exposure = exposure_val
                    existing.leverage = leverage_val
                else:
                    self._session.add(PortfolioExposure(**row))

    def fetch_exposures(
        self, portfolio_id: str, limit: int = 50
    ) -> list[PortfolioExposure]:
        statement = (
            select(PortfolioExposure)
            .where(PortfolioExposure.portfolio_id == portfolio_id)
            .order_by(PortfolioExposure.as_of.desc())
            .limit(limit)
        )
        return list(self._session.scalars(statement))

    def store_regime(
        self, label: str, valence: float, confidence: float, as_of: datetime
    ) -> MarketRegime:
        regime = MarketRegime(
            label=label, valence=valence, confidence=confidence, as_of=as_of
        )
        self._session.add(regime)
        return regime

    def latest_regime(self) -> MarketRegime | None:
        statement = select(MarketRegime).order_by(MarketRegime.as_of.desc()).limit(1)
        return self._session.scalars(statement).first()


__all__ = ["MemoryRepository"]
