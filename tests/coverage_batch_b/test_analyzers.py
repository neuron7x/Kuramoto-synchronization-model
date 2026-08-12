# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Behavioural coverage for analytics.code_health.analyzers.

All git interactions are made hermetic either by patching the private
``_run`` helper or by patching ``subprocess.run`` on the module, so no real
git process is ever spawned.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

import pytest

from analytics.code_health import analyzers
from analytics.code_health.analyzers import (
    CallGraphAnalyzer,
    CouplingAnalyzer,
    GitHistoryAnalyzer,
    PythonFileAnalyzer,
    RiskHeuristics,
    compute_trends,
    load_previous_snapshot,
    rolling_average,
    save_snapshot,
)

_HEX = "a" * 40
_HEX2 = "b" * 40


class _FakeCompleted:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


def _write(tmp_path: Path, name: str, source: str) -> Path:
    p = tmp_path / name
    p.write_text(source, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# PythonFileAnalyzer
# ---------------------------------------------------------------------------

_SAMPLE = '''
import os

def top(x):
    if x > 0:
        return os.getpid()
    for i in range(x):
        pass
    return [i for i in range(3)]

class Widget:
    def method(self, a, b):
        return a and b or a

    async def afetch(self):
        with open("f") as fh:
            return fh.read()
'''


def test_parse_is_cached(tmp_path: Path) -> None:
    p = _write(tmp_path, "m.py", _SAMPLE)
    analyzer = PythonFileAnalyzer(p)
    tree1 = analyzer.parse()
    tree2 = analyzer.parse()
    assert tree1 is tree2


def test_iter_functions_qualnames_and_complexity(tmp_path: Path) -> None:
    p = _write(tmp_path, "m.py", _SAMPLE)
    funcs = {f.qualname: f for f in PythonFileAnalyzer(p).iter_functions()}
    assert "m.top" in funcs
    assert "m.Widget.method" in funcs
    assert "m.Widget.afetch" in funcs
    # top has: base1 + if + for + listcomp + boolop-less => complexity > 1
    assert funcs["m.top"].cyclomatic_complexity >= 4
    # method uses `and`/`or` boolops which add per extra value
    assert funcs["m.Widget.method"].cyclomatic_complexity >= 2
    # calls collected: os.getpid -> attr 'getpid', range -> name 'range'
    assert "getpid" in funcs["m.top"].calls
    assert "range" in funcs["m.top"].calls


def test_infer_end_line_normal(tmp_path: Path) -> None:
    p = _write(tmp_path, "m.py", "def f():\n    x = 1\n    return x\n")
    analyzer = PythonFileAnalyzer(p)
    fn = next(iter(analyzer.iter_functions()))
    # normal path uses end_lineno (line 3 is the last line of the body)
    assert fn.end_line == 3
    assert fn.start_line == 1


def test_infer_end_line_fallback_without_end_lineno(tmp_path: Path) -> None:
    import ast

    analyzer = PythonFileAnalyzer(_write(tmp_path, "m.py", "x = 1\n"))
    # A node whose end_lineno is absent forces the walk-based fallback.
    module = ast.parse("a = 1\nb = 2\nc = 3\n")
    node = module.body[-1]  # `c = 3` on line 3
    object.__setattr__(node, "end_lineno", None)
    assert analyzer._infer_end_line(node) == 3


def test_collect_calls_attribute_and_name(tmp_path: Path) -> None:
    p = _write(tmp_path, "m.py", "def g():\n    obj.do()\n    plain()\n")
    fn = next(iter(PythonFileAnalyzer(p).iter_functions()))
    assert {"do", "plain"} <= fn.calls


# ---------------------------------------------------------------------------
# CallGraphAnalyzer
# ---------------------------------------------------------------------------


def test_call_graph_fan_in_fan_out(tmp_path: Path) -> None:
    source = (
        "def a():\n    b()\n\n"
        "def b():\n    c()\n\n"
        "def c():\n    pass\n"
    )
    p = _write(tmp_path, "m.py", source)
    funcs = list(PythonFileAnalyzer(p).iter_functions())
    graph = CallGraphAnalyzer()
    graph.ingest(funcs)
    assert graph.fan_out("m.a") == 1
    assert graph.fan_in("m.b") == 1
    assert graph.fan_in("m.c") == 1


def test_call_graph_unknown_node_returns_zero() -> None:
    graph = CallGraphAnalyzer()
    assert graph.fan_in("missing") == 0
    assert graph.fan_out("missing") == 0


# ---------------------------------------------------------------------------
# CouplingAnalyzer
# ---------------------------------------------------------------------------


def test_coupling_counts_unique_top_level_modules(tmp_path: Path) -> None:
    source = (
        "import os\n"
        "import os.path\n"
        "from collections import OrderedDict\n"
        "from . import sibling\n"
        "import m\n"  # self reference discarded
    )
    p = _write(tmp_path, "m.py", source)
    # os (from os and os.path collapse to 'os'), collections, and the relative
    # import (module is None -> ignored). self 'm' discarded.
    assert CouplingAnalyzer(p).measure() == 2


def test_coupling_relative_import_without_module(tmp_path: Path) -> None:
    p = _write(tmp_path, "m.py", "from . import x\n")
    assert CouplingAnalyzer(p).measure() == 0


# ---------------------------------------------------------------------------
# GitHistoryAnalyzer — using patched _run
# ---------------------------------------------------------------------------


def _git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outputs: dict[str, str]) -> GitHistoryAnalyzer:
    analyzer = GitHistoryAnalyzer(tmp_path)

    def fake_run(*args: str, check: bool = False) -> _FakeCompleted:
        joined = " ".join(args)
        for key, value in outputs.items():
            if key in joined:
                return _FakeCompleted(value)
        return _FakeCompleted("")

    monkeypatch.setattr(analyzer, "_run", fake_run)
    return analyzer


