from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

log = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    t: float
    kv: Dict[str, Any]


@dataclass
class MetricsEmitter:
    buffer: List[MetricPoint] = field(default_factory=list)

    def emit(self, **kv: Any) -> None:
        self.buffer.append(MetricPoint(time.time(), kv))
        log.info("METRIC: %s", json.dumps(kv, ensure_ascii=False))

    def drain(self) -> List[MetricPoint]:
        out, self.buffer = self.buffer, []
        return out
