# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Iterable, List, Tuple, Union


@dataclass(frozen=True)
class StrategySignature:
    R: float
    delta_H: float
    kappa_mean: float
    entropy: float
    instability: float

    def key(self, precision: int = 4) -> Tuple[float, float, float, float, float]:
        rounded = tuple(
            round(value, precision)
            for value in (
                self.R,
                self.delta_H,
                self.kappa_mean,
                self.entropy,
                self.instability,
            )
        )
        return (rounded[0], rounded[1], rounded[2], rounded[3], rounded[4])


@dataclass
class StrategyRecord:
    name: str
    signature: Union[StrategySignature, Tuple[float, float, float, float, float]]
    score: float
    ts: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not isinstance(self.signature, StrategySignature):
            object.__setattr__(self, "signature", StrategySignature(*self.signature))


class StrategyMemory:
    def __init__(self, decay_lambda: float = 1e-6, max_records: int = 256):
        self._records: List[StrategyRecord] = []
        self.lmb = decay_lambda
        self.max_records = max_records

    def _decayed_score(self, record: StrategyRecord) -> float:
        age = time.time() - record.ts
        return math.exp(-self.lmb * age) * record.score

    def add(
        self,
        name: str,
        signature: Union[StrategySignature, Tuple[float, float, float, float, float]],
        score: float,
    ) -> None:
        sig = (
            signature
            if isinstance(signature, StrategySignature)
            else StrategySignature(*signature)
        )
        key = sig.key()
        existing_index = next(
            (i for i, rec in enumerate(self._records) if rec.signature.key() == key),
            None,
        )
        record = StrategyRecord(name=name, signature=sig, score=score)
        if existing_index is None:
            self._records.append(record)
        elif score > self._records[existing_index].score:
            self._records[existing_index] = record
        if len(self._records) > self.max_records:
            self._evict()

    def topk(self, k: int = 5) -> List[StrategyRecord]:
        records = sorted(self._records, key=self._decayed_score, reverse=True)
        return records[:k]

    def cleanup(self, min_score: float = 0.0) -> None:
        self._records = [
            record
            for record in self._records
            if self._decayed_score(record) > min_score
        ]

    def _evict(self) -> None:
        if not self._records:
            return
        worst_index = min(
            range(len(self._records)),
            key=lambda i: self._decayed_score(self._records[i]),
        )
        self._records.pop(worst_index)

    @property
    def records(self) -> List[StrategyRecord]:
        return list(self._records)

    @records.setter
    def records(self, values: Iterable[StrategyRecord]) -> None:
        converted: List[StrategyRecord] = []
        for record in values:
            if not isinstance(record, StrategyRecord):
                raise TypeError("records setter expects StrategyRecord instances")
            converted.append(record)
        self._records = converted
