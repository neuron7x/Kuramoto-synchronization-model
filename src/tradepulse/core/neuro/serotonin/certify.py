from __future__ import annotations

import json
import os
import math
import threading
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np

from tradepulse.core.neuro.numeric_config import STABILITY_EPSILON
from tradepulse.core.neuro.serotonin.serotonin_controller import SerotoninController
from tradepulse.policy.basal_ganglia import BasalGangliaDecisionStack

_EPS = STABILITY_EPSILON


@dataclass
class RegimeMetrics:
    name: str
    max_flips: int
    max_flips_window: int
    time_in_hold_ratio: float
    min_level: float
    max_level: float
    violations: list[str]


def _build_observations(prices: Sequence[float]) -> list[dict[str, float]]:
    arr = np.asarray(prices, dtype=float)
    if arr.ndim != 1 or len(arr) < 2:
        raise ValueError("prices must be 1-D with at least 2 points")
    returns = np.diff(arr) / np.where(arr[:-1] == 0.0, _EPS, arr[:-1])
    rolling_max = np.maximum.accumulate(arr[:-1])
    drawdowns = (arr[1:] - rolling_max) / rolling_max
    obs = []
    prev_r = 0.0
    for ret, dd in zip(returns, drawdowns):
        stress = float(abs(ret) * 8.0 + max(0.0, -dd * 4.0))
        novelty = float(abs(ret - prev_r) * 5.0)
        obs.append(
            {
                "stress": max(0.0, stress),
                "drawdown": float(dd),
                "novelty": max(0.0, novelty),
                "market_vol": max(0.0, abs(ret)),
                "free_energy": max(0.0, novelty * 0.5),
                "cum_losses": max(0.0, -dd),
                "rho_loss": 0.0,
            }
        )
        prev_r = ret
    return obs


def _count_flips(flags: Sequence[bool]) -> int:
    return sum(1 for i in range(1, len(flags)) if flags[i] != flags[i - 1])


def _hysteresis_violation(level: float, cfg: Mapping[str, float], hold_state: bool) -> bool:
    margin = cfg.get("hysteresis_margin", 0.05)
    threshold = cfg["cooldown_threshold"] * (1.0 - margin)
    return (not hold_state) and level > threshold + STABILITY_EPSILON


def _check_persistence(ctrl: SerotoninController) -> list[str]:
    violations: list[str] = []
    fd, path_str = tempfile.mkstemp(prefix="serotonin_state_", suffix=".json")
    os.close(fd)
    path = Path(path_str)
    before = ctrl.get_state()
    ctrl.save_state(str(path))

    # Second writer should block via lock but not corrupt
    t = threading.Thread(target=ctrl.save_state, args=(str(path),), daemon=True)
    t.start()
    t.join(timeout=2)
    if t.is_alive():
        violations.append("concurrent_save_timeout")

    new_ctrl = SerotoninController(ctrl.config_path)
    new_ctrl.load_state(str(path))
    after = new_ctrl.get_state()

    for key, val in before.items():
        if isinstance(val, bool):
            if bool(after[key]) != bool(val):
                violations.append(f"state_mismatch:{key}")
        else:
            if (
                not math.isfinite(float(after[key]))
                or abs(float(after[key]) - float(val)) > STABILITY_EPSILON
            ):
                violations.append(f"state_mismatch:{key}")

    if path.with_suffix(path.suffix + ".tmp").exists():
        violations.append("atomic_write_failed")

    if path.exists():
        path.unlink()
    return violations


