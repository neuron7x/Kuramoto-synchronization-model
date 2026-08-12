# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Branch-level coverage for private helpers in ``geosync.cli.geosync_cli``.

These tests exercise the pure helper functions directly so every error and
fallback branch is reached without spinning up the full command machinery.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

import geosync.cli.geosync_cli as gc
from core.config.cli_models import (
    DeploymentConfig,
    Environment,
    FeatureFrameSourceConfig,
    FeatureParitySpecConfig,
    StrategyConfig,
)
from core.utils.dataframe_io import MissingParquetDependencyError


def _make_deploy_cfg(**kubectl: Any) -> DeploymentConfig:
    return DeploymentConfig(
        name="dep",
        environment=Environment.STAGE,
        strategy="alpha",
        artifact="ghcr.io/x@sha256:1",
        kubectl=kubectl or {},
    )


# --------------------------------------------------------------------------
# hashing / byte writers
# --------------------------------------------------------------------------
def test_hash_and_existing_digest(tmp_path: Path) -> None:
    assert gc._hash_bytes(b"abc") == gc._hash_bytes(b"abc")
    missing = tmp_path / "nope.bin"
    assert gc._existing_digest(missing) is None
    present = tmp_path / "there.bin"
    present.write_bytes(b"data")
    assert gc._existing_digest(present) == gc._hash_bytes(b"data")


def test_write_bytes_new_then_unchanged(tmp_path: Path) -> None:
    dest = tmp_path / "sub" / "out.bin"
    digest1, wrote1 = gc._write_bytes(dest, b"payload", command="t")
    assert wrote1 is True
    digest2, wrote2 = gc._write_bytes(dest, b"payload", command="t")
    assert wrote2 is False
    assert digest1 == digest2


# --------------------------------------------------------------------------
# path resolution
# --------------------------------------------------------------------------
def test_resolve_path_absolute_and_relative(tmp_path: Path) -> None:
    absolute = tmp_path / "abs"
    assert gc._resolve_path(tmp_path, absolute) == absolute
    rel = gc._resolve_path(tmp_path, "child")
    assert rel == (tmp_path / "child").resolve()


def test_resolve_kubectl_binary_absolute(tmp_path: Path) -> None:
    abs_bin = (tmp_path / "kubectl").resolve()
    assert gc._resolve_kubectl_binary(tmp_path, abs_bin) == abs_bin


def test_resolve_kubectl_binary_with_dir_component(tmp_path: Path) -> None:
    resolved = gc._resolve_kubectl_binary(tmp_path, "bin/kubectl")
    assert resolved == (tmp_path / "bin/kubectl").resolve()


def test_resolve_kubectl_binary_on_path() -> None:
    resolved = gc._resolve_kubectl_binary(Path.cwd(), "python3")
    which = shutil.which("python3")
    assert which is not None
    assert resolved == Path(which)


def test_resolve_kubectl_binary_not_found(tmp_path: Path) -> None:
    target = "definitely-not-a-real-binary-xyz"
    assert gc._resolve_kubectl_binary(tmp_path, target) == Path(target)


def test_resolve_overlay_path_explicit_path() -> None:
    cfg = DeploymentConfig(
        name="d",
        environment=Environment.STAGE,
        strategy="s",
        artifact="a",
        manifests={"path": "overlays/custom"},
    )
    config_path = Path("configs/deploy.yaml")
    resolved = gc._resolve_overlay_path(config_path, cfg)
    assert resolved == gc._resolve_path(config_path.parent, "overlays/custom")


def test_resolve_overlay_path_default_name_for_environment() -> None:
    cfg = DeploymentConfig(
        name="d",
        environment=Environment.PROD,
        strategy="s",
        artifact="a",
    )
    resolved = gc._resolve_overlay_path(Path("cfg/deploy.yaml"), cfg)
    assert resolved.name == "production"


def test_resolve_overlay_path_named() -> None:
    cfg = DeploymentConfig(
        name="d",
        environment=Environment.STAGE,
        strategy="s",
        artifact="a",
        manifests={"name": "staging"},
    )
    resolved = gc._resolve_overlay_path(Path("cfg/deploy.yaml"), cfg)
    assert resolved.name == "staging"


