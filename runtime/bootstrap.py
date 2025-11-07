"""Runtime bootstrap utilities for deterministic agent execution."""

from __future__ import annotations

import os
import random
from typing import Optional

import numpy as np
import torch


def set_determinism(seed: int = 42, *, omp_threads: Optional[int] = 1, mkl_threads: Optional[int] = 1) -> None:
    """Configure process-wide determinism settings.

    The configuration follows the governance specification for V2.1. All random number
    generators are seeded and the torch backend is forced into deterministic execution
    mode where supported.
    """

    os.environ["PYTHONHASHSEED"] = str(seed)
    if omp_threads is not None:
        os.environ["OMP_NUM_THREADS"] = str(omp_threads)
    if mkl_threads is not None:
        os.environ["MKL_NUM_THREADS"] = str(mkl_threads)

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True


__all__ = ["set_determinism"]
