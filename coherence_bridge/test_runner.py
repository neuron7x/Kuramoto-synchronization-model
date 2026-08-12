# mypy: ignore-errors
# ruff: noqa: E402
#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""One-command test runner with human-readable report.

Usage:
    python coherence_bridge/test_runner.py           # full report
    python coherence_bridge/test_runner.py --quick    # fast smoke only
    python coherence_bridge/test_runner.py --bench    # include benchmark
"""

from __future__ import annotations

import math
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_repo = str(Path(__file__).resolve().parent.parent)
if _repo not in sys.path:
    sys.path.insert(0, _repo)

import numpy as np


@dataclass
class PhaseResult:
    name: str
    passed: bool
    detail: str
    duration_ms: float


def _phase(name):
    def decorator(fn):
        fn._phase_name = name
        return fn

    return decorator


class TestRunner:
    def __init__(self):
        self.results = []

    def run(self, include_bench=False):
        phases = [
            self._membrane,
            self._gamma,
            self._ricci,
            self._lyapunov,
            self._invariants,
            self._decisions,
            self._risk_gate,
            self._features,
            self._metacognition,
            self._nan_hardening,
            self._determinism,
        ]
        if include_bench:
            phases.append(self._benchmark)

        all_pass = True
        for phase in phases:
            t0 = time.perf_counter()
            try:
                detail = phase()
                dur = (time.perf_counter() - t0) * 1000
                self.results.append(PhaseResult(phase._phase_name, True, detail, dur))
            except Exception as exc:
                dur = (time.perf_counter() - t0) * 1000
                self.results.append(PhaseResult(phase._phase_name, False, str(exc)[:120], dur))
                all_pass = False

        self._print_report()
        return all_pass

    def _print_report(self):
        w = 62
        print()
        print("=" * w)
        print("  CoherenceBridge — Test Report")
        print("  feat/askar-ots | neuron7xLab/GeoSync")
        print("=" * w)
        print()

        total_ms = sum(r.duration_ms for r in self.results)
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)

        for r in self.results:
            icon = "✓" if r.passed else "✗"
            ms = f"{r.duration_ms:.0f}ms"
            print(f"  {icon} {r.name:<30s} {ms:>8s}  {r.detail}")

        print()
        print("-" * w)
        status = "ALL PASS" if passed == total else f"{total - passed} FAILED"
        print(f"  {passed}/{total} phases | {total_ms:.0f}ms total | {status}")
        print("=" * w)

    @_phase("Architecture membrane")
    def _membrane(self):
        import ast

        for f in Path("geosync").rglob("*.py"):
            if "__pycache__" in str(f):
                continue
            try:
                tree = ast.parse(f.read_text())
            except SyntaxError:
                continue
            for n in ast.walk(tree):
                if isinstance(n, ast.ImportFrom) and n.module and "coherence_bridge" in n.module:
                    raise AssertionError(f"{f} imports coherence_bridge")
        return "0 violations"

    @_phase("Gamma estimator (PSD)")
    def _gamma(self):
        from geosync.estimators.gamma_estimator import PSDGammaEstimator

        est = PSDGammaEstimator()
        g = est.compute(np.cumsum(np.random.default_rng(42).standard_normal(1024)))
        assert -5 <= g.value <= 5 and g.value != 1.0
        assert abs(g.hurst - (g.value - 1.0) / 2.0) < 1e-3
        return f"γ={g.value:.3f} H={g.hurst:.3f} CI=[{g.ci_low:.2f},{g.ci_high:.2f}]"

    @_phase("Ricci curvature (topology)")
    def _ricci(self):
        from geosync.estimators.augmented_ricci import AugmentedFormanRicci

        rng = np.random.default_rng(43)
        r = AugmentedFormanRicci().compute(
            rng.standard_normal((200, 1)) + rng.standard_normal((200, 5)) * 0.1,
            [f"A{i}" for i in range(5)],
        )
        assert 0 <= r.fragile_fraction <= 1
        return f"κ={r.mean_kappa:.3f} edges={r.n_edges} fragile={r.fragile_fraction:.0%}"

    @_phase("Lyapunov exponent (chaos)")
    def _lyapunov(self):
        from geosync.estimators.lyapunov_estimator import RosensteinLyapunov

        x = [0.5]
        for _ in range(2500):
            x.append(3.9 * x[-1] * (1 - x[-1]))
        lr = RosensteinLyapunov().compute(np.array(x[500:]))
        assert lr.is_valid and lr.is_chaotic
        return f"λ={lr.lambda_max:.4f} T₂={lr.doubling_time:.1f}"

    @_phase("Formal invariants (T1-T13)")
    def _invariants(self):
        from coherence_bridge.invariants import verify_signal
        from coherence_bridge.mock_engine import MockEngine
        from coherence_bridge.server import _sanitize_signal

        me = MockEngine()
        v = 0
        for _ in range(50):
            for inst in me.instruments:
                sig = me.get_signal(inst)
                assert sig is not None
                for r in verify_signal(_sanitize_signal(sig), raise_on_failure=False):
                    if not r.passed:
                        v += 1
        assert v == 0, f"{v} violations"
        return "0 violations / 250 signals"

    @_phase("Decision engine (TRADE/OBS/ABORT)")
    def _decisions(self):
        from coherence_bridge.decision_engine import GeoSyncDecisionEngine
        from coherence_bridge.mock_engine import MockEngine

        me = MockEngine()
        dec = GeoSyncDecisionEngine(engine=me)
        res = Counter()
        for i in range(200):
            sig = me.get_signal(me.instruments[i % len(me.instruments)])
            assert sig is not None
            out = dec.process(sig, 1.0)
            assert 0 <= out.adjusted_size <= 1.0
            res[out.decision.value] += 1
        assert res["TRADE"] > 0
        return " ".join(f"{k}={v}" for k, v in sorted(res.items()))

    @_phase("Risk gate (fail-closed)")
    def _risk_gate(self):
        from coherence_bridge.mock_engine import MockEngine
        from coherence_bridge.risk_gate import CoherenceRiskGate

        me = MockEngine()
        gate = CoherenceRiskGate(engine=me, fail_closed=True)
        for inst in me.instruments:
            for sz in [0.001, 1.0, 100.0]:
                d = gate.apply(inst, sz)
                assert 0 <= d.adjusted_size <= sz
        assert not gate.apply("UNKNOWN", 1.0).allowed
        return "never amplifies, fail-closed on unknown"

    @_phase("Features (13, 0 NaN)")
    def _features(self):
        from coherence_bridge.decision_engine import GeoSyncDecisionEngine
        from coherence_bridge.feature_exporter import RegimeFeatureExporter
        from coherence_bridge.mock_engine import MockEngine
        from geosync.neuroeconomics.metacognition import MetaCognitionLayer

        me = MockEngine()
        dec = GeoSyncDecisionEngine(engine=me)
        meta = MetaCognitionLayer()
        sig = me.get_signal("EURUSD")
        assert sig is not None
        out = dec.process(sig)
        st = meta.observe(sig, out, dec._memory)
        p = RegimeFeatureExporter.to_ml_features(sig)
        m = meta.get_meta_features(st)
        all_f = {**p, **m}
        assert len(all_f) == 13 and all(math.isfinite(v) for v in all_f.values())
        return f"{len(all_f)} features, all finite"

    @_phase("MetaCognition (γ₂ + witness)")
    def _metacognition(self):
        from coherence_bridge.decision_engine import GeoSyncDecisionEngine
        from coherence_bridge.mock_engine import MockEngine
        from geosync.neuroeconomics.metacognition import MetaCognitionLayer

        me = MockEngine()
        dec = GeoSyncDecisionEngine(engine=me)
        meta = MetaCognitionLayer()
        for i in range(100):
            sig = me.get_signal(me.instruments[i % len(me.instruments)])
            assert sig is not None
            out = dec.process(sig, 1.0)
            st = meta.observe(sig, out, dec._memory)
            assert 0.1 <= st.kelly_meta_multiplier <= 1.0
        return f"γ₂={st.gamma_model.gamma_model:.3f} regime={st.model_regime.value}"

    @_phase("NaN hardening (poison signal)")
    def _nan_hardening(self):
        from coherence_bridge.feature_exporter import RegimeFeatureExporter
        from coherence_bridge.server import _sanitize_signal

        poison = {
            "timestamp_ns": 1700000000000000000,
            "instrument": "EURUSD",
            "gamma": float("nan"),
            "order_parameter_R": float("inf"),
            "ricci_curvature": float("-inf"),
            "lyapunov_max": float("nan"),
            "regime": "UNKNOWN",
            "regime_confidence": float("nan"),
            "regime_duration_s": -1.0,
            "signal_strength": float("nan"),
            "risk_scalar": float("nan"),
            "sequence_number": 0,
        }
        clean = _sanitize_signal(poison)
        assert clean["risk_scalar"] == 0.0
        features = RegimeFeatureExporter.to_ml_features(clean)
        for v in features.values():
            assert math.isfinite(v)
        return "all NaN → 0, features finite"

    @_phase("Determinism (50 steps)")
    def _determinism(self):
        from coherence_bridge.mock_engine import MockEngine

        e1, e2 = MockEngine(), MockEngine()
        for _ in range(50):
            s1 = e1.get_signal("EURUSD")
            s2 = e2.get_signal("EURUSD")
            assert s1 is not None and s2 is not None
            assert s1["sequence_number"] == s2["sequence_number"]
            assert s1["regime"] == s2["regime"]
        return "50 steps identical"

    @_phase("Benchmark (3000 FX ticks)")
    def _benchmark(self):
        from scipy.signal import welch

        from coherence_bridge.risk import compute_risk_scalar
        from geosync.neuroeconomics.flow_controller import FlowController

        np.random.seed(2026)
        returns = np.random.normal(0, 0.00005, 3000)
        returns[500:800] *= 4
        returns[1200:1400] *= 6
        fc = FlowController()
        decisions = Counter()
        t0 = time.perf_counter()
        for i in range(300, 3000):
            w = returns[i - 300 : i]
            f, pxx = welch(w, fs=1.0, nperseg=64)
            mask = (f > 0.001) & (f < 0.5) & (pxx > 0)
            gamma = (
                abs(np.polyfit(np.log(f[mask] + 1e-12), np.log(pxx[mask] + 1e-12), 1)[0])
                if mask.sum() >= 4
                else 1.0
            )
            sig = {
                "timestamp_ns": 1700000000000000000 + i * 60000000000,
                "instrument": "EURUSD",
                "gamma": round(gamma, 6),
                "order_parameter_R": 0.3,
                "ricci_curvature": 0.0,
                "lyapunov_max": 0.01,
                "regime": "METASTABLE",
                "regime_confidence": 0.7,
                "regime_duration_s": 1.0,
                "signal_strength": 0.0,
                "risk_scalar": round(compute_risk_scalar(gamma), 4),
                "sequence_number": i,
            }
            flow = fc.process(sig, 1.0, outcome=returns[i] * 1000)
            decisions[flow.decision.value] += 1
        dur = (time.perf_counter() - t0) * 1000
        total = sum(decisions.values())
        dist = " ".join(f"{k}={v / total:.0%}" for k, v in sorted(decisions.items()))
        return f"{total} ticks in {dur:.0f}ms | {dist}"


def main():
    runner = TestRunner()
    ok = runner.run(include_bench="--bench" in sys.argv)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
