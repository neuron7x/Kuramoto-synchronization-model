# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import argparse

import pytest

from scripts import notify_status


def test_parse_key_value_success() -> None:
    key, value = notify_status._parse_key_value("foo=bar=baz")
    assert key == "foo"
    assert value == "bar=baz"


def test_parse_key_value_failure() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        notify_status._parse_key_value("invalid")


def test_prepare_arguments_enriches_metadata() -> None:
    namespace = argparse.Namespace(
        stage="build",
        status="success",
        workflow="CI",
        job="coverage",
        run_url="https://example.test/run/1",
        branch="main",
        commit="123456789abcdef",
        actor="octocat",
        environment="staging",
        fields=["coverage=success"],
        slack_webhook=None,
        slack_channel=None,
        slack_username="CI Bot",
        teams_webhook=None,
        teams_theme_color=None,
        timeout=5.0,
        dry_run=False,
    )

    args = notify_status._prepare_arguments(namespace)
    assert args.metadata["coverage"] == "success"
    assert args.metadata["Commit"] == "1234567"
    assert args.metadata["Environment"] == "staging"
    assert args.metadata["Run"] == "https://example.test/run/1"


def test_compose_message_includes_context() -> None:
    args = notify_status.NotificationArguments(
        stage="deploy",
        status="failure",
        workflow="Deploy",
        job="deploy-staging",
        run_url="https://example.test/run/2",
        branch="release",
        commit="abcdef1",
        actor="deployer",
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
    assert "Deployment workflow 'Deploy' / job 'deploy-staging'" in message
    assert "production" in message
    assert "Run details: https://example.test/run/2" in message
