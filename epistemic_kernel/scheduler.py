"""Falsifier-first experiment ranking."""
from __future__ import annotations
from typing import Iterable, Tuple
from .models import ExperimentCandidate

def epistemic_score(e: ExperimentCandidate, *, falsification_weight: float=1.0,
                    independence_weight: float=1.0) -> float:
    if e.cost <= 0: raise ValueError("experiment cost must be > 0")
    vals=(e.expected_information_gain,e.falsification_probability,e.independence_gain)
    if any(v < 0 for v in vals): raise ValueError("epistemic terms must be non-negative")
    return (e.expected_information_gain + falsification_weight*e.falsification_probability +
            independence_weight*e.independence_gain)/e.cost

def rank_experiments(candidates: Iterable[ExperimentCandidate], **kwargs: float) -> Tuple[ExperimentCandidate, ...]:
    rows=tuple(candidates)
    return tuple(sorted(rows,key=lambda e:(-epistemic_score(e,**kwargs),e.experiment_id)))
