# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Teeth for the operator-attention signal layer.

The signal's whole value is that it raises the right band: RED only when a
metric REGRESSED below its frozen value, WARN when a metric is intrinsically
weak (or a claim rides a reduced floor), OK otherwise. Every banding boundary
is pinned here with a positive control (the signal fires) and a negative control
(it stays silent), so a mutated comparison flips an assertion.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "emit_metric_signals.py"
_spec = importlib.util.spec_from_file_location("emit_metric_signals", _MOD_PATH)
assert _spec and _spec.loader
sig = importlib.util.module_from_spec(_spec)
# Register before exec: the frozen dataclass resolves its field types via
# sys.modules[cls.__module__] during asdict/instantiation.
sys.modules["emit_metric_signals"] = sig
_spec.loader.exec_module(sig)


def _probe(pid: str, axis: str, score: float) -> dict:
    return {"id": pid, "axis": axis, "procedure": "p", "state": "MEASURED", "score": score}


# --- band_signal: the three bands and their boundaries -----------------------


def test_band_red_only_on_regression() -> None:
    """A score below its frozen value is RED; at or above it is never RED."""
    below = sig.band_signal(0.80, 0.90, source="ten_axes", metric="m")
    assert below.level == sig.RED and below.direction == "REGRESSED"
    # Negative control: exactly at the frozen value is NOT a regression.
    at = sig.band_signal(0.90, 0.90, source="ten_axes", metric="m")
    assert at.level != sig.RED


def test_band_warn_on_weak_absolute_not_on_healthy() -> None:
    """Below the attention floor (but not regressed) is WARN; above it is OK."""
    weak = sig.band_signal(0.30, 0.30, source="ten_axes", metric="m", attention_floor=0.5)
    assert weak.level == sig.WARN and weak.direction == "WEAK_ABSOLUTE"
    # Negative control: a healthy score at its floor is OK, not WARN.
    healthy = sig.band_signal(0.92, 0.92, source="ten_axes", metric="m", attention_floor=0.5)
    assert healthy.level == sig.OK


def test_band_attention_floor_is_inclusive() -> None:
    """Exactly at the attention floor is OK -- the weak band is strictly below it."""
    assert sig.band_signal(0.5, 0.5, source="ten_axes", metric="m", attention_floor=0.5).level == sig.OK


def test_regression_dominates_weakness() -> None:
    """A weak AND regressed metric reports RED, not WARN -- breach outranks weak."""
    s = sig.band_signal(0.20, 0.30, source="ten_axes", metric="m", attention_floor=0.5)
    assert s.level == sig.RED


# --- signals_from_reports: the two metric families ---------------------------


def test_ten_axis_regression_surfaces_red() -> None:
    baseline = {"probes": [_probe("p1", "precision", 0.90)]}
    current = {"weakest_axis": "precision", "probes": [_probe("p1", "precision", 0.80)]}
    out = sig.signals_from_reports(current, baseline, {})
    reds = [s for s in out if s.level == sig.RED]
    assert [s.metric for s in reds] == ["p1"]


def test_healthy_ten_axis_emits_no_red_or_warn() -> None:
    baseline = {"probes": [_probe("p1", "precision", 0.90)]}
    current = {"weakest_axis": "precision", "probes": [_probe("p1", "precision", 0.93)]}
    out = sig.signals_from_reports(current, baseline, {})
    assert all(s.level == sig.OK for s in out)


def test_reduced_mutation_floor_is_warn_full_floor_is_silent() -> None:
    ledger = {
        "modules": {
            "a.py": {"floor": 0.85, "killed": 6, "total": 7},
            "b.py": {"floor": 1.0, "killed": 5, "total": 5},
        }
    }
    out = sig.signals_from_reports({"probes": []}, {"probes": []}, ledger)
    warns = [s for s in out if s.source == "mutation_kill"]
    assert [s.metric for s in warns] == ["a.py"]  # b.py at floor 1.0 is silent
    assert warns[0].level == sig.WARN


# --- fail-closed integrity: the signal must never go silently green ----------


def test_unbaselined_probe_is_red_not_silently_ok() -> None:
    """A measured probe with no frozen floor cannot be verified -> RED.

    First-principles: a safety signal fails CLOSED. Without a baseline entry the
    probe's regression is invisible, so it must NOT read OK/WARN. Guards the
    fail-open where a stale/missing baseline made a catastrophic score look fine.
    """
    current = {"weakest_axis": "beauty", "probes": [_probe("orphan", "beauty", 0.05)]}
    out = sig.signals_from_reports(current, {"probes": []}, {})
    (s,) = out
    assert s.level == sig.RED
    assert s.direction == "UNBASELINED"


def test_renamed_probe_hiding_a_regression_is_red() -> None:
    """A real regression hidden behind a renamed probe id must surface as RED.

    Baseline knows `p1` at 0.90; the current report ships `renamed` at 0.10. The
    regression is invisible by id-match, so the unbaselined probe fails closed.
    """
    current = {"weakest_axis": "completeness", "probes": [_probe("renamed", "completeness", 0.10)]}
    baseline = {"probes": [_probe("p1", "completeness", 0.90)]}
    assert sig.worst([s.level for s in sig.signals_from_reports(current, baseline, {})]) == sig.RED


