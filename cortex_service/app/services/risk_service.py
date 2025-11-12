"""Service for risk assessment business logic."""

from __future__ import annotations

from typing import Iterable

from ..config import RiskSettings
from ..errors import ValidationError
from ..ethics.risk import Exposure, RiskAssessment, compute_risk
from ..logger import get_logger
from ..metrics import RISK_SCORE

logger = get_logger(__name__)


class RiskService:
    """Service layer for risk assessment operations."""

    def __init__(self, settings: RiskSettings) -> None:
        """Initialize the risk service.

        Args:
            settings: Risk computation settings
        """
        self._settings = settings

    def assess_risk(self, exposures: Iterable[Exposure]) -> RiskAssessment:
        """Assess portfolio risk from exposures.

        Args:
            exposures: Iterator of portfolio exposures

        Returns:
            Risk assessment with score and metrics

        Raises:
            ValidationError: If exposures are invalid
        """
        exposure_list = list(exposures)

        try:
            assessment = compute_risk(exposure_list, self._settings)

            # Record metrics
            RISK_SCORE.observe(assessment.score)

            logger.debug(
                "Assessed risk",
                extra={
                    "exposure_count": len(exposure_list),
                    "risk_score": assessment.score,
                    "value_at_risk": assessment.value_at_risk,
                    "breaches": len(assessment.breached),
                },
            )

            return assessment
        except ValueError as exc:
            raise ValidationError(
                f"Invalid exposures for risk computation: {exc}"
            ) from exc


__all__ = ["RiskService"]