# --------------------------------------------------------------------------
# kubectl command building / execution
# --------------------------------------------------------------------------
def test_build_kubectl_command_includes_options() -> None:
    cfg = _make_deploy_cfg(
        context="ctx",
        namespace="ns",
        extra_args=["--foo"],
    )
    command = gc._build_kubectl_command(Path("kubectl"), cfg, "apply", "-k", ".")
    assert command[:1] == ["kubectl"]
    assert "--context" in command and "ctx" in command
    assert "--namespace" in command and "ns" in command
    assert "--foo" in command
    assert command[-3:] == ["apply", "-k", "."]


def test_run_kubectl_binary_missing(tmp_path: Path) -> None:
    cfg = _make_deploy_cfg()
    with pytest.raises(gc.ComputeError, match="not found"):
        gc._run_kubectl(
            "deploy",
            tmp_path / "no_such_kubectl",
            cfg,
            {},
            "version",
        )


def test_run_kubectl_nonzero_exit(tmp_path: Path) -> None:
    stub = tmp_path / "kubectl"
    stub.write_text("#!/bin/sh\nexit 3\n", encoding="utf-8")
    stub.chmod(0o755)
    cfg = _make_deploy_cfg()
    with pytest.raises(gc.ComputeError, match="exit code 3"):
        gc._run_kubectl("deploy", stub, cfg, {}, "apply")


def test_run_kubectl_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_run(command: list[str], **kwargs: Any) -> None:
        captured["command"] = command

    monkeypatch.setattr(gc.subprocess, "run", _fake_run)
    cfg = _make_deploy_cfg()
    gc._run_kubectl("deploy", Path("kubectl"), cfg, {}, "apply")
    assert captured["command"][0] == "kubectl"


# --------------------------------------------------------------------------
# _load_callable
# --------------------------------------------------------------------------
def test_load_callable_missing_attr_path() -> None:
    with pytest.raises(gc.ConfigError, match="module.*callable"):
        gc._load_callable("os")


def test_load_callable_invalid_attribute() -> None:
    with pytest.raises(gc.ConfigError, match="is invalid"):
        gc._load_callable("os:does_not_exist")


def test_load_callable_not_callable() -> None:
    with pytest.raises(gc.ConfigError, match="does not reference a callable"):
        gc._load_callable("os:sep")


def test_load_callable_valid() -> None:
    fn = gc._load_callable("os.path:join")
    assert callable(fn)


# --------------------------------------------------------------------------
# _load_prices branches
# --------------------------------------------------------------------------
def test_load_prices_missing_data_source() -> None:
    empty: Any = SimpleNamespace()
    with pytest.raises(gc.ConfigError, match="does not define a data source"):
        gc._load_prices(empty)


def test_load_prices_unsupported_kind() -> None:
    cfg: Any = SimpleNamespace(source=SimpleNamespace(kind="json", path="x"))
    with pytest.raises(gc.ConfigError, match="Unsupported data source"):
        gc._load_prices(cfg)


def test_load_prices_missing_file() -> None:
    cfg: Any = SimpleNamespace(
        source=SimpleNamespace(kind="csv", path="/no/such/file.csv")
    )
    with pytest.raises(gc.ArtifactError, match="does not exist"):
        gc._load_prices(cfg)


def test_load_prices_missing_timestamp_column(tmp_path: Path) -> None:
    path = tmp_path / "p.csv"
    pd.DataFrame({"price": [1.0, 2.0]}).to_csv(path, index=False)
    cfg: Any = SimpleNamespace(
        source=SimpleNamespace(
            kind="csv", path=str(path), timestamp_field="timestamp", value_field="price"
        )
    )
    with pytest.raises(gc.ConfigError, match="Timestamp column missing"):
        gc._load_prices(cfg)