def test_empty_report_is_red_not_ok() -> None:
    """A composition report with no measured probe is RED, not a silent OK.

    An empty/broken build_report watches nothing; the signal must say so.
    """
    out = sig.signals_from_reports({"probes": []}, {"probes": []}, {})
    assert [s.direction for s in out] == ["EMPTY_REPORT"]
    assert out[0].level == sig.RED


def test_signals_are_reproducible_across_runs() -> None:
    """Reproducibility (axis 10): identical inputs yield byte-identical signals."""
    from dataclasses import asdict

    current = {"weakest_axis": "precision", "probes": [_probe("p1", "precision", 0.93)]}
    baseline = {"probes": [_probe("p1", "precision", 0.90)]}
    ledger = {"modules": {"a.py": {"floor": 0.85, "killed": 6, "total": 7}}}
    first = [asdict(s) for s in sig.signals_from_reports(current, baseline, ledger)]
    second = [asdict(s) for s in sig.signals_from_reports(current, baseline, ledger)]
    assert first == second


def test_verdict_axis_label_only_on_the_weakest_axis() -> None:
    """The `[VERDICT AXIS]` note keys off `axis == weakest`, never its negation."""
    probes = [_probe("weak", "completeness", 0.40), _probe("other", "precision", 0.40)]
    out = sig.signals_from_reports(
        {"weakest_axis": "completeness", "probes": probes}, {"probes": probes}, {}
    )
    by = {s.metric: s for s in out}
    assert "VERDICT AXIS" in by["weak"].detail
    assert "VERDICT AXIS" not in by["other"].detail


def test_measured_filter_skips_probes_missing_a_score() -> None:
    """A probe not MEASURED-with-score is skipped in both current and baseline.

    Pins the two membership guards (:147 baseline comprehension `state==MEASURED
    and 'score' in p`, :151 current-probe skip `state!=MEASURED or 'score' not
    in probe`). A malformed MEASURED-without-score probe must be dropped, not
    dereferenced -- the mutated boolean would let it through and raise KeyError.
    """
    malformed = {"id": "bad", "axis": "precision", "state": "MEASURED"}  # no 'score'
    current = {"weakest_axis": "precision", "probes": [malformed, _probe("ok", "precision", 0.9)]}
    baseline = {"probes": [malformed, _probe("ok", "precision", 0.9)]}
    out = sig.signals_from_reports(current, baseline, {})
    assert [s.metric for s in out] == ["ok"]  # 'bad' skipped, no KeyError


def test_main_is_fail_closed_and_reports_bands(monkeypatch, tmp_path, capsys) -> None:
    """main() returns 1 on RED, 0 otherwise, and its output/artifact match band.

    Pins :268 `overall == RED and not warn_only` (fail-closed exit), :257
    `overall == OK` (which banner), :260 `overall == RED` (BREACH vs ATTENTION),
    and :246 the per-level counts. build_report and the baseline loads are
    stubbed so the contract is tested without an 11s live measurement.
    """
    import json as _json
    import types

    artifact = tmp_path / "signals.json"
    frozen = {"score": 0.90}
    monkeypatch.setattr(sig, "SIGNAL_ARTIFACT", artifact)
    monkeypatch.setattr(
        sig, "_load", lambda p: {"probes": [_probe("p1", "precision", frozen["score"])]}
        if p == sig.TEN_AXES_BASELINE else {}
    )

    def _install(score: float, frozen_score: float) -> None:
        frozen["score"] = frozen_score
        fake = types.ModuleType("check_ten_axes")
        fake.build_report = lambda: {
            "weakest_axis": "precision",
            "probes": [_probe("p1", "precision", score)],
        }
        monkeypatch.setitem(sys.modules, "check_ten_axes", fake)

    # Regressed below frozen 0.90 -> RED, BREACH banner, count RED==1, exit 1.
    _install(0.80, 0.90)
    assert sig.main([]) == 1
    assert "RED (BREACH)" in capsys.readouterr().out
    assert _json.loads(artifact.read_text())["counts"]["RED"] == 1
    assert sig.main(["--warn-only"]) == 0  # surfaced but not failing
    capsys.readouterr()  # drain the --warn-only output before the next capture

    # Weak absolute (below 0.5) but NOT regressed (== frozen) -> WARN, exit 0.
    _install(0.40, 0.40)
    assert sig.main([]) == 0
    out_warn = capsys.readouterr().out
    assert "WARN (ATTENTION)" in out_warn
    assert "BREACH" not in out_warn

    # Healthy and above frozen -> OK banner, exit 0.
    _install(0.95, 0.90)
    assert sig.main([]) == 0
    assert "OPERATOR SIGNAL: OK" in capsys.readouterr().out


def test_worst_precedence_red_over_warn_over_ok() -> None:
    assert sig.worst([sig.OK, sig.WARN, sig.RED]) == sig.RED
    assert sig.worst([sig.OK, sig.WARN]) == sig.WARN
    assert sig.worst([sig.OK]) == sig.OK
    assert sig.worst([]) == sig.OK
