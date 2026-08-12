# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Convergence-boundary teeth for the Kuramoto early-stopping engine.

The engine's whole value is stopping *exactly* when R(t) has been steady for
``patience`` consecutive steps and not one step sooner. Three decision guards
carry that contract; each test below pins one so that a mutated comparison
flips an observable field of the result summary:

- ``:112  if delta < epsilon``      -- only a genuinely-steady EMA counts as stable.
- ``:114  if stable_count >= patience`` -- convergence needs the FULL patience window.
- ``:148  converged_step < max_steps``  -- compute-saved is reported only on a real early stop.

Natural frequencies are pinned to zero so the ensemble locks to R==1.0 well
before ``min_steps``; the convergence geometry is then deterministic and the
assertions are exact, not statistical.
"""

from __future__ import annotations

import numpy as np

from core.kuramoto.config import KuramotoConfig
from core.kuramoto.early_stopping import EarlyStoppingEngine


def _locked_config(steps: int) -> KuramotoConfig:
    # omega == 0 => the phases synchronise to R==1.0 within a few dozen steps,
    # so for every k >= min_steps the EMA change is < any sane epsilon.
    return KuramotoConfig(N=20, K=5.0, dt=0.01, steps=steps, seed=7, omega=np.zeros(20))


def test_steady_ema_converges_after_full_patience_and_reports_savings() -> None:
    """A locked ensemble stops at exactly min_steps + patience, saving compute.

    Kills :112 (``delta < epsilon``): under ``Lt->GtE`` a vanishing EMA change no
    longer counts as stable, so ``stable_count`` never accumulates and the run
    never early-stops -- ``early_stopped`` would be False.
    Kills :148 (``converged_step < max_steps``): under ``Lt->GtE`` the ternary
    collapses ``compute_saved_pct`` to 0.0 on a run that genuinely stopped early.
    """
    engine = EarlyStoppingEngine(
        _locked_config(steps=1000),
        epsilon=1e-4,
        patience=50,
        ema_alpha=0.05,
        min_steps=300,
    )
    summary = engine.run().summary

    assert summary["early_stopped"] is True, (
        "a fully-locked ensemble (R==1.0, ΔEMA≈0 < ε) must trigger early stopping; "
        "if delta<ε is inverted the stable counter never advances"
    )
    # min_steps warmup gate opens at k==300; the first eligible step increments
    # stable_count to 1, so patience==50 is met at k+1 == 300 + 50.
    assert summary["converged_at_step"] == 350, (
        f"expected stop at min_steps(300)+patience(50)=350, got "
        f"{summary['converged_at_step']}"
    )
    assert summary["compute_saved_pct"] > 0.0, (
        "a genuine early stop (converged_step < max_steps) must report positive "
        "compute savings; the < max_steps guard governs that ternary"
    )


def test_patience_exceeding_available_window_never_converges() -> None:
    """When patience outlasts the whole run, no early stop may fire.

    Kills :114 (``stable_count >= patience``): under ``GtE->Lt`` the break fires as
    soon as ``stable_count`` is merely *below* patience -- i.e. on the very first
    stable step -- so the engine would wrongly early-stop. With patience(5000) >
    available stable steps(<=100) the correct behaviour is to run to completion.
    """
    engine = EarlyStoppingEngine(
        _locked_config(steps=400),
        epsilon=1e-4,
        patience=5000,
        ema_alpha=0.05,
        min_steps=300,
    )
    summary = engine.run().summary

    assert summary["early_stopped"] is False, (
        "patience(5000) exceeds the at-most-100 stable steps available, so the "
        "full-window criterion can never be met -- the run must complete"
    )
    assert summary["converged_at_step"] == summary["max_steps"] == 400
    assert summary["compute_saved_pct"] == 0.0
