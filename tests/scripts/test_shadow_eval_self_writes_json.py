# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""FIX-2 contract: shadow eval writes results/shadow_live.json on every run.

Falsification gate: mtime monotonic across consecutive evaluator invocations.
If two back-to-back runs leave shadow_live.json with identical mtime, the
self-update contract is broken.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SHADOW_LIVE_JSON = REPO / "results" / "shadow_live.json"
EVAL_SCRIPT = REPO / "scripts" / "evaluate_cross_asset_kuramoto_shadow.py"


def _run_evaluator() -> subprocess.CompletedProcess[str]:
    """Run `make eval-tick`, which captures evaluator stdout into the JSON.

    Note: the evaluator script itself is a frozen artefact (entry in
    SOURCE_HASHES.json); persistence to results/shadow_live.json is
    therefore done by the Makefile target, not by mutating the script.
    """
    return subprocess.run(
        ["make", "eval-tick"],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=180,
        check=False,
    )


@pytest.mark.skipif(
    not (
        Path.home() / "spikes" / "cross_asset_sync_regime" / "paper_state" / "equity.csv"
    ).is_file(),
    reason="Live spike paper-state not available in this environment.",
)
def test_eval_writes_shadow_live_json_with_monotonic_mtime() -> None:
    """Eval must (a) produce results/shadow_live.json, (b) bump mtime on rerun."""
    res1 = _run_evaluator()
    assert res1.returncode == 0, (
        f"FIX-2 VIOLATED: evaluator first run failed rc={res1.returncode}; "
        f"stderr={res1.stderr[:500]}"
    )
    assert SHADOW_LIVE_JSON.is_file(), (
        f"FIX-2 VIOLATED: results/shadow_live.json not produced by evaluator. "
        f"Expected path: {SHADOW_LIVE_JSON}."
    )
    mtime_1 = SHADOW_LIVE_JSON.stat().st_mtime

    payload = json.loads(SHADOW_LIVE_JSON.read_text(encoding="utf-8"))
    assert (
        "eval" in payload
    ), f"FIX-2 VIOLATED: payload schema missing 'eval' key. Got keys: {sorted(payload.keys())}."
    eval_block = payload["eval"]
    for required_key in (
        "eval_date",
        "live_bars_completed",
        "cumulative_net_return",
        "sharpe_live",
        "status_label",
        "gate_decision",
    ):
        assert required_key in eval_block, (
            f"FIX-2 VIOLATED: 'eval' missing key {required_key!r}. "
            f"Got: {sorted(eval_block.keys())}."
        )

    # mtime resolution can be coarse; sleep enough to step the timestamp
    # and force-touch in case the filesystem rounds to whole seconds.
    time.sleep(1.1)
    res2 = _run_evaluator()
    assert res2.returncode == 0, (
        f"FIX-2 VIOLATED: evaluator second run failed rc={res2.returncode}; "
        f"stderr={res2.stderr[:500]}"
    )
    mtime_2 = SHADOW_LIVE_JSON.stat().st_mtime
    assert mtime_2 > mtime_1, (
        f"FIX-2 VIOLATED: results/shadow_live.json mtime did not advance "
        f"across consecutive evaluator runs. "
        f"mtime_1={mtime_1}, mtime_2={mtime_2}. "
        f"Self-update contract broken: evaluator silently skipped the write."
    )