def test_load_prices_missing_value_column(tmp_path: Path) -> None:
    path = tmp_path / "p.csv"
    pd.DataFrame({"timestamp": [1, 2]}).to_csv(path, index=False)
    cfg: Any = SimpleNamespace(
        source=SimpleNamespace(
            kind="csv", path=str(path), timestamp_field="timestamp", value_field="price"
        )
    )
    with pytest.raises(gc.ConfigError, match="Value column missing"):
        gc._load_prices(cfg)


def test_load_prices_sorts_unsorted(tmp_path: Path) -> None:
    path = tmp_path / "p.csv"
    pd.DataFrame(
        {"timestamp": [3, 1, 2], "price": [30.0, 10.0, 20.0]}
    ).to_csv(path, index=False)
    cfg: Any = SimpleNamespace(
        source=SimpleNamespace(
            kind="csv", path=str(path), timestamp_field="timestamp", value_field="price"
        )
    )
    frame = gc._load_prices(cfg)
    assert list(frame["timestamp"]) == [1, 2, 3]
    assert isinstance(frame.index, pd.RangeIndex)


def test_load_prices_already_sorted(tmp_path: Path) -> None:
    path = tmp_path / "p.csv"
    pd.DataFrame(
        {"timestamp": [1, 2, 3], "price": [10.0, 20.0, 30.0]}
    ).to_csv(path, index=False)
    cfg: Any = SimpleNamespace(
        source=SimpleNamespace(
            kind="csv", path=str(path), timestamp_field="timestamp", value_field="price"
        )
    )
    frame = gc._load_prices(cfg)
    assert list(frame["price"]) == [10.0, 20.0, 30.0]


def test_load_prices_parquet_missing_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "p.parquet"
    path.write_bytes(b"stub")

    def _raise(*_a: Any, **_k: Any) -> pd.DataFrame:
        raise MissingParquetDependencyError("no parquet")

    monkeypatch.setattr(gc, "read_dataframe", _raise)
    cfg: Any = SimpleNamespace(
        source=SimpleNamespace(
            kind="parquet", path=str(path), timestamp_field="timestamp", value_field="price"
        )
    )
    with pytest.raises(gc.ArtifactError, match="Parquet sources require"):
        gc._load_prices(cfg)


def test_load_prices_reads_parquet(tmp_path: Path) -> None:
    path = tmp_path / "p.parquet"
    pd.DataFrame({"timestamp": [1, 2], "price": [1.0, 2.0]}).to_parquet(path)
    cfg: Any = SimpleNamespace(
        source=SimpleNamespace(
            kind="parquet", path=str(path), timestamp_field="timestamp", value_field="price"
        )
    )
    frame = gc._load_prices(cfg)
    assert list(frame["price"]) == [1.0, 2.0]


# --------------------------------------------------------------------------
# _load_feature_frame branches
# --------------------------------------------------------------------------
def test_load_feature_frame_missing(tmp_path: Path) -> None:
    src = FeatureFrameSourceConfig(path=tmp_path / "missing.csv")
    with pytest.raises(gc.ArtifactError, match="does not exist"):
        gc._load_feature_frame(src)


def test_load_feature_frame_auto_csv(tmp_path: Path) -> None:
    path = tmp_path / "f.csv"
    pd.DataFrame({"a": [1]}).to_csv(path, index=False)
    src = FeatureFrameSourceConfig(path=path, format="auto")
    frame = gc._load_feature_frame(src)
    assert list(frame.columns) == ["a"]


def test_load_feature_frame_auto_parquet(tmp_path: Path) -> None:
    path = tmp_path / "f.parquet"
    pd.DataFrame({"a": [1, 2]}).to_parquet(path)
    src = FeatureFrameSourceConfig(path=path, format="auto")
    frame = gc._load_feature_frame(src)
    assert list(frame["a"]) == [1, 2]


def test_load_feature_frame_parquet_missing_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "f.parquet"
    path.write_bytes(b"stub")

    def _raise(*_a: Any, **_k: Any) -> pd.DataFrame:
        raise MissingParquetDependencyError("no parquet")

    monkeypatch.setattr(gc, "read_dataframe", _raise)
    src = FeatureFrameSourceConfig(path=path, format="parquet")
    with pytest.raises(gc.ArtifactError, match="Parquet sources require"):
        gc._load_feature_frame(src)


