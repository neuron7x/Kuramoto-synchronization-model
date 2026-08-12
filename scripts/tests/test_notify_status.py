# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for notify_status.py script."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
import argparse

import pytest

from scripts import notify_status


def test_parse_key_value_valid() -> None:
    """Test _parse_key_value with valid input."""
    key, value = notify_status._parse_key_value("KEY=value")
    assert key == "KEY"
    assert value == "value"


def test_parse_key_value_with_equals_in_value() -> None:
    """Test _parse_key_value handles equals in value."""
    key, value = notify_status._parse_key_value("URL=https://example.com?a=b")
    assert key == "URL"
    assert value == "https://example.com?a=b"


def test_parse_key_value_with_spaces() -> None:
    """Test _parse_key_value strips spaces."""
    key, value = notify_status._parse_key_value(" KEY = value ")
    assert key == "KEY"
    assert value == "value"


def test_parse_key_value_invalid_format() -> None:
    """Test _parse_key_value raises for invalid format."""
    with pytest.raises(argparse.ArgumentTypeError) as exc_info:
        notify_status._parse_key_value("invalid-no-equals")

    assert "Expected KEY=VALUE" in str(exc_info.value)


def test_parse_key_value_empty_key() -> None:
    """Test _parse_key_value raises for empty key."""
    with pytest.raises(argparse.ArgumentTypeError) as exc_info:
        notify_status._parse_key_value("=value")

    assert "Key cannot be empty" in str(exc_info.value)


def test_build_parser_required_args() -> None:
    """Test _build_parser requires stage, status, workflow, run-url."""
    parser = notify_status._build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_build_parser_valid_args() -> None:
    """Test _build_parser with valid arguments."""
    parser = notify_status._build_parser()
    args = parser.parse_args(
        [
            "--stage",
            "build",
            "--status",
            "success",
            "--workflow",
            "CI",
            "--run-url",
            "https://github.com/test/run/123",
        ]
    )

    assert args.stage == "build"
    assert args.status == "success"
    assert args.workflow == "CI"
    assert args.run_url == "https://github.com/test/run/123"


def test_build_parser_optional_args() -> None:
    """Test _build_parser with optional arguments."""
    parser = notify_status._build_parser()
    args = parser.parse_args(
        [
            "--stage",
            "deploy",
            "--status",
            "failure",
            "--workflow",
            "Deploy",
            "--run-url",
            "https://example.com/run",
            "--job",
            "deploy-prod",
            "--branch",
            "main",
            "--commit",
            "abc123def456",
            "--actor",
            "developer",
            "--environment",
            "production",
        ]
    )

    assert args.job == "deploy-prod"
    assert args.branch == "main"
    assert args.commit == "abc123def456"
    assert args.actor == "developer"
    assert args.environment == "production"


def test_collect_metadata_empty() -> None:
    """Test _collect_metadata with empty fields."""
    result = notify_status._collect_metadata([])
    assert result == {}


def test_collect_metadata_with_fields() -> None:
    """Test _collect_metadata with fields."""
    fields = ["key1=value1", "key2=value2"]
    result = notify_status._collect_metadata(fields)

    assert result == {"key1": "value1", "key2": "value2"}


def test_short_sha_none() -> None:
    """Test _short_sha with None input."""
    assert notify_status._short_sha(None) is None


def test_short_sha_empty() -> None:
    """Test _short_sha with empty string."""
    assert notify_status._short_sha("") is None


def test_short_sha_short_input() -> None:
    """Test _short_sha with short input."""
    assert notify_status._short_sha("abc123") == "abc123"


def test_short_sha_long_input() -> None:
    """Test _short_sha truncates long SHA."""
    result = notify_status._short_sha("abc123def456789012345678901234567890")
    assert result == "abc123d"
    assert len(result) == 7


def test_short_sha_strips_whitespace() -> None:
    """Test _short_sha strips whitespace."""
    result = notify_status._short_sha("  abc123def456  ")
    assert result == "abc123d"


def test_derive_subject() -> None:
    """Test _derive_subject generates correct subject."""
    result = notify_status._derive_subject("build", "success")
    assert "Build" in result
    assert "Success" in result


def test_derive_subject_deploy_failure() -> None:
    """Test _derive_subject for deploy failure."""
    result = notify_status._derive_subject("deploy", "failure")
    assert "Deployment" in result
    assert "Failure" in result


def test_compose_message_basic() -> None:
    """Test _compose_message generates message."""
    args = notify_status.NotificationArguments(
        stage="build",
        status="success",
        workflow="CI",
        job=None,
        run_url="https://example.com/run",
        branch=None,
        commit=None,
        actor=None,
        environment=None,
        metadata={},
        slack_webhook=None,
        slack_channel=None,
        slack_username=None,
        teams_webhook=None,
        teams_theme_color=None,
        timeout=5.0,
        dry_run=False,
    )

    message = notify_status._compose_message(args)

    assert "Build" in message
    assert "completed successfully" in message
    assert "CI" in message


