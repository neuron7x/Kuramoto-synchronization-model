"""Neuro-inspired CNS stabiliser for the TACL control loop."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.linalg import inv
from scipy.signal import convolve
from scipy.stats import entropy

from runtime.kill_switch import is_kill_switch_active


@dataclass(slots=True)
class StabilizerEvent:
    """Structured representation of CNS telemetry."""

    epoch: int
    ga_phase: str
    data: Dict[str, object]
    timestamp: float
    action_class: str
    mode: str
    allowed: bool


class CNSStabilizer:
    """CNS stabiliser implementing the v2.1 tri-layer inhibition stack.

    The implementation follows the neurocybernetic specification described in the
    project brief.  It exposes an asyncio-aware API while also providing a
    synchronous convenience wrapper for callers that operate from blocking
    control loops.
    """

    def __init__(
        self,
        max_signals: int = 1000,
        epsilon: float = 0.01,
        *,
        kT: float = 1.0,
        alpha: float = 0.5,
        normalize: str = "none",
        td_threshold: float = -0.3,
        hpa_threshold: float = 0.5,
        hybrid_mode: bool = False,
    ) -> None:
        self.buffer: Deque[float] = deque(maxlen=max_signals)
        self.kalman_P = np.array([[0.1]])
        self.pid_kp, self.pid_ki, self.pid_integral = 0.3, 0.1, 0.0
        self.threshold = 0.5
        self.lambda_ttl = 0.9
        self.epsilon = epsilon
        self.kT, self.alpha = kT, alpha
        self.normalize = normalize
        self.td_threshold = td_threshold
        self.hpa_threshold = hpa_threshold
        self.hybrid_mode = hybrid_mode
        self.diverge_count = 0
        self.reset_task: Optional[asyncio.Task[None]] = None
        self._circadian_loop: Optional[asyncio.AbstractEventLoop] = None
        self._circadian_thread: Optional[threading.Thread] = None

        self.delta_f_history: Deque[float] = deque(maxlen=10)
        self.delta_f_variance: Deque[float] = deque(maxlen=10)
        self.q_table: Dict[int, Dict[int, float]] = {
            0: {0: 0.1, 1: -0.05},
            1: {0: -0.05, 1: 0.2},
        }
        self.audit_log: List[str] = []
        self.eventlog: List[StabilizerEvent] = []

        self.safety_margin = 0.0
        self.epoch = 0
        self.heatmap_data: List[Dict[str, float | str]] = []
        self.micro_recovery_count = 0
        self._last_audit_status = "confirmed"
        self.system_mode = "PoR"

    async def process_signals(
        self, raw_signals: List[float], *, ga_phase: str = "pre_evolve"
    ) -> List[float]:
        """Process a batch of raw signals asynchronously.

        Parameters
        ----------
        raw_signals:
            Coherency or risk-normalised signals produced by the VLPO filter.
        ga_phase:
            Identifier for the GA integration stage, used in telemetry.
        """

        start_time = time.time()
        self.epoch += 1

        kill_switch_active = is_kill_switch_active()
        if kill_switch_active:
            integrity_ratio = self.get_integrity_ratio()
            self._log_event(
                ga_phase,
                {
                    "phase": "halt",
                    "action": "veto",
                    "type": "kill_switch",
                    "reason": "kill_switch_active",
                    "integrity": integrity_ratio,
                    "monotonic": self._last_audit_status,
                },
                action_class="OBSERVE",
                allowed=False,
                kill_switch_active=True,
            )
            return []

        raw_length = int(len(raw_signals))
        signals_norm = self._normalize(np.asarray(raw_signals, dtype=float))
        chunk_length = int(len(signals_norm))

        hpa_tone = 0.0
        if len(self.delta_f_history) > 2:
            df_array = np.array(list(self.delta_f_history))
            if len(df_array) >= 3:
                hpa_tone = np.gradient(np.diff(df_array))[-1]
                if hpa_tone > self.hpa_threshold:
                    phase = self._annotate_phase(hpa_tone)
                    self._log_gate("hpa_veto", hpa_tone)
                    self._log_event(
                        ga_phase,
                        {
                            "hpa": float(hpa_tone),
                            "phase": phase,
                            "action": "veto",
                            "type": "hpa",
                            "integrity": self.get_integrity_ratio(),
                            "monotonic": self._last_audit_status,
                        },
                        action_class="SELF_REGULATE",
                        allowed=False,
                    )
                    return []

        td_error = self.get_td_error_proxy(signals_norm)
        veto_flags = {
            "hpa": hpa_tone > 0.3,
            "td": td_error < self.td_threshold,
        }

        throttle_factor = 1.0
        if self.hybrid_mode and veto_flags["hpa"] and veto_flags["td"]:
            throttle_factor = 0.5
            signals_norm = signals_norm[::2]
            chunk_length = int(len(signals_norm))
            self._log_gate("hybrid_throttle", throttle_factor)
            self._log_event(
                ga_phase,
                {
                    "hybrid": float(throttle_factor),
                    "flags": {
                        "hpa": bool(veto_flags["hpa"]),
                        "td": bool(veto_flags["td"]),
                    },
                    "action": "throttle",
                    "type": "hybrid",
                    "integrity": self.get_integrity_ratio(),
                    "monotonic": self._last_audit_status,
                },
                action_class="SELF_REGULATE",
                allowed=True,
            )
        elif td_error < self.td_threshold:
            phase = self._annotate_phase(td_error)
            self._log_gate("td_veto", td_error)
            self._log_event(
                ga_phase,
                {
                    "td": float(td_error),
                    "phase": phase,
                    "action": "veto",
                    "type": "td",
                    "integrity": self.get_integrity_ratio(),
                    "monotonic": self._last_audit_status,
                },
                action_class="SELF_REGULATE",
                allowed=False,
            )
            return []

        delta_f_proxy = self.compute_delta_f(signals_norm) if chunk_length > 0 else 0.0
        self.lambda_ttl = max(0.5, 0.9 - 0.2 * delta_f_proxy)

        for sig in signals_norm:
            decayed = float(sig) * np.exp(-len(self.buffer) * (1 - self.lambda_ttl))
            self.buffer.append(decayed)

        if len(self.buffer) > 800:
            await self.rest_phase()

        states = np.array(list(self.buffer), dtype=float)

        try:
            filtered_states = self.kalman_update(states)
            self.diverge_count = 0
        except ValueError:
            self.diverge_count += 1
            filtered_states = convolve(states, np.ones(3) / 3, mode="valid")

        real_delta_f = self.compute_delta_f(filtered_states)
        self.delta_f_history.append(real_delta_f)
        self.delta_f_variance.append(real_delta_f)

        phase = self._annotate_phase(real_delta_f)

        error = real_delta_f - self.epsilon
        self.pid_integral += error

        threshold_before_pid = self.threshold
        self.pid_adjust(error, self.pid_integral)

        new_delta_f_proxy = self.compute_delta_f(filtered_states)
        tolerance = 1e-6
        audit_status = (
            "confirmed" if new_delta_f_proxy <= real_delta_f + tolerance else "violated"
        )
        self._last_audit_status = audit_status
        self.audit_log.append(
            (
                "Epoch %d: Monotonic descent %s (ΔF'=%.4f %s ΔF=%.4f)"
                % (
                    self.epoch,
                    audit_status,
                    new_delta_f_proxy,
                    "<" if audit_status == "confirmed" else ">=",
                    real_delta_f,
                )
            )
        )

        if audit_status == "violated":
            self._micro_recovery(ga_phase)

        if len(self.delta_f_variance) > 1:
            var = float(np.var(list(self.delta_f_variance)))
            self.safety_margin = 1.96 * np.sqrt(var)
            self.threshold = float(
                np.clip(self.threshold + self.safety_margin * 0.1, 0.1, 2.0)
            )

        integrity_ratio = self.get_integrity_ratio()
        mode = self._determine_mode(
            phase=phase,
            integrity=integrity_ratio,
            kill_switch_active=False,
            monotonic_status=audit_status,
        )

        self.heatmap_data.append(
            {
                "epoch": self.epoch,
                "delta_f": real_delta_f,
                "phase": phase,
                "margin": self.safety_margin,
            }
        )

        if audit_status == "violated" and integrity_ratio < 0.8:
            self._log_gate("monotonic_veto", new_delta_f_proxy)
            self._log_event(
                ga_phase,
                {
                    "delta_f": real_delta_f,
                    "phase": phase,
                    "action": "veto",
                    "type": "monotonic",
                    "integrity": integrity_ratio,
                    "monotonic": audit_status,
                    "threshold_before_pid": threshold_before_pid,
                    "threshold_after_pid": self.threshold,
                    "recovery_path": False,
                },
                action_class="SELF_REGULATE",
                allowed=False,
                mode=mode,
            )
            return []

        if real_delta_f > self.threshold:
            self._log_gate("delta_f_denied", real_delta_f)
            self._log_event(
                ga_phase,
                {
                    "delta_f": real_delta_f,
                    "phase": phase,
                    "action": "veto",
                    "type": "delta_f",
                    "integrity": integrity_ratio,
                    "threshold_before_pid": threshold_before_pid,
                    "threshold_after_pid": self.threshold,
                    "monotonic": audit_status,
                },
                action_class="SELF_REGULATE",
                allowed=False,
                mode=mode,
            )
            return []

        target_length = chunk_length if chunk_length > 0 else raw_length
        chunk_filtered = self._extract_chunk(filtered_states, target_length)
        aligned_chunk = self._align_to_raw_length(chunk_filtered, raw_length)
        latency = time.time() - start_time

        self._log_gate("passed", real_delta_f)
        self._log_event(
            ga_phase,
            {
                "delta_f": real_delta_f,
                "phase": phase,
                "action": "pass",
                "integrity": integrity_ratio,
                "margin": self.safety_margin,
                "threshold_after_pid": self.threshold,
                "chunk_size": len(aligned_chunk),
                "processed_samples": chunk_length,
                "latency": latency,
                "monotonic": audit_status,
            },
            action_class="INFLUENCE_INTERNAL",
            allowed=True,
            mode=mode,
        )

        return aligned_chunk

    def process_signals_sync(
        self, raw_signals: List[float], *, ga_phase: str = "pre_evolve"
    ) -> List[float]:
        """Synchronous helper for environments without an event loop."""

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.process_signals(raw_signals, ga_phase=ga_phase))
        else:  # pragma: no cover - synchronous controller does not enter here
            if loop.is_running():
                raise RuntimeError(
                    "process_signals_sync cannot run inside an active event loop"
                )
            return loop.run_until_complete(
                self.process_signals(raw_signals, ga_phase=ga_phase)
            )

    def _annotate_phase(
        self, delta_f_now: float, gradient_source: Optional[float] = None
    ) -> str:
        if gradient_source is None:
            if len(self.delta_f_history) > 0:
                grad_arr = np.array(list(self.delta_f_history) + [delta_f_now])
                gradient = float(np.gradient(grad_arr)[-1])
            else:
                gradient = 0.0
        else:
            gradient = float(gradient_source)

        if delta_f_now > self.threshold * 0.8 and gradient > 0:
            return "pre-spike"
        if gradient < 0:
            return "post-spike"
        if self.safety_margin > 0.1:
            return "recover"
        return "stable"

    def _micro_recovery(self, ga_phase: str) -> None:
        self.micro_recovery_count += 1
        self.pid_kp *= 0.9
        self.pid_ki *= 0.95
        self.pid_kp = float(np.clip(self.pid_kp, 0.1, 0.5))
        self.pid_ki = float(np.clip(self.pid_ki, 0.05, 0.2))

        self._log_event(
            ga_phase,
            {
                "action": "micro_recovery",
                "kp": self.pid_kp,
                "ki": self.pid_ki,
                "count": self.micro_recovery_count,
                "monotonic": self._last_audit_status,
            },
            action_class="SELF_REGULATE",
            allowed=True,
        )

    def export_heatmap(self, filepath: str = "delta_f_heatmap.csv") -> pd.DataFrame:
        df = pd.DataFrame(self.heatmap_data)
        df.to_csv(filepath, index=False)
        return df

    def get_ga_fitness_feedback(self) -> float:
        violations = sum(1 for log in self.audit_log if "violated" in log)
        confirmed = len(self.audit_log) - violations
        penalty = -0.1 * violations
        bonus = 0.05 * confirmed
        return penalty + bonus

    def _normalize(self, signals: np.ndarray) -> np.ndarray:
        if len(signals) < 2:
            return signals
        if self.normalize == "logret":
            return np.diff(np.log(signals + 1e-8))
        if self.normalize == "zscore":
            return (signals - np.mean(signals)) / (np.std(signals) + 1e-8)
        return signals

    def get_td_error_proxy(self, signals: np.ndarray) -> float:
        state = 0 if float(np.std(signals)) < 0.01 else 1
        action = 0
        reward = -float(np.std(signals))
        next_state = state
        q_current = self.q_table.get(state, {}).get(action, 0.0)
        q_max_next = max(self.q_table.get(next_state, {}).values() or [0.0])
        gamma = 0.99
        return reward + gamma * q_max_next - q_current

    def kalman_update(self, z: np.ndarray) -> np.ndarray:
        if len(z) == 0:
            return np.array([])
        F = np.array([[1.0]])
        H = np.array([[1.0]])
        Q = 0.01
        R = 0.1
        x = np.array([[z[0]]])
        filtered_states = [float(x[0, 0])]
        for obs in z[1:]:
            K = self.kalman_P @ H.T @ inv(H @ self.kalman_P @ H.T + R + 1e-8)
            x = F @ x + K @ (obs - H @ x)
            filtered_states.append(float(x[0, 0]))
            self.kalman_P = (np.eye(1) - K @ H) @ self.kalman_P @ F.T + Q
        return np.asarray(filtered_states, dtype=float)

    def compute_delta_f(self, states: np.ndarray) -> float:
        if len(states) < 2:
            return 0.0
        diffs = np.diff(states)
        U = float(np.mean(np.abs(diffs)))
        n_bins = min(10, max(len(states) // 20 + 1, 1))
        hist, _ = np.histogram(states, bins=n_bins)
        S = float(entropy(hist + 1e-8))
        R = float(np.std(states))
        return float(U + self.kT * S + self.alpha * R)

    def pid_adjust(self, error: float, integral: float) -> None:
        self.threshold += self.pid_kp * error + self.pid_ki * integral
        self.threshold = float(np.clip(self.threshold, 0.1, 2.0))

    async def rest_phase(self) -> None:
        await asyncio.sleep(0.1)
        self.buffer.clear()

    def _log_gate(self, status: str, value: float) -> None:
        print(f"Gate {status}: value={value:.3f}, threshold={self.threshold:.3f}")

    async def circadian_reset(self) -> None:
        while True:
            await asyncio.sleep(86400)
            self.buffer.clear()
            self.kalman_P = np.array([[0.1]])
            self.pid_integral = 0.0
            self.threshold = 0.5
            print("Circadian reset: homeostasis restored")

    def start_circadian(self) -> None:
        if self.reset_task is not None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            self._circadian_loop = loop
            self._circadian_thread = threading.Thread(
                target=loop.run_forever, daemon=True
            )
            self._circadian_thread.start()
            self.reset_task = asyncio.run_coroutine_threadsafe(
                self.circadian_reset(), loop
            )
        else:
            self._circadian_loop = loop
            self.reset_task = loop.create_task(self.circadian_reset())

    def _determine_mode(
        self,
        *,
        phase: str,
        integrity: float,
        kill_switch_active: bool,
        monotonic_status: str,
    ) -> str:
        if (
            kill_switch_active
            or integrity < 0.8
            or phase == "pre-spike"
            or monotonic_status == "violated"
        ):
            return "PoR"
        return "PoA"

    def _log_event(
        self,
        ga_phase: str,
        data: Dict[str, object],
        *,
        action_class: str,
        allowed: bool,
        mode: Optional[str] = None,
        kill_switch_active: Optional[bool] = None,
    ) -> None:
        if kill_switch_active is None:
            kill_switch_active = is_kill_switch_active()
        integrity = float(data.get("integrity", self.get_integrity_ratio()))
        phase = str(data.get("phase", "stable"))
        monotonic_status = str(data.get("monotonic", self._last_audit_status))
        resolved_mode = mode or self._determine_mode(
            phase=phase,
            integrity=integrity,
            kill_switch_active=kill_switch_active,
            monotonic_status=monotonic_status,
        )
        self.system_mode = resolved_mode
        enriched = dict(data)
        enriched.setdefault("action_class", action_class)
        enriched.setdefault("mode", resolved_mode)
        enriched.setdefault("system_mode", resolved_mode)
        enriched.setdefault("allowed", allowed)
        event = StabilizerEvent(
            epoch=self.epoch,
            ga_phase=ga_phase,
            data=enriched,
            timestamp=time.time(),
            action_class=action_class,
            mode=resolved_mode,
            allowed=allowed,
        )
        self.eventlog.append(event)
        print(
            json.dumps(
                {
                    "epoch": event.epoch,
                    "ga_phase": event.ga_phase,
                    "data": event.data,
                    "timestamp": event.timestamp,
                    "action_class": event.action_class,
                    "mode": event.mode,
                    "system_mode": event.mode,
                    "allowed": event.allowed,
                }
            )
        )

    def get_audit_log(self) -> List[str]:
        return list(self.audit_log)

    def get_safety_margin(self) -> float:
        return self.safety_margin

    def get_eventlog(self) -> List[Dict[str, object]]:
        return [
            {
                "epoch": event.epoch,
                "ga_phase": event.ga_phase,
                "data": event.data,
                "timestamp": event.timestamp,
                "action_class": event.action_class,
                "mode": event.mode,
                "system_mode": event.mode,
                "allowed": event.allowed,
            }
            for event in self.eventlog
        ]

    def get_integrity_ratio(self) -> float:
        return self.safety_margin / self.threshold if self.threshold > 0 else 0.0

    def get_system_mode(self) -> str:
        return self.system_mode

    def notify_external_block(self, *, ga_phase: str, reason: str) -> None:
        self._log_event(
            ga_phase,
            {
                "phase": "halt",
                "action": "external_block",
                "reason": reason,
                "integrity": self.get_integrity_ratio(),
                "monotonic": self._last_audit_status,
            },
            action_class="INFLUENCE_EXTERNAL",
            allowed=False,
        )

    def _extract_chunk(
        self, filtered_states: np.ndarray, chunk_length: int
    ) -> List[float]:
        if chunk_length == 0:
            return []
        if len(filtered_states) < chunk_length:
            tail = filtered_states
        else:
            tail = filtered_states[-chunk_length:]
        if len(tail) < chunk_length:
            pad_value = float(tail[-1]) if len(tail) else 0.0
            tail = np.pad(
                tail, (chunk_length - len(tail), 0), constant_values=pad_value
            )
        return [float(x) for x in tail]

    def _align_to_raw_length(self, chunk: List[float], raw_length: int) -> List[float]:
        if raw_length == len(chunk):
            return chunk
        if raw_length == 0:
            return []
        if not chunk:
            return [0.0] * raw_length
        indices = np.linspace(0, len(chunk) - 1, num=raw_length)
        resampled = np.interp(indices, np.arange(len(chunk)), chunk)
        return [float(x) for x in resampled]


__all__ = ["CNSStabilizer", "StabilizerEvent"]
