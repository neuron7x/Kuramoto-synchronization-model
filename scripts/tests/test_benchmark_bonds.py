from __future__ import annotations

import types

import pytest

import scripts.benchmark_bonds as bench


def test_main_passes_with_small_delta(monkeypatch) -> None:
    monkeypatch.setattr(
        bench, "run_benchmark", lambda iterations=200: {"dFdt_mean": 0.0, "dFdt_min": 0.0, "dFdt_max": 0.0, "samples": 1}
    )
    monkeypatch.setattr(
        bench.argparse.ArgumentParser,
        "parse_args",
        lambda self: types.SimpleNamespace(target_dF=1e-10, iterations=10),
    )

    bench.main()  # should not raise


def test_main_exits_on_regression(monkeypatch) -> None:
    monkeypatch.setattr(
        bench, "run_benchmark", lambda iterations=200: {"dFdt_mean": 5e-10, "dFdt_min": 0.0, "dFdt_max": 1.0, "samples": 3}
    )
    monkeypatch.setattr(
        bench.argparse.ArgumentParser,
        "parse_args",
        lambda self: types.SimpleNamespace(target_dF=1e-10, iterations=10),
    )

    with pytest.raises(SystemExit):
        bench.main()
