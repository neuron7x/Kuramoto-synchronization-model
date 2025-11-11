"""Memory persistence service layer.

This module provides business logic for exposure and regime persistence,
separated from the API layer for better testability and reusability.
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy.orm import Session

from ..errors import NotFoundError, RepositoryError
from ..memory.repository import MemoryRepository
from ..models import MarketRegime, PortfolioExposure
from ..modulation.regime import RegimeState


def store_portfolio_exposures(
    session: Session,
    exposures: Sequence[PortfolioExposure],
) -> None:
    """Store portfolio exposures to the database.
    
    Args:
        session: Database session
        exposures: List of portfolio exposures to store
        
    Raises:
        RepositoryError: If storage fails
    """
    if not exposures:
        return
    
    try:
        repository = MemoryRepository(session)
        repository.store_exposures(exposures)
    except Exception as exc:
        raise RepositoryError(
            f"Failed to store exposures: {exc}",
            code="ExposureStorageFailed",
        ) from exc


def fetch_portfolio_exposures(
    session: Session,
    portfolio_id: str,
    limit: int = 50,
) -> list[PortfolioExposure]:
    """Fetch portfolio exposures from the database.
    
    Args:
        session: Database session
        portfolio_id: Portfolio identifier
        limit: Maximum number of exposures to fetch
        
    Returns:
        List of portfolio exposures (most recent first)
        
    Raises:
        NotFoundError: If portfolio not found
        RepositoryError: If fetch fails
    """
    try:
        repository = MemoryRepository(session)
        exposures = repository.fetch_exposures(portfolio_id, limit=limit)
        
        if not exposures:
            raise NotFoundError(
                f"Portfolio not found: {portfolio_id}",
                code="PortfolioNotFound",
                details={"portfolio_id": portfolio_id},
            )
        
        return exposures
    except NotFoundError:
        raise
    except Exception as exc:
        raise RepositoryError(
            f"Failed to fetch exposures: {exc}",
            code="ExposureFetchFailed",
        ) from exc


def store_regime_state(
    session: Session,
    state: RegimeState,
) -> MarketRegime:
    """Store market regime state to the database.
    
    Args:
        session: Database session
        state: Regime state to store
        
    Returns:
        Persisted market regime record
        
    Raises:
        RepositoryError: If storage fails
    """
    try:
        repository = MemoryRepository(session)
        return repository.store_regime(
            label=state.label,
            valence=state.valence,
            confidence=state.confidence,
            as_of=state.as_of,
        )
    except Exception as exc:
        raise RepositoryError(
            f"Failed to store regime state: {exc}",
            code="RegimeStorageFailed",
        ) from exc


def fetch_latest_regime(
    session: Session,
) -> RegimeState | None:
    """Fetch the most recent market regime state.
    
    Args:
        session: Database session
        
    Returns:
        Latest regime state, or None if no state exists
        
    Raises:
        RepositoryError: If fetch fails
    """
    try:
        repository = MemoryRepository(session)
        regime = repository.latest_regime()
        
        if regime is None:
            return None
        
        return RegimeState(
            label=regime.label,
            valence=regime.valence,
            confidence=regime.confidence,
            as_of=regime.as_of,
        )
    except Exception as exc:
        raise RepositoryError(
            f"Failed to fetch latest regime: {exc}",
            code="RegimeFetchFailed",
        ) from exc


__all__ = [
    "store_portfolio_exposures",
    "fetch_portfolio_exposures",
    "store_regime_state",
    "fetch_latest_regime",
]
