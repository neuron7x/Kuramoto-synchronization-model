"""Safe persistence helpers for agent checkpoints.

These helpers avoid Python pickle deserialization by storing model state in a
NumPy ``.npz`` container.  Only tensor weights are persisted which keeps
Semgrep's ``pickles-in-pytorch`` rule satisfied while remaining compatible
with ``torch.nn.Module.load_state_dict``.
"""

from __future__ import annotations

import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import Mapping

import numpy as np
import torch


def _ensure_npz_suffix(path: Path) -> Path:
    if path.suffix != ".npz":
        raise ValueError(f"Checkpoint path must end with .npz, got {path}")
    return path


def save_state_dict_safely(state_dict: Mapping[str, torch.Tensor], path: Path) -> Path:
    """Persist ``state_dict`` to ``path`` without using pickle.

    Parameters
    ----------
    state_dict:
        Mapping of parameter names to tensors obtained from ``state_dict()``.
    path:
        Destination ``.npz`` path. The directory must exist.

    Returns
    -------
    Path
        The final path the checkpoint was stored at.
    """

    path = _ensure_npz_suffix(path)
    arrays = {name: tensor.detach().cpu().numpy() for name, tensor in state_dict.items()}
    with tempfile.NamedTemporaryFile(
        suffix=".npz", delete=False, dir=str(path.parent)
    ) as tmp_file:
        np.savez_compressed(tmp_file, **arrays)
        tmp_path = Path(tmp_file.name)
    tmp_path.replace(path)
    return path


def load_state_dict_safely(path: Path) -> "OrderedDict[str, torch.Tensor]":
    """Load a ``state_dict`` saved with :func:`save_state_dict_safely`.

    The function never enables pickle-based deserialization and therefore
    mitigates remote model execution attacks.
    """

    path = _ensure_npz_suffix(path)
    with np.load(path, allow_pickle=False) as npz:
        ordered_keys = list(npz.files)  # already yielded in the persistence order
        state = OrderedDict(
            (name, torch.from_numpy(np.array(npz[name]))) for name in ordered_keys
        )
    return state
