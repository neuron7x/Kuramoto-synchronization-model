"""Tests for MLSDM CLI functionality."""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from tradepulse.sdk.mlsdm.__main__ import (
    JSONFormatter,
    build_arg_parser,
    configure_logging,
)


class TestJSONFormatter:
    """Tests for JSONFormatter class."""

    def test_format_simple_message(self) -> None:
        """Test formatting a simple log message."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Test message"
        assert parsed["module"] == "test"
        assert parsed["logger"] == "test"
        assert "timestamp" in parsed

    def test_format_with_exception(self) -> None:
        """Test formatting a log message with exception info."""
        formatter = JSONFormatter()

        try:
            raise ValueError("Test exception")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["level"] == "ERROR"
        assert parsed["message"] == "Error occurred"
        assert "exc_info" in parsed
        assert "ValueError: Test exception" in parsed["exc_info"]

    def test_format_ensure_ascii_false(self) -> None:
        """Test that non-ASCII characters are preserved."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test: äöü 中文",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        assert "äöü" in output
        assert "中文" in output


class TestConfigureLogging:
    """Tests for configure_logging function."""

    def test_configure_logging_default(self) -> None:
        """Test logging configuration with default level."""
        # Clear existing handlers
        root = logging.getLogger()
        root.handlers.clear()

        logger = configure_logging()

        assert isinstance(logger, logging.Logger)
        assert root.level == logging.INFO
        assert len(root.handlers) >= 1
        assert isinstance(root.handlers[0].formatter, JSONFormatter)

    def test_configure_logging_custom_level(self) -> None:
        """Test logging configuration with custom level."""
        # Clear existing handlers
        root = logging.getLogger()
        root.handlers.clear()

        configure_logging(level=logging.DEBUG)

        assert root.level == logging.DEBUG

    def test_configure_logging_idempotent(self) -> None:
        """Test that multiple calls don't add duplicate handlers."""
        # Clear existing handlers
        root = logging.getLogger()
        root.handlers.clear()

        configure_logging()
        initial_handlers = len(root.handlers)

        configure_logging()
        configure_logging()

        # Should not add more handlers
        assert len(root.handlers) == initial_handlers


class TestBuildArgParser:
    """Tests for build_arg_parser function."""

    def test_parser_default_values(self) -> None:
        """Test parser with default values."""
        parser = build_arg_parser()
        args = parser.parse_args([])

        assert args.config == "config/default_config.yaml"
        assert args.steps == 100
        assert args.api is False
        assert args.host == "0.0.0.0"
        assert args.port == 8000

    def test_parser_custom_config(self) -> None:
        """Test parser with custom config path."""
        parser = build_arg_parser()
        args = parser.parse_args(["--config", "custom/config.yaml"])

        assert args.config == "custom/config.yaml"

    def test_parser_custom_steps(self) -> None:
        """Test parser with custom steps."""
        parser = build_arg_parser()
        args = parser.parse_args(["--steps", "500"])

        assert args.steps == 500

    def test_parser_api_flag(self) -> None:
        """Test parser with API flag."""
        parser = build_arg_parser()
        args = parser.parse_args(["--api"])

        assert args.api is True

    def test_parser_custom_host_port(self) -> None:
        """Test parser with custom host and port."""
        parser = build_arg_parser()
        args = parser.parse_args(["--host", "127.0.0.1", "--port", "9000"])

        assert args.host == "127.0.0.1"
        assert args.port == 9000

    def test_parser_all_args(self) -> None:
        """Test parser with all arguments."""
        parser = build_arg_parser()
        args = parser.parse_args([
            "--config", "test.yaml",
            "--steps", "200",
            "--api",
            "--host", "localhost",
            "--port", "3000",
        ])

        assert args.config == "test.yaml"
        assert args.steps == 200
        assert args.api is True
        assert args.host == "localhost"
        assert args.port == 3000


class TestMainFunction:
    """Tests for main function."""

    @patch("tradepulse.sdk.mlsdm.__main__.ConfigLoader.load_config")
    @patch("tradepulse.sdk.mlsdm.__main__.MemoryManager")
    def test_main_simulation_success(
        self, mock_manager_class: MagicMock, mock_load_config: MagicMock
    ) -> None:
        """Test main function with successful simulation."""
        from tradepulse.sdk.mlsdm.__main__ import main

        mock_load_config.return_value = {"fhmc": {}}
        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager

        with patch("sys.argv", ["mlsdm", "--steps", "10"]):
            main()

        mock_load_config.assert_called_once()
        mock_manager.run_simulation.assert_called_once_with(10)

    @patch("tradepulse.sdk.mlsdm.__main__.ConfigLoader.load_config")
    def test_main_config_load_failure(self, mock_load_config: MagicMock) -> None:
        """Test main function with config load failure."""
        from tradepulse.sdk.mlsdm.__main__ import main

        mock_load_config.side_effect = FileNotFoundError("Config not found")

        with patch("sys.argv", ["mlsdm"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    @patch("tradepulse.sdk.mlsdm.__main__.ConfigLoader.load_config")
    @patch("tradepulse.sdk.mlsdm.__main__.MemoryManager")
    def test_main_simulation_failure(
        self, mock_manager_class: MagicMock, mock_load_config: MagicMock
    ) -> None:
        """Test main function with simulation failure."""
        from tradepulse.sdk.mlsdm.__main__ import main

        mock_load_config.return_value = {"fhmc": {}}
        mock_manager = MagicMock()
        mock_manager.run_simulation.side_effect = RuntimeError("Simulation failed")
        mock_manager_class.return_value = mock_manager

        with patch("sys.argv", ["mlsdm"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_main_api_mode(self) -> None:
        """Test main function in API mode."""
        import sys

        from tradepulse.sdk.mlsdm.__main__ import main

        # Create a mock uvicorn module and inject it
        mock_uvicorn = MagicMock()
        sys.modules["uvicorn"] = mock_uvicorn

        # Also need to mock the app import
        mock_app = MagicMock()

        try:
            with patch("sys.argv", ["mlsdm", "--api", "--host", "localhost", "--port", "9000"]):
                with patch("tradepulse.sdk.mlsdm.api.app.app", mock_app):
                    main()

            # Verify uvicorn.run was called with correct parameters
            mock_uvicorn.run.assert_called_once()
            call_args = mock_uvicorn.run.call_args
            # Check that the app was passed
            assert call_args.args[0] is mock_app or "app" in str(call_args.args[0])
            assert call_args.kwargs["host"] == "localhost"
            assert call_args.kwargs["port"] == 9000
        finally:
            # Clean up
            if "uvicorn" in sys.modules:
                del sys.modules["uvicorn"]
