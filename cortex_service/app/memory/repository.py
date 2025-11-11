"""Persistence layer for cortex memory constructs.

This module provides the repository pattern for database operations,
isolating persistence logic from business logic.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..models import MarketRegime, PortfolioExposure


class MemoryRepository:
    """Handles persistence of exposures and regime state.
    
    This repository provides methods for storing and retrieving
    portfolio exposures and market regime states.
    
    Attributes:
        _session: SQLAlchemy database session
    """

    def __init__(self, session: Session):
        """Initialize the repository with a database session.
        
        Args:
            session: SQLAlchemy session for database operations
        """
        self._session = session

    def store_exposures(self, exposures: Iterable[PortfolioExposure]) -> None:
        """Store or update portfolio exposures.
        
        Uses upsert logic for PostgreSQL and fallback logic for other databases.
        
        Args:
            exposures: Iterable of portfolio exposures to store
        """
        payload: list[dict[str, Any]] = [
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
        
        # Get dialect name safely for mypy
        bind = self._session.bind
        if bind is None:
            raise RuntimeError("Session has no bind")
        dialect = bind.dialect.name
        if dialect == "postgresql":
            statement = insert(PortfolioExposure).values(payload)
            update_columns = {
                "exposure": statement.excluded.exposure,
                "leverage": statement.excluded.leverage,
                "as_of": statement.excluded.as_of,
            }
            self._session.execute(statement.on_conflict_do_update(index_elements=[
                PortfolioExposure.portfolio_id,
                PortfolioExposure.instrument,
                PortfolioExposure.as_of,
            ], set_=update_columns))
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
                    # Cast to float for mypy
                    existing.exposure = float(row["exposure"])
                    existing.leverage = float(row["leverage"])
                else:
                    self._session.add(PortfolioExposure(**row))

    def fetch_exposures(self, portfolio_id: str, limit: int = 50) -> list[PortfolioExposure]:
        """Fetch exposures for a portfolio.
        
        Args:
            portfolio_id: Portfolio identifier
            limit: Maximum number of exposures to return
            
        Returns:
            List of portfolio exposures (most recent first)
        """
        statement = (
            select(PortfolioExposure)
            .where(PortfolioExposure.portfolio_id == portfolio_id)
            .order_by(PortfolioExposure.as_of.desc())
            .limit(limit)
        )
        return list(self._session.scalars(statement))

    def store_regime(self, label: str, valence: float, confidence: float, as_of: datetime) -> MarketRegime:
        """Store a market regime state.
        
        Args:
            label: Regime classification label
            valence: Regime valence value
            confidence: Confidence level
            as_of: Timestamp for the regime state
            
        Returns:
            Persisted market regime record
        """
        regime = MarketRegime(label=label, valence=valence, confidence=confidence, as_of=as_of)
        self._session.add(regime)
        return regime

    def latest_regime(self) -> MarketRegime | None:
        """Fetch the most recent market regime state.
        
        Returns:
            Latest market regime record, or None if no states exist
        """
        statement = select(MarketRegime).order_by(MarketRegime.as_of.desc()).limit(1)
        return self._session.scalars(statement).first()


__all__ = ["MemoryRepository"]
