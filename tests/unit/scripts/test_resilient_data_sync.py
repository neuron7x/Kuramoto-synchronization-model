"""Regression tests for the resilient data synchronization utility."""

from argparse import ArgumentTypeError
from pathlib import Path

from scripts import resilient_data_sync as sync


def test_parse_args_supports_basic_flags() -> None:
    """Ensure the CLI parser recognises core options."""

    args = sync.parse_args(["https://example.com/data.csv", "--json", "--retries", "3"])

    assert args.sources == ["https://example.com/data.csv"]
    assert args.json is True
    assert args.retries == 3


def test_parse_checksum_pairs_round_trips() -> None:
    """Checksum helper should map SOURCE=HASH pairs into a dictionary."""

    mapping = sync._parse_checksum_pairs(["foo=abc", "bar=def"])

    assert mapping == {"foo": "abc", "bar": "def"}


def test_parse_checksum_pairs_rejects_invalid_format() -> None:
    """Invalid checksum arguments should raise a parser error."""

    try:
        sync._parse_checksum_pairs(["foo"])
    except ArgumentTypeError:
        return

    raise AssertionError("Expected ArgumentTypeError for malformed checksum pair")


def test_resolve_sources_preserves_directory_structure(tmp_path: Path) -> None:
    """Directory inputs should yield unique relative destination paths."""

    root = tmp_path / "dataset"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir()
    file_one = root / "a" / "prices.csv"
    file_two = root / "b" / "prices.csv"
    file_one.write_text("ts,price\n0,1\n")
    file_two.write_text("ts,price\n1,2\n")

    resolved = sync._resolve_sources([str(root)], "*.csv")
    assert len(resolved) == 2

    destinations = sorted(spec.destination_key for spec in resolved)
    assert destinations == ["a/prices.csv", "b/prices.csv"]

    for spec in resolved:
        assert str(Path(spec.destination_key)).startswith(("a", "b"))
        # Checksums may be referenced via absolute or relative path.
        assert str(Path(spec.source)) in spec.checksum_keys
        assert Path(spec.destination_key).as_posix() in spec.checksum_keys


def test_resolve_sources_supports_remote_urls() -> None:
    """Remote URLs should retain a friendly destination name."""

    resolved = sync._resolve_sources(["https://example.com/data.csv"], pattern="*.csv")

    assert len(resolved) == 1
    spec = resolved[0]
    assert spec.destination_key == "data.csv"
    assert spec.checksum_keys == ("https://example.com/data.csv",)
