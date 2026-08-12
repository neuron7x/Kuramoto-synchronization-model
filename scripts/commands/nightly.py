# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Execute the nightly regression battery including backtests and E2E flows."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
import argparse
import logging
from pathlib import Path

from observability.incidents import IncidentManager
from observability.notifications import (
    EmailSender,
    NotificationDispatcher,
    SlackNotifier,
)
from scripts.commands.base import CommandError, register
from scripts.nightly import BaselineStore, NightlyRegressionRunner
from scripts.runtime import EXIT_CODES, create_artifact_manager

LOGGER = logging.getLogger(__name__)


def build_parser(subparsers: argparse._SubParsersAction[object]) -> None:
    parser = subparsers.add_parser(
        "nightly",
        help="Run nightly regression backtests and end-to-end validations.",
    )
    parser.set_defaults(command="nightly", handler=handle)
    parser.add_argument(
        "--baseline-path",
        type=Path,
        default=Path("configs/nightly/baselines.json"),
        help="Path to the baseline configuration JSON.",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=None,
        help="Optional root directory for generated artefacts.",
    )
    parser.add_argument(
        "--history-path",
        type=Path,
        default=Path("reports/nightly/regressions/history.jsonl"),
        help="Location of the JSONL history log.",
    )
    parser.add_argument(
        "--incident-root",
        type=Path,
        default=Path("reports/incidents"),
        help="Directory used to persist automatically created incidents.",
    )
    parser.add_argument(
        "--slack-webhook",
        type=str,
        default=None,
        help="Slack webhook URL for team notifications.",
    )
    parser.add_argument(
        "--slack-channel",
        type=str,
        default=None,
        help="Optional Slack channel override for notifications.",
    )
    parser.add_argument(
        "--slack-username",
        type=str,
        default="geosync-nightly",
        help="Displayed username for Slack notifications.",
    )
    parser.add_argument(
        "--email-host",
        type=str,
        default=None,
        help="SMTP host used for email notifications.",
    )
    parser.add_argument(
        "--email-port",
        type=int,
        default=587,
        help="SMTP port used for email notifications (default: 587).",
    )
    parser.add_argument(
        "--email-sender",
        type=str,
        default=None,
        help="Sender address for email notifications.",
    )
    parser.add_argument(
        "--email-recipient",
        action="append",
        default=[],
        help="Recipient address for email notifications (can be specified multiple times).",
    )
    parser.add_argument(
        "--email-username",
        type=str,
        default=None,
        help="SMTP username when authentication is required.",
    )
    parser.add_argument(
        "--email-password",
        type=str,
        default=None,
        help="SMTP password when authentication is required.",
    )
    parser.add_argument(
        "--email-use-ssl",
        action="store_true",
        help="Use SMTPS (implicit TLS). Overrides STARTTLS.",
    )
    parser.add_argument(
        "--email-no-tls",
        action="store_true",
        help="Disable TLS for SMTP connections (not recommended).",
    )


@register("nightly")
def handle(args: argparse.Namespace) -> int:
    try:
        baseline_store = BaselineStore(args.baseline_path)
    except FileNotFoundError as exc:  # pragma: no cover - defensive
        raise CommandError(str(exc)) from exc
    except ValueError as exc:  # pragma: no cover - defensive
        raise CommandError(f"Invalid baseline configuration: {exc}") from exc

    artifact_manager = create_artifact_manager("nightly_regression", root=args.artifact_root)
    incident_manager = IncidentManager(args.incident_root)
    dispatcher = _build_dispatcher(args)

    runner = NightlyRegressionRunner(
        baseline_store=baseline_store,
        artifact_manager=artifact_manager,
        history_path=args.history_path,
        incident_manager=incident_manager,
        notification_dispatcher=dispatcher,
    )
    summary = runner.run()

    LOGGER.info(
        "Nightly regression completed",
        extra={
            "success": summary.success,
            "artifact_dir": str(summary.artifact_dir),
            "incident_id": summary.incident_id,
            "deviations": len(summary.deviations),
        },
    )

    return EXIT_CODES["success"] if summary.success else EXIT_CODES["circuit_breaker_open"]


def _build_dispatcher(args: argparse.Namespace) -> NotificationDispatcher | None:
    slack_notifier: SlackNotifier | None = None
    if args.slack_webhook:
        slack_notifier = SlackNotifier(
            args.slack_webhook,
            channel=args.slack_channel,
            username=args.slack_username,
        )

    email_sender: EmailSender | None = None
    if args.email_host:
        if not args.email_sender or not args.email_recipient:
            raise CommandError(
                "Email notifications require --email-sender and at least one --email-recipient."
            )
        use_tls = not args.email_no_tls and not args.email_use_ssl
        email_sender = EmailSender(
            host=args.email_host,
            port=int(args.email_port),
            sender=args.email_sender,
            recipients=tuple(args.email_recipient),
            username=args.email_username,
            password=args.email_password,
            use_tls=use_tls,
            use_ssl=bool(args.email_use_ssl),
        )

    if not slack_notifier and not email_sender:
        return None

    return NotificationDispatcher(
        email_sender=email_sender,
        slack_notifier=slack_notifier,
        logger=LOGGER,
    )
