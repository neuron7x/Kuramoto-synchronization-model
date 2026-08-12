from __future__ import annotations

from typing import Any


def test_evaluation_rows_vary() -> None:
    module: Any = __import__(
        "scripts." + "evaluate_dopamine_rpe_extension",
        fromlist=["build_rows"],
    )
    rows = module.build_rows(5, 20260629)
    values = [row["signed_score"] for row in rows]
    assert module.validate_rows(rows, 5) == []
    assert min(values) < 0.0
    assert max(values) > 0.0
