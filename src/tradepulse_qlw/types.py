"""Type definitions for TradePulse-QLW."""

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class EngineResult:
    """Result from QLW engine computation."""

    psi: np.ndarray  # Wave field (nt, nx)
    resonance: np.ndarray  # Resonance alignment scores
    forbidden_mask: np.ndarray  # Hard forbidden zones
    soft_mask: np.ndarray  # Soft penalty mask
    meta: dict[str, Any]  # Metadata and diagnostics
