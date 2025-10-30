# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable

from .graph import discover_fu


@dataclass
class RuleViolation:
    rule: str
    detail: str
    path: str


def check_invariants(root: Path, graph: Dict[str, list]) -> Iterable[RuleViolation]:
    required = {"src", "tests", "api", "docs", "config", "ci", "benchmarks"}
    for name, path in discover_fu(root):
        present = {p.name for p in path.iterdir() if p.is_dir()}
        missing = sorted(required - present)
        if missing:
            yield RuleViolation(
                "I1", f"Missing required dirs: {', '.join(missing)}", str(path)
            )

        for f in path.rglob("*.py"):
            txt = f.read_text(encoding="utf-8", errors="ignore")
            if "/adapters/" in str(f).replace("\\", "/"):
                if re.search(r"from\s+([a-zA-Z0-9_\.]+)\.src\.core", txt):
                    yield RuleViolation(
                        "I2", "adapter imports core of another FU", str(f)
                    )

        for f in path.rglob("*.js"):
            txt = f.read_text(encoding="utf-8", errors="ignore")
            if "/adapters/" in str(f).replace("\\", "/"):
                if re.search(r"from\s+[\'\"].+?/src/core", txt):
                    yield RuleViolation(
                        "I2", "adapter imports core of another FU", str(f)
                    )