def test_run_invokes_subprocess(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_subprocess_run(cmd: List[str], **kwargs: object) -> _FakeCompleted:
        captured["cmd"] = cmd
        captured["cwd"] = kwargs.get("cwd")
        return _FakeCompleted("ok")

    monkeypatch.setattr(analyzers.subprocess, "run", fake_subprocess_run)
    analyzer = GitHistoryAnalyzer(tmp_path)
    result = analyzer._run("status", "--short")
    assert result.stdout == "ok"
    assert captured["cmd"] == ["git", "status", "--short"]
    assert captured["cwd"] == tmp_path


def test_change_frequency_and_churn_with_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    numstat = "\n".join(
        [
            _HEX,
            "10\t2\tfile_a.py",
            "5\t0\tfile_a.py",  # same commit again -> churn adds, freq unchanged
            "-\t-\t-",  # path '-' skip
            "-\t-\tfile_b.py",  # non-digit churn, still frequency++
            "bad line",  # len != 3 -> skip
            _HEX2,
            "3\t1\tfile_a.py",  # new commit -> frequency++
            "",  # empty -> skip
        ]
    )
    analyzer = _git(tmp_path, monkeypatch, {"--numstat --pretty=%H": numstat})
    fa = tmp_path / "file_a.py"
    assert analyzer.file_change_frequency(fa) == 2
    # 10+2 (commit1) + 5+0 (commit1) + 3+1 (commit2) = 21
    assert analyzer.file_churn(fa) == 21
    # file_b churn stayed 0 (non-digit), frequency 1
    fb = tmp_path / "file_b.py"
    assert analyzer.file_churn(fb) == 0
    assert analyzer.file_change_frequency(fb) == 1
    # unknown file -> defaults
    assert analyzer.file_change_frequency(tmp_path / "nope.py") == 0


def test_interface_instability_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    diff = "\n".join(
        [
            _HEX,
            "diff --git a/foo.py b/foo.py",
            "--- a/foo.py",
            "+++ b/foo.py",
            "+def new_func():",
            "+    pass",
            "-class Old:",  # removed interface line counts too
            "+regular = 1",
            "diff --git a//dev/null b//dev/null",
            "+ghost",  # current_file == /dev/null -> skip
            "diff --git a/bin.dat b/bin.dat",
            "Binary files a/bin.dat and b/bin.dat differ",
        ]
    )
    analyzer = _git(tmp_path, monkeypatch, {"-p": diff})
    stability = analyzer.interface_instability(tmp_path / "foo.py")
    # foo.py total changes: def, pass, class, regular = 4; interface: def, class = 2
    assert stability == pytest.approx(1.0 - 2 / 4)
    # cached second call
    assert analyzer.interface_instability(tmp_path / "foo.py") == pytest.approx(0.5)
    # unknown file -> 1.0
    assert analyzer.interface_instability(tmp_path / "missing.py") == 1.0


def test_interface_instability_zero_total_branch(tmp_path: Path) -> None:
    analyzer = GitHistoryAnalyzer(tmp_path)
    analyzer._interface_cache[365] = {"z.py": (0, 0)}
    assert analyzer.interface_instability(tmp_path / "z.py") == 1.0


def test_interface_instability_content_before_diff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A leading '+' line before any diff header exercises the `not current_file` branch.
    diff = "\n".join([_HEX, "+orphan line", "diff --git a/x.py b/x.py", "+def q():"])
    analyzer = _git(tmp_path, monkeypatch, {"-p": diff})
    # x.py: total 1, interface 1 -> stability 0
    assert analyzer.interface_instability(tmp_path / "x.py") == pytest.approx(0.0)


def test_hot_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = "\n".join(["a.py", "a.py", "b.py", "", "  ", "a.py", "c.py"])
    analyzer = _git(tmp_path, monkeypatch, {"--name-only": out})
    hot = analyzer.hot_files(limit=2)
    assert hot[0] == ("a.py", 3)
    assert len(hot) == 2


def test_developer_activity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = "\n".join(
        [
            "99\t1\torphan.py",  # numstat before any author -> author None branch
            "Alice",
            "10\t2\tfile_a.py",
            "5\t0\tfile_b.py",
            "bad two cols",  # len != 3 skip
            "",  # empty skip
            "Bob",
            "3\t1\tfile_a.py",
            "-\t-\tbinary.png",  # non-digit churn but still counts file
        ]
    )
    analyzer = _git(tmp_path, monkeypatch, {"--numstat --pretty=%an": log})
    devs = analyzer.developer_activity()
    by_name = {d.author: d for d in devs}
    assert by_name["Alice"].churn == 17
    assert by_name["Alice"].files_touched == 2
    assert by_name["Alice"].commits == 1
    assert "file_a.py" in by_name["Alice"].hotspots
    assert by_name["Bob"].churn == 4
    # A numstat row for a binary file ("-\t-\tpath") begins with '-', which is
    # not a digit, so developer_activity treats it as an author line rather than
    # a file row. Bob therefore only touched file_a.py.
    assert by_name["Bob"].files_touched == 1
    # sorted by churn desc
    assert devs[0].author == "Alice"


def test_relative_inside_and_outside(tmp_path: Path) -> None:
    analyzer = GitHistoryAnalyzer(tmp_path)
    inside = tmp_path / "sub" / "f.py"
    assert analyzer._relative(inside) == str(Path("sub") / "f.py")
    outside = Path("/some/other/root/g.py")
    assert analyzer._relative(outside) == str(outside)


def test_run_real_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Cover the real _run body (check kwarg default False) with subprocess patched.
    def fake(cmd: List[str], **kwargs: object) -> _FakeCompleted:
        assert kwargs["check"] is False
        return _FakeCompleted("x")

    monkeypatch.setattr(analyzers.subprocess, "run", fake)
    analyzer = GitHistoryAnalyzer(tmp_path)
    assert analyzer._run("log").stdout == "x"


# ---------------------------------------------------------------------------
# RiskHeuristics
# ---------------------------------------------------------------------------


def test_risk_heuristics_all_factors() -> None:
    heur = RiskHeuristics(
        {
            "complexity": 10,
            "max_complexity": 15,
            "fan_in": 10,
            "fan_out": 10,
            "churn": 50,
            "change_frequency": 10,
            "interface_stability": 0.8,
        }
    )
    profile = heur.evaluate(
        avg_complexity=40,
        max_complexity=60,
        fan_in=40,
        fan_out=40,
        churn=500,
        change_frequency=60,
        interface_stability=0.2,
    )
    assert profile.risk_score == 1.0  # clamped
    assert "High average cyclomatic complexity" in profile.contributing_factors
    assert "Elevated worst-case complexity" in profile.contributing_factors
    assert "High fan-in indicates coupling" in profile.contributing_factors
    assert "High fan-out indicates broad dependencies" in profile.contributing_factors
    assert "Significant churn in recent history" in profile.contributing_factors
    assert "Frequent modifications make this area unstable" in profile.contributing_factors
    assert "Public interface changes too frequently" in profile.contributing_factors
    # all recommendation branches, including interface_stability < 0.5
    recs = profile.recommendations
    assert any("smaller units" in r for r in recs)
    assert any("facades" in r for r in recs)
    assert any("abstractions" in r for r in recs)
    assert any("regression tests" in r for r in recs)
    assert any("hardening sprint" in r for r in recs)
    assert any("version interfaces" in r for r in recs)


def test_risk_heuristics_no_factors_uses_defaults() -> None:
    heur = RiskHeuristics({})  # thresholds absent -> .get defaults used
    profile = heur.evaluate(
        avg_complexity=1,
        max_complexity=1,
        fan_in=1,
        fan_out=1,
        churn=1,
        change_frequency=1,
        interface_stability=1.0,
    )
    assert profile.risk_score == 0.0
    assert profile.contributing_factors == []
    assert profile.recommendations == []


def test_risk_heuristics_partial_interface_between_half_and_threshold() -> None:
    heur = RiskHeuristics({"interface_stability": 0.9})
    profile = heur.evaluate(
        avg_complexity=1,
        max_complexity=1,
        fan_in=1,
        fan_out=1,
        churn=1,
        change_frequency=1,
        interface_stability=0.7,  # < 0.9 threshold but > 0.5
    )
    assert "Public interface changes too frequently" in profile.contributing_factors
    # interface not < 0.5 -> no 'version interfaces' recommendation
    assert not any("version interfaces" in r for r in profile.recommendations)


# ---------------------------------------------------------------------------
# snapshot + trend helpers
# ---------------------------------------------------------------------------


def test_load_previous_snapshot_missing(tmp_path: Path) -> None:
    assert load_previous_snapshot(tmp_path / "nope.json") is None


def test_load_previous_snapshot_valid(tmp_path: Path) -> None:
    f = tmp_path / "h.json"
    f.write_text('{"a.py": {"avg_cyclomatic_complexity": 3.0}}', encoding="utf-8")
    data = load_previous_snapshot(f)
    assert data == {"a.py": {"avg_cyclomatic_complexity": 3.0}}


def test_load_previous_snapshot_invalid_json(tmp_path: Path) -> None:
    f = tmp_path / "bad.json"
    f.write_text("{not json", encoding="utf-8")
    assert load_previous_snapshot(f) is None


def test_save_snapshot_roundtrip(tmp_path: Path) -> None:
    f = tmp_path / "snap.json"
    save_snapshot(f, {"a.py": {"x": 1.0}})
    assert load_previous_snapshot(f) == {"a.py": {"x": 1.0}}


def test_compute_trends_none_previous() -> None:
    assert compute_trends(previous=None, current={"a": {"avg_cyclomatic_complexity": 1.0}}) == []


def test_compute_trends_values() -> None:
    previous = {"a.py": {"avg_cyclomatic_complexity": 2.0}, "b.py": {}}
    current = {
        "a.py": {"avg_cyclomatic_complexity": 5.0},
        "b.py": {"avg_cyclomatic_complexity": 1.0},  # prev missing -> skip
        "c.py": {},  # current missing -> skip
    }
    trends = compute_trends(previous=previous, current=current)
    assert trends == [("a.py", 2.0, 5.0)]


def test_rolling_average() -> None:
    assert rolling_average([]) == 0.0
    assert rolling_average([2.0, 4.0]) == 3.0
