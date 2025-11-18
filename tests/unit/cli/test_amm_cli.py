import argparse
from contextlib import contextmanager
from pathlib import Path

import pytest

from cli import amm_cli


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    path = tmp_path / "sample.csv"
    path.write_text("x,R,kappa,H\n1,2,3,4\n", encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "value, expected",
    [
        ("1024", 1024),
        ("65535", 65535),
        ("9095", 9095),
    ],
)
def test_valid_port_accepts_valid_values(value: str, expected: int) -> None:
    assert amm_cli._valid_port(value) == expected


@pytest.mark.parametrize(
    "value",
    ["1023", "65536", "-1", "not-a-port"],
)
def test_valid_port_rejects_invalid_values(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        amm_cli._valid_port(value)


@pytest.mark.parametrize(
    "value, expected",
    [
        ("btcusdt", "BTCUSDT"),
        ("ETH123", "ETH123"),
        ("AdaUSDT", "ADAUSDT"),
    ],
)
def test_valid_symbol_accepts_valid_values(value: str, expected: str) -> None:
    assert amm_cli._valid_symbol(value) == expected


@pytest.mark.parametrize(
    "value",
    ["", "ab", "abc!", "SYMBOL-WITH-HYPHEN", "THISISWAYTOOLONGSYMBOL"],
)
def test_valid_symbol_rejects_invalid_values(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        amm_cli._valid_symbol(value)


@pytest.mark.parametrize(
    "value",
    ["1m", "4h", "15s", "7d", "2w"],
)
def test_valid_timeframe_accepts_valid_values(value: str) -> None:
    assert amm_cli._valid_timeframe(value) == value


@pytest.mark.parametrize("value", ["", "15", "hm", "1x"])
def test_valid_timeframe_rejects_invalid_values(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        amm_cli._valid_timeframe(value)


def test_existing_csv_accepts_files(sample_csv: Path) -> None:
    resolved = amm_cli._existing_csv(str(sample_csv))
    assert resolved == sample_csv.resolve()


def test_existing_csv_rejects_missing_files(tmp_path: Path) -> None:
    missing = tmp_path / "missing.csv"
    with pytest.raises(argparse.ArgumentTypeError):
        amm_cli._existing_csv(str(missing))


@pytest.mark.anyio
async def test_stream_csv_yields_valid_rows(sample_csv: Path) -> None:
    rows = [row async for row in amm_cli.stream_csv(sample_csv)]
    assert rows == [(1.0, 2.0, 3.0, 4.0)]


@pytest.mark.anyio
async def test_stream_csv_rejects_missing_columns(tmp_path: Path) -> None:
    path = tmp_path / "invalid.csv"
    path.write_text("x,kappa\n1,2\n", encoding="utf-8")
    with pytest.raises(amm_cli.CSVValidationError):
        [row async for row in amm_cli.stream_csv(path)]


@pytest.mark.anyio
async def test_stream_csv_rejects_invalid_numbers(tmp_path: Path) -> None:
    path = tmp_path / "invalid_numbers.csv"
    path.write_text("x,R,kappa,H\n1,not-a-number,3,\n", encoding="utf-8")
    with pytest.raises(amm_cli.CSVValidationError):
        [row async for row in amm_cli.stream_csv(path)]


@pytest.mark.anyio
async def test_run_publishes_metrics(monkeypatch: pytest.MonkeyPatch, sample_csv: Path) -> None:
    ports: list[int] = []
    monkeypatch.setattr(amm_cli, "start_http_server", lambda port: ports.append(port))

    published: list[tuple[str, str, dict[str, float | None], dict[str, float | None]]] = []

    def fake_publish(symbol: str, tf: str, out, **kwargs):
        published.append((symbol, tf, out, kwargs))

    monkeypatch.setattr(amm_cli, "publish_metrics", fake_publish)

    @contextmanager
    def fake_timed_update(symbol: str, tf: str):
        yield

    monkeypatch.setattr(amm_cli, "timed_update", fake_timed_update)

    class DummyAMM:
        def __init__(self, config):
            self.config = config
            self.gain = 1.5
            self.threshold = 0.7
            self.calls: list[tuple[float, float, float, float | None]] = []

        async def aupdate(self, x: float, R: float, kappa: float, H: float | None):
            row = (x, R, kappa, H)
            self.calls.append(row)
            return {"x": x, "R": R, "kappa": kappa, "H": H}

    amm_instances: list[DummyAMM] = []

    def fake_adaptive_market_mind(config):
        instance = DummyAMM(config)
        amm_instances.append(instance)
        return instance

    monkeypatch.setattr(amm_cli, "AdaptiveMarketMind", fake_adaptive_market_mind)

    await amm_cli.run(sample_csv, "ETHUSDT", "5m", 8080)

    assert ports == [8080]
    assert len(amm_instances) == 1
    assert amm_instances[0].calls == [(1.0, 2.0, 3.0, 4.0)]

    assert published == [
        (
            "ETHUSDT",
            "5m",
            {"x": 1.0, "R": 2.0, "kappa": 3.0, "H": 4.0},
            {"k": 1.5, "theta": 0.7, "q_hi": None},
        )
    ]
