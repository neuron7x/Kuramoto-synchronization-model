# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002J-P6 null-model hierarchy v1 package.

Ten null families, each a FALSIFIER targeting ONE named false
explanation. Importing from this package gives the null classes and the
shared :class:`NullInstance` data model.

This package builds the null-generator hierarchy contract; it does NOT
execute nulls against real substrate data at scale (P7/P8) and
authorises no canonical run.
"""

from __future__ import annotations

from research.systemic_risk.nulls.d002j.null_base import (
    SCHEMA_NULL_INSTANCE,
    NullInstance,
)
from research.systemic_risk.nulls.d002j.null_families import (
    ALL_NULLS,
    N1LabelPermutationNull,
    N2TimeWindowShiftPlaceboNull,
    N3TemporalBlockBootstrapNull,
    N4IAAFTSurrogateNull,
    N5DegreePreservingGraphNull,
    N6WeightPreservingShuffleNull,
    N7ConfigurationModelNull,
    N8SparseMaxEntReconstructionNull,
    N9ShockTimePlaceboNull,
    N10VintageLeakageTrapNull,
)

__all__ = [
    "ALL_NULLS",
    "SCHEMA_NULL_INSTANCE",
    "NullInstance",
    "N1LabelPermutationNull",
    "N2TimeWindowShiftPlaceboNull",
    "N3TemporalBlockBootstrapNull",
    "N4IAAFTSurrogateNull",
    "N5DegreePreservingGraphNull",
    "N6WeightPreservingShuffleNull",
    "N7ConfigurationModelNull",
    "N8SparseMaxEntReconstructionNull",
    "N9ShockTimePlaceboNull",
    "N10VintageLeakageTrapNull",
]