def run_regime(
    name: str,
    prices: Sequence[float],
    controller: SerotoninController,
    *,
    flip_window: int = 20,
    flip_limit: int = 8,
) -> RegimeMetrics:
    controller.reset()
    observations = _build_observations(prices)
    holds: list[bool] = []
    vetoes: list[bool] = []
    cooldowns: list[float] = []
    levels: list[float] = []
    violations: list[str] = []
    last_cooldown = 0.0

    for obs in observations:
        res = controller.step(
            stress=obs["stress"],
            drawdown=obs["drawdown"],
            novelty=obs["novelty"],
            market_vol=obs["market_vol"],
            free_energy=obs["free_energy"],
            cum_losses=obs["cum_losses"],
            rho_loss=obs["rho_loss"],
            dt=1.0,
        )

        if not (0.0 <= res.level <= 1.0):
            violations.append("level_out_of_bounds")
        if not math.isfinite(res.cooldown):
            violations.append("cooldown_nonfinite")
        if res.cooldown < -STABILITY_EPSILON:
            violations.append("cooldown_negative")
        if res.hold and res.cooldown + _EPS < last_cooldown:
            violations.append("cooldown_nonmonotonic")
        if _hysteresis_violation(res.level, controller.config, res.hold):
            violations.append("hysteresis_violation")

        last_cooldown = res.cooldown if res.hold else 0.0
        holds.append(bool(res.hold))
        vetoes.append(bool(res.veto))
        cooldowns.append(float(res.cooldown))
        levels.append(float(res.level))

    if holds and name == "whipsaw":
        for idx in range(len(holds)):
            window = holds[max(0, idx - flip_window + 1) : idx + 1]
            if _count_flips(window) > flip_limit:
                violations.append("excessive_hold_flips")
                break

    violations.extend(_check_persistence(controller))

    time_in_hold = sum(1 for h in holds if h) / max(1, len(holds))
    return RegimeMetrics(
        name=name,
        max_flips=max((_count_flips(holds), _count_flips(vetoes))),
        max_flips_window=flip_window,
        time_in_hold_ratio=time_in_hold,
        min_level=min(levels) if levels else 0.0,
        max_level=max(levels) if levels else 0.0,
        violations=sorted(set(violations)),
    )


def run_basal_ganglia_integration(seed: int = 123) -> list[str]:
    rng = np.random.default_rng(int(seed))
    q_values = {"A": 0.4, "B": 0.8}
    constraints = {
        "stress": 2.0,
        "drawdown": -0.3,
        "novelty": 0.5,
        "dt": 1.0,
        "value": 0.1,
        "next_value": 0.2,
        "reward": -0.05,
        "volatility": 0.6,
    }
    # Add small randomness to avoid degenerate ties while remaining deterministic
    jitter = float(rng.normal(0.0, 0.01))
    constraints["reward"] += jitter

    stack = BasalGangliaDecisionStack()
    result = stack.select_action(q_values, constraints)
    serotonin_state = result.extras["serotonin"]
    violations: list[str] = []
    if bool(serotonin_state["hold"] >= 0.5) and result.decision == "GO":
        violations.append("integration_hold_ignored")
    temperature = float(result.extras.get("temperature", 1.0))
    floor = float(serotonin_state["temperature_floor"])
    if temperature < floor - STABILITY_EPSILON:
        violations.append("temperature_floor_violated")
    return violations


def serialize_metrics(metrics: Iterable[RegimeMetrics]) -> list[dict[str, object]]:
    payload = []
    for m in metrics:
        payload.append(
            {
                "name": m.name,
                "max_flips": m.max_flips,
                "max_flips_window": m.max_flips_window,
                "time_in_hold_ratio": m.time_in_hold_ratio,
                "min_level": m.min_level,
                "max_level": m.max_level,
                "violations": m.violations,
            }
        )
    return payload


def write_certificate(
    *,
    out_dir: Path,
    seed: int,
    dataset: str,
    regime_results: list[RegimeMetrics],
    integration_violations: list[str],
    commit: str | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "seed": seed,
        "dataset": dataset,
        "commit": commit,
        "regimes": serialize_metrics(regime_results),
        "integration_violations": integration_violations,
    }
    (out_dir / "certificate.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )

    lines = [
        "# Serotonin Robustness Certificate",
        "",
        f"- Seed: {seed}",
        f"- Dataset: {dataset}",
        f"- Commit: {commit or 'unknown'}",
        "",
        "## Regime Metrics",
        "",
        "| Regime | Min Level | Max Level | Hold Ratio | Max Flips | Violations |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for m in regime_results:
        vtext = ", ".join(m.violations) if m.violations else "—"
        lines.append(
            f"| {m.name} | {m.min_level:.4f} | {m.max_level:.4f} | "
            f"{m.time_in_hold_ratio:.3f} | {m.max_flips} / {m.max_flips_window} | {vtext} |"
        )
    lines.append("")
    if integration_violations:
        lines.append("## Integration Violations")
        for v in integration_violations:
            lines.append(f"- {v}")
    else:
        lines.append("## Integration Check")
        lines.append("- Basal ganglia respects serotonin hold/veto ✓")
    (out_dir / "certificate.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
