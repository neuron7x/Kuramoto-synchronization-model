"""Send consolidated pipeline status notifications to Slack and Teams."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Dict

from observability.notifications import (
    NotificationDispatcher,
    SlackNotifier,
    TeamsNotifier,
)

STATUS_LABELS = {
    "success": "Success",
    "failure": "Failure",
    "cancelled": "Cancelled",
    "in_progress": "In Progress",
}

STATUS_EMOJI = {
    "success": "✅",
    "failure": "❌",
    "cancelled": "⚠️",
    "in_progress": "⏳",
}

STATUS_VERBS = {
    "success": "completed successfully",
    "failure": "failed",
    "cancelled": "was cancelled",
    "in_progress": "is in progress",
}

STATUS_COLORS = {
    "success": "2EB886",
    "failure": "D00000",
    "cancelled": "DAA038",
    "in_progress": "1D9BD1",
}

STAGE_LABELS = {
    "build": "Build",
    "deploy": "Deployment",
}

LOGGER = logging.getLogger("tradepulse.notify_status")


@dataclass(slots=True)
class NotificationArguments:
    stage: str
    status: str
    workflow: str
    job: str | None
    run_url: str
    branch: str | None
    commit: str | None
    actor: str | None
    environment: str | None
    metadata: Dict[str, str]
    slack_webhook: str | None
    slack_channel: str | None
    slack_username: str | None
    teams_webhook: str | None
    teams_theme_color: str | None
    timeout: float
    dry_run: bool


def _parse_key_value(payload: str) -> tuple[str, str]:
    if "=" not in payload:
        raise argparse.ArgumentTypeError(
            f"Invalid metadata entry '{payload}'. Expected KEY=VALUE format."
        )
    key, value = payload.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        raise argparse.ArgumentTypeError(
            f"Invalid metadata entry '{payload}'. Key cannot be empty."
        )
    return key, value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=sorted(STAGE_LABELS),
        required=True,
        help="Logical pipeline stage (build or deploy).",
    )
    parser.add_argument(
        "--status",
        choices=sorted(STATUS_LABELS),
        required=True,
        help="Terminal status of the pipeline stage.",
    )
    parser.add_argument("--workflow", required=True, help="GitHub workflow name.")
    parser.add_argument("--job", help="Job name within the workflow.")
    parser.add_argument("--run-url", required=True, help="URL to the workflow run.")
    parser.add_argument("--branch", help="Git reference name associated with the run.")
    parser.add_argument("--commit", help="Commit SHA associated with the run.")
    parser.add_argument("--actor", help="GitHub actor that triggered the run.")
    parser.add_argument(
        "--environment", help="Target environment for deployment notifications."
    )
    parser.add_argument(
        "--field",
        dest="fields",
        action="append",
        default=[],
        help="Additional KEY=VALUE metadata pairs (can be repeated).",
    )
    parser.add_argument(
        "--slack-webhook",
        default=os.environ.get("SLACK_WEBHOOK_URL"),
        help="Slack incoming webhook URL (falls back to SLACK_WEBHOOK_URL env var).",
    )
    parser.add_argument(
        "--slack-channel",
        default=os.environ.get("SLACK_CHANNEL"),
        help="Override Slack channel routed by the webhook.",
    )
    parser.add_argument(
        "--slack-username",
        default=os.environ.get("SLACK_USERNAME", "TradePulse CI Bot"),
        help="Display name for Slack notifications.",
    )
    parser.add_argument(
        "--teams-webhook",
        default=os.environ.get("TEAMS_WEBHOOK_URL"),
        help="Microsoft Teams incoming webhook URL (falls back to TEAMS_WEBHOOK_URL env var).",
    )
    parser.add_argument(
        "--teams-theme-color",
        default=os.environ.get("TEAMS_THEME_COLOR"),
        help="Override hex color applied to Microsoft Teams cards.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="HTTP timeout (seconds) applied to webhook requests.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the rendered payload instead of delivering notifications.",
    )
    return parser


def _collect_metadata(fields: list[str]) -> Dict[str, str]:
    metadata: Dict[str, str] = {}
    for entry in fields:
        key, value = _parse_key_value(entry)
        metadata[key] = value
    return metadata


def _short_sha(sha: str | None) -> str | None:
    if not sha:
        return None
    stripped = sha.strip()
    if len(stripped) <= 7:
        return stripped
    return stripped[:7]


def _derive_subject(stage: str, status: str) -> str:
    stage_label = STAGE_LABELS.get(stage, stage.title())
    status_label = STATUS_LABELS.get(status, status.title())
    return f"{stage_label} {status_label}"


def _compose_message(args: NotificationArguments) -> str:
    emoji = STATUS_EMOJI.get(args.status, "ℹ️")
    verb = STATUS_VERBS.get(args.status, "completed")
    stage_label = STAGE_LABELS.get(args.stage, args.stage.title())

    context = f"workflow '{args.workflow}'"
    if args.job:
        context = f"{context} / job '{args.job}'"

    qualifiers: list[str] = []
    if args.environment:
        qualifiers.append(f"environment *{args.environment}*")
    if args.branch:
        qualifiers.append(f"branch `{args.branch}`")
    commit_short = _short_sha(args.commit)
    if commit_short:
        qualifiers.append(f"commit `{commit_short}`")

    qualifier_str = " for " + ", ".join(qualifiers) if qualifiers else ""
    first_line = f"{emoji} {stage_label} {context}{qualifier_str} {verb}."

    details: list[str] = [first_line]
    if args.actor:
        details.append(f"Triggered by `{args.actor}`.")
    details.append(f"Run details: {args.run_url}")
    return "\n".join(details)


def _normalise_color(status: str, override: str | None) -> str | None:
    color = override or STATUS_COLORS.get(status)
    if not color:
        return None
    return color.lstrip("#").upper()


def _prepare_arguments(namespace: argparse.Namespace) -> NotificationArguments:
    metadata = _collect_metadata(namespace.fields)

    if namespace.environment:
        metadata.setdefault("Environment", namespace.environment)
    if namespace.branch:
        metadata.setdefault("Branch", namespace.branch)
    commit_short = _short_sha(namespace.commit)
    if commit_short:
        metadata.setdefault("Commit", commit_short)
    if namespace.actor:
        metadata.setdefault("Actor", namespace.actor)
    metadata.setdefault("Run", namespace.run_url)

    return NotificationArguments(
        stage=namespace.stage,
        status=namespace.status,
        workflow=namespace.workflow,
        job=namespace.job,
        run_url=namespace.run_url,
        branch=namespace.branch,
        commit=namespace.commit,
        actor=namespace.actor,
        environment=namespace.environment,
        metadata=metadata,
        slack_webhook=namespace.slack_webhook,
        slack_channel=namespace.slack_channel,
        slack_username=namespace.slack_username,
        teams_webhook=namespace.teams_webhook,
        teams_theme_color=_normalise_color(
            namespace.status, namespace.teams_theme_color
        ),
        timeout=namespace.timeout,
        dry_run=bool(namespace.dry_run),
    )


async def _send_notifications(args: NotificationArguments) -> None:
    slack_notifier: SlackNotifier | None = None
    teams_notifier: TeamsNotifier | None = None

    if args.slack_webhook:
        slack_notifier = SlackNotifier(
            args.slack_webhook,
            channel=args.slack_channel or None,
            username=args.slack_username or None,
            timeout=args.timeout,
        )

    if args.teams_webhook:
        teams_notifier = TeamsNotifier(
            args.teams_webhook,
            theme_color=args.teams_theme_color,
            timeout=args.timeout,
        )

    if not slack_notifier and not teams_notifier:
        LOGGER.info("No notification channels configured; skipping delivery.")
        return

    dispatcher = NotificationDispatcher(
        slack_notifier=slack_notifier,
        teams_notifier=teams_notifier,
        logger=LOGGER,
    )

    subject = _derive_subject(args.stage, args.status)
    message = _compose_message(args)
    await dispatcher.dispatch(
        f"pipeline.{args.stage}.{args.status}",
        subject=subject,
        message=message,
        metadata=args.metadata,
    )
    await dispatcher.aclose()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    parser = _build_parser()
    namespace = parser.parse_args()
    args = _prepare_arguments(namespace)

    if args.dry_run:
        subject = _derive_subject(args.stage, args.status)
        message = _compose_message(args)
        print(subject)
        print(message)
        print(args.metadata)
        return 0

    try:
        asyncio.run(_send_notifications(args))
    except Exception:  # pragma: no cover - defensive logging
        LOGGER.exception("Notification delivery crashed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
