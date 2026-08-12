"""T3 · envelope-stress at seed=20260501 is deterministic and distinct
from the live shadow seed (20260422)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
SCRIPT = REPO / "scripts" / "analysis_cak_envelope_stress.py"
EVAL_SCRIPT = REPO / "scripts" / "evaluate_cross_asset_kuramoto_shadow.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None, "spec_from_file_location returned None"
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_seed_constant_is_distinct_from_shadow() -> None:
    offline = _load(SCRIPT, "offline_stress")
    shadow = _load(EVAL_SCRIPT, "shadow_eval")
    assert (
        offline.SEED != shadow.ENVELOPE_SEED
    ), f"offline seed {offline.SEED} must differ from shadow seed {shadow.ENVELOPE_SEED}"


def test_paths_reproducible_for_same_seed() -> None:
    offline = _load(SCRIPT, "offline_stress2")
    oos = offline._oos_log_returns()
    rng1 = np.random.default_rng(offline.SEED + 20)
    rng2 = np.random.default_rng(offline.SEED + 20)
    a = offline._paths(oos, 20, rng1)
    b = offline._paths(oos, 20, rng2)
    assert np.array_equal(a, b), "seeded block-bootstrap must be bit-reproducible"


def test_seeds_differ_yields_different_paths() -> None:
    offline = _load(SCRIPT, "offline_stress3")
    oos = offline._oos_log_returns()
    rng1 = np.random.default_rng(1)
    rng2 = np.random.default_rng(2)
    a = offline._paths(oos, 20, rng1)
    b = offline._paths(oos, 20, rng2)
    assert not np.array_equal(a, b), "seed change must yield different paths"