# --------------------------------------------------------------------------
# _load_fete_inputs branches
# --------------------------------------------------------------------------
def test_load_fete_inputs_missing_file(tmp_path: Path) -> None:
    with pytest.raises(gc.ArtifactError, match="does not exist"):
        gc._load_fete_inputs(tmp_path / "x.csv", "price", None)


def test_load_fete_inputs_missing_price_column(tmp_path: Path) -> None:
    path = tmp_path / "d.csv"
    pd.DataFrame({"other": [1.0, 2.0, 3.0]}).to_csv(path, index=False)
    with pytest.raises(gc.ConfigError, match="Price column"):
        gc._load_fete_inputs(path, "price", None)


def test_load_fete_inputs_too_few_rows(tmp_path: Path) -> None:
    path = tmp_path / "d.csv"
    pd.DataFrame({"price": [1.0, 2.0]}).to_csv(path, index=False)
    with pytest.raises(gc.ConfigError, match="at least three"):
        gc._load_fete_inputs(path, "price", None)


def test_load_fete_inputs_missing_prob_column(tmp_path: Path) -> None:
    path = tmp_path / "d.csv"
    pd.DataFrame({"price": [1.0, 2.0, 3.0]}).to_csv(path, index=False)
    with pytest.raises(gc.ConfigError, match="Probability column"):
        gc._load_fete_inputs(path, "price", "prob")


def test_load_fete_inputs_with_prob_column(tmp_path: Path) -> None:
    path = tmp_path / "d.csv"
    pd.DataFrame(
        {"price": [1.0, 2.0, 3.0], "prob": [0.1, 0.9, 1.5]}
    ).to_csv(path, index=False)
    prices, probs = gc._load_fete_inputs(path, "price", "prob")
    assert prices.size == 3
    assert probs.max() <= 1.0 and probs.min() >= 0.0


def test_load_fete_inputs_synthetic_prob(tmp_path: Path) -> None:
    path = tmp_path / "d.csv"
    pd.DataFrame({"price": [1.0, 2.0, 3.0, 4.0]}).to_csv(path, index=False)
    prices, probs = gc._load_fete_inputs(path, "price", None)
    assert prices.size == probs.size == 4


# --------------------------------------------------------------------------
# _build_parity_spec / _resolve_strategy
# --------------------------------------------------------------------------
def test_build_parity_spec_default_and_value_columns() -> None:
    spec_none = _spec_cfg(value_columns=None)
    built_none = gc._build_parity_spec(spec_none)
    assert built_none.value_columns is None

    spec_cols = _spec_cfg(value_columns=("value",))
    built_cols = gc._build_parity_spec(spec_cols)
    assert built_cols.value_columns == ("value",)


def _spec_cfg(*, value_columns: tuple[str, ...] | None) -> FeatureParitySpecConfig:
    return FeatureParitySpecConfig(
        feature_view="fv",
        timestamp_granularity="1min",
        numeric_tolerance=0.0,
        value_columns=value_columns,
    )


def test_resolve_strategy_wraps_callable() -> None:
    cfg = StrategyConfig(
        entrypoint="core.strategies.signals:moving_average_signal",
        parameters={"window": 3},
    )
    strategy = gc._resolve_strategy(cfg)
    prices = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    signals = strategy(prices)
    assert signals.shape == prices.shape


# --------------------------------------------------------------------------
# _write_frame branches
# --------------------------------------------------------------------------
def test_write_frame_csv(tmp_path: Path) -> None:
    frame = pd.DataFrame({"a": [1, 2]})
    digest = gc._write_frame(frame, tmp_path / "o.csv", command="t")
    assert digest


def test_write_frame_empty_suffix_treated_as_csv(tmp_path: Path) -> None:
    frame = pd.DataFrame({"a": [1]})
    digest = gc._write_frame(frame, tmp_path / "noext", command="t")
    assert digest