def test_compose_message_with_details() -> None:
    """Test _compose_message with all details."""
    args = notify_status.NotificationArguments(
        stage="deploy",
        status="failure",
        workflow="Deploy",
        job="deploy-prod",
        run_url="https://example.com/run",
        branch="main",
        commit="abc123def456",
        actor="developer",
        environment="production",
        metadata={},
        slack_webhook=None,
        slack_channel=None,
        slack_username=None,
        teams_webhook=None,
        teams_theme_color=None,
        timeout=5.0,
        dry_run=False,
    )

    message = notify_status._compose_message(args)

    assert "Deployment" in message
    assert "failed" in message
    assert "deploy-prod" in message
    assert "main" in message
    assert "abc123d" in message
    assert "developer" in message
    assert "production" in message


def test_normalise_color_with_override() -> None:
    """Test _normalise_color with override."""
    result = notify_status._normalise_color("success", "#123ABC")
    assert result == "123ABC"


def test_normalise_color_from_status() -> None:
    """Test _normalise_color from status."""
    result = notify_status._normalise_color("success", None)
    assert result == "2EB886"


def test_normalise_color_unknown_status() -> None:
    """Test _normalise_color with unknown status."""
    result = notify_status._normalise_color("unknown", None)
    assert result is None


def test_prepare_arguments_basic() -> None:
    """Test _prepare_arguments creates NotificationArguments."""
    parser = notify_status._build_parser()
    namespace = parser.parse_args(
        [
            "--stage",
            "build",
            "--status",
            "success",
            "--workflow",
            "CI",
            "--run-url",
            "https://example.com/run",
        ]
    )

    args = notify_status._prepare_arguments(namespace)

    assert isinstance(args, notify_status.NotificationArguments)
    assert args.stage == "build"
    assert args.status == "success"
    assert "Run" in args.metadata


def test_prepare_arguments_populates_metadata() -> None:
    """Test _prepare_arguments populates metadata from args."""
    parser = notify_status._build_parser()
    namespace = parser.parse_args(
        [
            "--stage",
            "deploy",
            "--status",
            "success",
            "--workflow",
            "Deploy",
            "--run-url",
            "https://example.com/run",
            "--branch",
            "main",
            "--commit",
            "abc123",
            "--actor",
            "dev",
            "--environment",
            "prod",
        ]
    )

    args = notify_status._prepare_arguments(namespace)

    assert args.metadata["Branch"] == "main"
    assert args.metadata["Commit"] == "abc123"
    assert args.metadata["Actor"] == "dev"
    assert args.metadata["Environment"] == "prod"


def test_status_labels_mapping() -> None:
    """Test STATUS_LABELS contains expected statuses."""
    assert "success" in notify_status.STATUS_LABELS
    assert "failure" in notify_status.STATUS_LABELS
    assert "cancelled" in notify_status.STATUS_LABELS
    assert "in_progress" in notify_status.STATUS_LABELS


def test_status_emoji_mapping() -> None:
    """Test STATUS_EMOJI contains expected statuses."""
    assert notify_status.STATUS_EMOJI["success"] == "✅"
    assert notify_status.STATUS_EMOJI["failure"] == "❌"


def test_status_colors_mapping() -> None:
    """Test STATUS_COLORS contains expected colors."""
    assert notify_status.STATUS_COLORS["success"] == "2EB886"
    assert notify_status.STATUS_COLORS["failure"] == "D00000"


def test_stage_labels_mapping() -> None:
    """Test STAGE_LABELS contains expected stages."""
    assert notify_status.STAGE_LABELS["build"] == "Build"
    assert notify_status.STAGE_LABELS["deploy"] == "Deployment"


def test_notification_arguments_dataclass() -> None:
    """Test NotificationArguments dataclass."""
    args = notify_status.NotificationArguments(
        stage="build",
        status="success",
        workflow="CI",
        job="build-job",
        run_url="https://example.com",
        branch="main",
        commit="abc123",
        actor="dev",
        environment="staging",
        metadata={"key": "value"},
        slack_webhook="https://hooks.slack.com/test",
        slack_channel="#channel",
        slack_username="Bot",
        teams_webhook="https://teams.webhook.com/test",
        teams_theme_color="123456",
        timeout=10.0,
        dry_run=True,
    )

    assert args.stage == "build"
    assert args.dry_run is True
    assert args.timeout == 10.0


def test_main_dry_run(capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main with dry-run prints message."""
    # Use actual parser with test arguments
    monkeypatch.setattr(
        "sys.argv",
        [
            "notify_status.py",
            "--stage",
            "build",
            "--status",
            "success",
            "--workflow",
            "CI",
            "--run-url",
            "https://example.com",
            "--dry-run",
        ],
    )

    exit_code = notify_status.main()

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Build Success" in captured.out
