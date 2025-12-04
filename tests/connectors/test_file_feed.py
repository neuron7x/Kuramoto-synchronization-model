# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for FileFeedIngestor file-based connector.

Tests JSONL and CSV file parsing with various scenarios.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mycelium_fractal_net.connectors.file_feed import FileFeedIngestor


class TestFileFeedIngestor:
    """Tests for FileFeedIngestor connector."""

    def test_initialization_jsonl(self) -> None:
        """Test initialization with JSONL format."""
        ingestor = FileFeedIngestor(
            path="/data/feed.jsonl",
            format="jsonl",
        )
        assert ingestor.format == "jsonl"
        assert ingestor.path == Path("/data/feed.jsonl")

    def test_initialization_csv(self) -> None:
        """Test initialization with CSV format."""
        ingestor = FileFeedIngestor(
            path="/data/feed.csv",
            format="csv",
        )
        assert ingestor.format == "csv"

    def test_invalid_format_rejected(self) -> None:
        """Test that invalid format raises error."""
        with pytest.raises(ValueError, match="Unsupported format"):
            FileFeedIngestor(path="/data/feed.xml", format="xml")

    def test_source_name_derived_from_path(self) -> None:
        """Test automatic source name derivation."""
        ingestor = FileFeedIngestor(path="/data/market_data.jsonl")
        assert ingestor.source_name == "file_market_data"

    def test_custom_source_name(self) -> None:
        """Test custom source name override."""
        ingestor = FileFeedIngestor(
            path="/data/feed.jsonl",
            source_name="custom_feed",
        )
        assert ingestor.source_name == "custom_feed"

    @pytest.mark.asyncio
    async def test_connect_validates_file_exists(self, tmp_path: Path) -> None:
        """Test that connect() validates file existence."""
        ingestor = FileFeedIngestor(path=tmp_path / "nonexistent.jsonl")

        with pytest.raises(FileNotFoundError):
            await ingestor.connect()

    @pytest.mark.asyncio
    async def test_connect_validates_is_file(self, tmp_path: Path) -> None:
        """Test that connect() validates path is a file."""
        ingestor = FileFeedIngestor(path=tmp_path)  # directory, not file

        with pytest.raises(ValueError, match="not a file"):
            await ingestor.connect()

    @pytest.mark.asyncio
    async def test_read_jsonl_file(self, tmp_path: Path) -> None:
        """Test reading JSONL file."""
        data_file = tmp_path / "data.jsonl"
        data_file.write_text(
            json.dumps({"id": 1, "value": "first"})
            + "\n"
            + json.dumps({"id": 2, "value": "second"})
            + "\n"
            + json.dumps({"id": 3, "value": "third"})
            + "\n"
        )

        ingestor = FileFeedIngestor(path=data_file, format="jsonl")
        await ingestor.connect()

        events = []
        async for event in ingestor.fetch():
            events.append(event)

        assert len(events) == 3
        assert events[0].payload["id"] == 1
        assert events[1].payload["value"] == "second"
        assert events[2].payload["id"] == 3

        await ingestor.close()

    @pytest.mark.asyncio
    async def test_read_jsonl_skips_empty_lines(self, tmp_path: Path) -> None:
        """Test that empty lines are skipped."""
        data_file = tmp_path / "data.jsonl"
        data_file.write_text(
            json.dumps({"id": 1})
            + "\n"
            + "\n"  # empty line
            + "   \n"  # whitespace only
            + json.dumps({"id": 2})
            + "\n"
        )

        ingestor = FileFeedIngestor(path=data_file, format="jsonl")
        await ingestor.connect()

        events = []
        async for event in ingestor.fetch():
            events.append(event)

        assert len(events) == 2

        await ingestor.close()

    @pytest.mark.asyncio
    async def test_read_jsonl_handles_invalid_json(self, tmp_path: Path) -> None:
        """Test that invalid JSON lines are logged and skipped."""
        data_file = tmp_path / "data.jsonl"
        data_file.write_text(
            json.dumps({"id": 1})
            + "\n"
            + "not valid json\n"
            + json.dumps({"id": 2})
            + "\n"
        )

        ingestor = FileFeedIngestor(path=data_file, format="jsonl")
        await ingestor.connect()

        events = []
        async for event in ingestor.fetch():
            events.append(event)

        assert len(events) == 2
        assert ingestor._error_count == 1

        await ingestor.close()

    @pytest.mark.asyncio
    async def test_read_csv_file(self, tmp_path: Path) -> None:
        """Test reading CSV file."""
        data_file = tmp_path / "data.csv"
        data_file.write_text("id,name,value\n" "1,first,100\n" "2,second,200\n")

        ingestor = FileFeedIngestor(path=data_file, format="csv")
        await ingestor.connect()

        events = []
        async for event in ingestor.fetch():
            events.append(event)

        assert len(events) == 2
        assert events[0].payload["id"] == 1
        assert events[0].payload["name"] == "first"
        assert events[1].payload["value"] == 200

        await ingestor.close()

    @pytest.mark.asyncio
    async def test_csv_field_mapping(self, tmp_path: Path) -> None:
        """Test CSV field mapping."""
        data_file = tmp_path / "data.csv"
        data_file.write_text("col_a,col_b,col_c\n" "1,hello,3.14\n")

        ingestor = FileFeedIngestor(
            path=data_file,
            format="csv",
            field_mapping={
                "col_a": "id",
                "col_b": "message",
            },
        )
        await ingestor.connect()

        events = []
        async for event in ingestor.fetch():
            events.append(event)

        assert events[0].payload["id"] == 1
        assert events[0].payload["message"] == "hello"
        # Unmapped columns preserved
        assert events[0].payload["col_c"] == 3.14

        await ingestor.close()

    @pytest.mark.asyncio
    async def test_csv_type_coercion(self, tmp_path: Path) -> None:
        """Test CSV value type coercion."""
        data_file = tmp_path / "data.csv"
        data_file.write_text(
            "int_val,float_val,bool_val,str_val,empty_val\n"
            "42,3.14,true,hello,\n"
            "100,2.5,false,world,\n"
        )

        ingestor = FileFeedIngestor(path=data_file, format="csv")
        await ingestor.connect()

        events = []
        async for event in ingestor.fetch():
            events.append(event)

        # Check type coercion
        assert events[0].payload["int_val"] == 42
        assert events[0].payload["float_val"] == 3.14
        assert events[0].payload["bool_val"] is True
        assert events[0].payload["str_val"] == "hello"
        assert events[0].payload["empty_val"] is None

        assert events[1].payload["bool_val"] is False

        await ingestor.close()

    @pytest.mark.asyncio
    async def test_timestamp_extraction_jsonl(self, tmp_path: Path) -> None:
        """Test timestamp extraction from JSONL records."""
        data_file = tmp_path / "data.jsonl"
        data_file.write_text(
            json.dumps({"id": 1, "timestamp": 1704067200.0})
            + "\n"
            + json.dumps({"id": 2, "time": "2024-01-02T12:00:00Z"})
            + "\n"
        )

        ingestor = FileFeedIngestor(path=data_file, format="jsonl")
        await ingestor.connect()

        events = []
        async for event in ingestor.fetch():
            events.append(event)

        assert events[0].timestamp.year == 2024
        assert events[0].timestamp.month == 1
        assert events[0].timestamp.day == 1

        assert events[1].timestamp.day == 2
        assert events[1].timestamp.hour == 12

        await ingestor.close()

    @pytest.mark.asyncio
    async def test_custom_timestamp_field(self, tmp_path: Path) -> None:
        """Test custom timestamp field configuration."""
        data_file = tmp_path / "data.jsonl"
        data_file.write_text(json.dumps({"id": 1, "event_time": 1704067200.0}) + "\n")

        ingestor = FileFeedIngestor(
            path=data_file,
            format="jsonl",
            timestamp_field="event_time",
        )
        await ingestor.connect()

        events = []
        async for event in ingestor.fetch():
            events.append(event)

        assert events[0].timestamp.year == 2024

        await ingestor.close()

    @pytest.mark.asyncio
    async def test_empty_file(self, tmp_path: Path) -> None:
        """Test reading empty file."""
        data_file = tmp_path / "empty.jsonl"
        data_file.write_text("")

        ingestor = FileFeedIngestor(path=data_file, format="jsonl")
        await ingestor.connect()

        events = []
        async for event in ingestor.fetch():
            events.append(event)

        assert len(events) == 0
        assert ingestor._record_count == 0

        await ingestor.close()

    @pytest.mark.asyncio
    async def test_meta_contains_file_info(self, tmp_path: Path) -> None:
        """Test that meta contains file information."""
        data_file = tmp_path / "data.jsonl"
        data_file.write_text(json.dumps({"id": 1}) + "\n")

        ingestor = FileFeedIngestor(path=data_file, format="jsonl")
        await ingestor.connect()

        events = []
        async for event in ingestor.fetch():
            events.append(event)

        assert "line" in events[0].meta
        assert "file" in events[0].meta
        assert events[0].meta["line"] == 1

        await ingestor.close()

    @pytest.mark.asyncio
    async def test_stats_property(self, tmp_path: Path) -> None:
        """Test stats property returns correct counts."""
        data_file = tmp_path / "data.jsonl"
        data_file.write_text(
            json.dumps({"id": 1}) + "\n" + "invalid\n" + json.dumps({"id": 2}) + "\n"
        )

        ingestor = FileFeedIngestor(path=data_file, format="jsonl")
        await ingestor.connect()

        async for _ in ingestor.fetch():
            pass

        stats = ingestor.stats
        assert stats["record_count"] == 2
        assert stats["error_count"] == 1

        await ingestor.close()

    @pytest.mark.asyncio
    async def test_context_manager(self, tmp_path: Path) -> None:
        """Test async context manager usage."""
        data_file = tmp_path / "data.jsonl"
        data_file.write_text(json.dumps({"id": 1}) + "\n")

        async with FileFeedIngestor(path=data_file, format="jsonl") as ingestor:
            events = []
            async for event in ingestor.fetch():
                events.append(event)
            assert len(events) == 1
