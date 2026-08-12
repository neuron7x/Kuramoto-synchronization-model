# mypy: disable-error-code="no-untyped-def,type-arg"
"""QuestDB writer tests (unit-level, no running QuestDB required)."""

from __future__ import annotations

import importlib.util
import time
from unittest.mock import MagicMock, patch

import pytest

if importlib.util.find_spec("questdb") is None:
    pytest.skip("questdb not installed", allow_module_level=True)

from coherence_bridge.questdb_writer import QuestDBSignalWriter


def _make_signal(**overrides) -> dict:
    base = {
        "timestamp_ns": time.time_ns(),
        "instrument": "EURUSD",
        "gamma": 1.0,
        "order_parameter_R": 0.5,
        "ricci_curvature": -0.1,
        "lyapunov_max": 0.001,
        "regime": "METASTABLE",
        "regime_confidence": 0.8,
        "regime_duration_s": 10.0,
        "signal_strength": 0.1,
        "risk_scalar": 0.9,
        "sequence_number": 0,
    }
    base.update(overrides)
    return base


@patch("coherence_bridge.questdb_writer.Sender")
def test_write_signal_calls_sender(mock_sender_cls):
    mock_sender = MagicMock()
    mock_sender_cls.from_conf.return_value.__enter__ = MagicMock(return_value=mock_sender)
    mock_sender_cls.from_conf.return_value.__exit__ = MagicMock(return_value=False)

    writer = QuestDBSignalWriter(host="localhost", port=9000)
    signal = _make_signal()
    writer.write_signal(signal)

    mock_sender.row.assert_called_once()
    mock_sender.flush.assert_called_once()

    call_args = mock_sender.row.call_args
    assert call_args[0][0] == "coherence_signals"
    assert call_args[1]["symbols"]["instrument"] == "EURUSD"
    assert call_args[1]["symbols"]["regime"] == "METASTABLE"
    assert call_args[1]["columns"]["gamma"] == 1.0


@patch("coherence_bridge.questdb_writer.Sender")
def test_write_batch(mock_sender_cls):
    mock_sender = MagicMock()
    mock_sender_cls.from_conf.return_value.__enter__ = MagicMock(return_value=mock_sender)
    mock_sender_cls.from_conf.return_value.__exit__ = MagicMock(return_value=False)

    writer = QuestDBSignalWriter()
    signals = [_make_signal(instrument=f"PAIR{i}") for i in range(10)]
    writer.write_batch(signals)

    assert mock_sender.row.call_count == 10
    mock_sender.flush.assert_called_once()


def test_default_config() -> None:
    writer = QuestDBSignalWriter()
    assert writer.host == "localhost"
    assert writer.port == 9000
    assert "http::addr=localhost:9000;" in writer._conf


def test_custom_config() -> None:
    writer = QuestDBSignalWriter(host="questdb.prod", port=9001)
    assert writer.host == "questdb.prod"
    assert writer.port == 9001


@patch("coherence_bridge.questdb_writer.Sender")
def test_write_dataframe(mock_sender_cls):
    """DataFrame path uses sender.dataframe() for ~400k rows/sec throughput."""
    import pandas as pd

    mock_sender = MagicMock()
    mock_sender_cls.from_conf.return_value.__enter__ = MagicMock(return_value=mock_sender)
    mock_sender_cls.from_conf.return_value.__exit__ = MagicMock(return_value=False)

    writer = QuestDBSignalWriter()
    df = pd.DataFrame([_make_signal(instrument=f"PAIR{i}") for i in range(5)])
    df["timestamp"] = pd.to_datetime(df["timestamp_ns"], unit="ns")
    writer.write_dataframe(df)

    mock_sender.dataframe.assert_called_once()
    call_args = mock_sender.dataframe.call_args
    assert call_args[1]["table_name"] == "coherence_signals"
    assert call_args[1]["at"] == "timestamp"
    mock_sender.flush.assert_called_once()


def test_write_dataframe_rejects_non_dataframe() -> None:
    writer = QuestDBSignalWriter()
    try:
        writer.write_dataframe([{"not": "a dataframe"}])
        assert False, "Should have raised TypeError"
    except TypeError as exc:
        assert "DataFrame" in str(exc)