def test_write_frame_parquet(tmp_path: Path) -> None:
    frame = pd.DataFrame({"a": [1, 2]})
    digest = gc._write_frame(frame, tmp_path / "o.parquet", command="t")
    assert digest


def test_write_frame_parquet_missing_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(*_a: Any, **_k: Any) -> bytes:
        raise MissingParquetDependencyError("no parquet")

    monkeypatch.setattr(gc, "dataframe_to_parquet_bytes", _raise)
    frame = pd.DataFrame({"a": [1]})
    with pytest.raises(gc.ConfigError, match="Writing parquet"):
        gc._write_frame(frame, tmp_path / "o.parquet", command="t")


def test_write_frame_unsupported_suffix(tmp_path: Path) -> None:
    frame = pd.DataFrame({"a": [1]})
    with pytest.raises(gc.ConfigError, match="Unsupported destination"):
        gc._write_frame(frame, tmp_path / "o.xml", command="t")


# --------------------------------------------------------------------------
# returns / feature dataset loaders
# --------------------------------------------------------------------------
def test_load_returns_frame_with_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "r.csv"
    pd.DataFrame(
        {"date": ["2024-01-02", "2024-01-01"], "AAA": [0.1, -0.1]}
    ).to_csv(path, index=False)
    frame = gc._load_returns_frame(path)
    assert isinstance(frame.index, pd.DatetimeIndex)
    assert frame.index.is_monotonic_increasing


def test_load_returns_frame_without_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "r.csv"
    pd.DataFrame({"AAA": [0.1, -0.1]}).to_csv(path, index=False)
    frame = gc._load_returns_frame(path)
    assert not isinstance(frame.index, pd.DatetimeIndex)


def test_load_feature_dataset_missing_label(tmp_path: Path) -> None:
    path = tmp_path / "f.csv"
    pd.DataFrame({"dr": [0.1]}).to_csv(path, index=False)
    with pytest.raises(gc.ComputeError, match="'y' label"):
        gc._load_feature_dataset(path)


def test_load_feature_dataset_missing_feature_columns(tmp_path: Path) -> None:
    path = tmp_path / "f.csv"
    pd.DataFrame({"dr": [0.1], "y": [1]}).to_csv(path, index=False)
    with pytest.raises(gc.ComputeError, match="dr, ricci_mean"):
        gc._load_feature_dataset(path)


def test_load_feature_dataset_valid(tmp_path: Path) -> None:
    path = tmp_path / "f.csv"
    pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02"],
            "dr": [0.1, 0.2],
            "ricci_mean": [0.0, 0.1],
            "topo_intensity": [0.3, 0.4],
            "causal_strength": [0.5, 0.6],
            "y": [0, 1],
        }
    ).to_csv(path, index=False)
    dataset = gc._load_feature_dataset(path)
    assert dataset.labels.tolist() == [0, 1]


# --------------------------------------------------------------------------
# step_logger error path
# --------------------------------------------------------------------------
def test_step_logger_reraises_on_error() -> None:
    with pytest.raises(ValueError, match="boom"):
        with gc.step_logger("cmd", "step"):
            raise ValueError("boom")


# --------------------------------------------------------------------------
# _run_backtest signal length guard
# --------------------------------------------------------------------------
def test_run_backtest_signal_length_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "p.csv"
    pd.DataFrame(
        {"timestamp": [1, 2, 3], "price": [10.0, 11.0, 12.0]}
    ).to_csv(path, index=False)
    from core.config.cli_models import BacktestConfig

    cfg = BacktestConfig(
        name="bt",
        data={"kind": "csv", "path": str(path)},
        strategy={"entrypoint": "core.strategies.signals:moving_average_signal"},
    )

    def _short(_prices: np.ndarray) -> np.ndarray:
        return np.array([0.0])

    monkeypatch.setattr(gc, "_resolve_strategy", lambda _cfg: _short)
    with pytest.raises(gc.ComputeError, match="signal for each price"):
        gc._run_backtest(cfg)
