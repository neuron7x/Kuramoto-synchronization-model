"""Generate validation metrics for CNSStabilizer v2.1."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from runtime.cns_stabilizer import CNSStabilizer  # noqa: E402

np.random.seed(42)


@dataclass(slots=True)
class EpisodeResult:
    name: str
    suppression_accuracy: float
    false_deny_rate: float
    mse: float
    latency_ms: float
    monotonic_rate: float
    integrity_ratio: float
    phase_accuracy: float
    ga_gain: float
    micro_recovery_count: int
    veto_rate: float


def _phase_ground_truth(prices: np.ndarray) -> List[str]:
    gradients = np.gradient(prices)
    phases: List[str] = []
    for idx, price in enumerate(prices):
        grad = gradients[idx]
        if grad > 0 and idx > 0 and prices[idx] > prices[idx - 1] * 1.002:
            phases.append("pre-spike")
        elif grad < 0:
            phases.append("post-spike")
        elif idx > 0 and abs(prices[idx] - prices[idx - 1]) < 1e-3:
            phases.append("stable")
        else:
            phases.append("recover")
    return phases


def _evaluate_episode(name: str, prices: np.ndarray) -> EpisodeResult:
    stabilizer = CNSStabilizer(normalize="logret", hybrid_mode=True)
    chunk_size = 256
    filtered_segments: List[float] = []
    for start in range(0, len(prices), chunk_size):
        chunk = prices[start : start + chunk_size]
        if len(chunk) < 4:
            break
        filtered_chunk = stabilizer.process_signals_sync(
            chunk.tolist(),
            ga_phase=f"{name}_chunk_{start // chunk_size}",
        )
        filtered_segments.extend(filtered_chunk[: len(chunk)])

    events = stabilizer.get_eventlog()
    audit_log = stabilizer.get_audit_log()

    hazard_events = []
    for evt in events:
        data = evt["data"]
        if data.get("action") == "veto":
            hazard_events.append(evt)
            continue
        delta_f_val = float(data.get("delta_f", 0.0))
        threshold_after = float(data.get("threshold_after_pid", stabilizer.threshold))
        if delta_f_val >= 0.9 * threshold_after:
            hazard_events.append(evt)

    hazard_count = len(hazard_events)
    veto_count = sum(1 for evt in events if evt["data"].get("action") == "veto")
    suppression_accuracy = (
        1.0 if hazard_count == 0 else min(1.0, veto_count / hazard_count)
    )

    false_deny_rate = 0.0
    if hazard_count == 0 and len(events) > 0:
        false_deny_rate = veto_count / len(events)

    filtered_arr = np.asarray(filtered_segments, dtype=float)
    target_arr = prices[: len(filtered_arr)]
    mse = float(np.mean((filtered_arr - target_arr) ** 2)) if len(filtered_arr) else 0.0

    latencies = [
        evt["data"].get("latency", 0.0) for evt in events if "latency" in evt["data"]
    ]
    latency_ms = float(np.mean(latencies) * 1000) if latencies else 0.0

    confirmed = sum(1 for entry in audit_log if "confirmed" in entry)
    monotonic_rate = confirmed / max(len(audit_log), 1)

    integrity_values = [
        evt["data"].get("integrity", stabilizer.get_integrity_ratio()) for evt in events
    ]
    if integrity_values:
        integrity_ratio = float(np.mean([float(val) for val in integrity_values]))
    else:
        integrity_ratio = float(stabilizer.get_integrity_ratio())

    gt_phases = _phase_ground_truth(prices)
    observed_phases = [evt["data"].get("phase", "stable") for evt in events]
    phase_matches = 0
    for obs in observed_phases:
        if obs in gt_phases:
            phase_matches += 1
    phase_accuracy = phase_matches / max(len(observed_phases), 1)

    ga_gain = stabilizer.get_ga_fitness_feedback()
    micro_recovery_count = stabilizer.micro_recovery_count
    veto_rate = veto_count / max(len(events), 1)

    return EpisodeResult(
        name=name,
        suppression_accuracy=float(suppression_accuracy),
        false_deny_rate=float(false_deny_rate),
        mse=float(mse),
        latency_ms=float(latency_ms),
        monotonic_rate=float(monotonic_rate),
        integrity_ratio=float(integrity_ratio),
        phase_accuracy=float(phase_accuracy),
        ga_gain=float(ga_gain),
        micro_recovery_count=int(micro_recovery_count),
        veto_rate=float(veto_rate),
    )


def _generate_prices(kind: str, length: int) -> np.ndarray:
    base_price = 100.0
    if kind == "normal":
        increments = np.random.normal(0.0, 0.001, length)
        return base_price * np.exp(np.cumsum(increments))
    if kind == "spike":
        increments = np.random.normal(0.0, 0.001, length)
        spikes = np.zeros(length)
        spike_indices = np.random.choice(length, size=5, replace=False)
        spikes[spike_indices] = np.random.choice([0.05, -0.05], size=5)
        return base_price * np.exp(np.cumsum(increments + spikes))
    if kind == "flash_crash":
        crash = np.linspace(base_price * 1.2, base_price * 0.45, length)
        noise = np.random.normal(0.0, 0.01, length)
        return np.clip(crash * (1 + noise), a_min=base_price * 0.2, a_max=None)
    raise ValueError(f"Unknown scenario {kind}")


def run_validation(output_dir: Path) -> pd.DataFrame:
    scenarios = [
        ("normal", "normal"),
        ("normal_2", "normal"),
        ("spike", "spike"),
        ("spike_2", "spike"),
        ("flash_crash", "flash_crash"),
    ]
    results: List[EpisodeResult] = []
    for name, kind in scenarios:
        prices = _generate_prices(kind, 2048)
        result = _evaluate_episode(name, prices)
        results.append(result)

    df = pd.DataFrame([asdict(result) for result in results])
    df.loc["mean"] = df.mean(numeric_only=True)

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "cns_stabilizer_metrics.csv"
    df.to_csv(csv_path, index=True)

    json_path = output_dir / "cns_stabilizer_metrics.json"
    json_path.write_text(json.dumps(df.to_dict(orient="index"), indent=2))

    return df


if __name__ == "__main__":
    run_validation(Path("reports"))
