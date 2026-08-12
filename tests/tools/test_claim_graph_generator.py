from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.generate_claim_graph import main


def test_generate_claim_graph_has_nodes() -> None:
    assert main() == 0
    graph: dict[str, Any] = json.loads(
        Path("docs/architecture/claim_graph.json").read_text(encoding="utf-8")
    )
    assert graph["nodes"]
    assert graph["constraints"]["dangling_nodes"] == 0
