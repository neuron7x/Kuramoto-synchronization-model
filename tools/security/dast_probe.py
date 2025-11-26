"""Dynamic application security smoke tests for the TradePulse API."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import logging
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import httpx
from httpx import ASGITransport

_WARNING_FILTERS: tuple[dict[str, object], ...] = (
    {"message": r'Field name "schema" in "QualityGateConfig"', "category": UserWarning},
    {"message": r'directory "/run/secrets" does not exist', "category": UserWarning},
    {
        "message": r"A custom validator is returning a value other than `self`.",
        "category": UserWarning,
        "module": "application.settings",
    },
    {
        "message": r"A custom validator is returning a value other than `self`.",
        "category": UserWarning,
        "module": "pydantic_settings",
    },
)

for filter_kwargs in _WARNING_FILTERS:
    warnings.filterwarnings("ignore", **filter_kwargs)  # type: ignore[arg-type]

from application.settings import BackendRuntimeSettings  # noqa: E402

DEFAULT_REPORT_PATH = Path("reports/security/dast_report.json")


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="Path to write the JSON report summarising DAST checks.",
    )
    parser.add_argument(
        "--host-header",
        default="attacker.tradepulse.invalid",
        help="Host header used to verify trusted host middleware.",
    )
    return parser.parse_args(argv)


def _silence_expected_warnings() -> None:
    warnings.filterwarnings(
        "ignore",
        message=r'Field name "schema" in "QualityGateConfig"',
        category=UserWarning,
    )
    warnings.filterwarnings(
        "ignore",
        message=r'directory "/run/secrets" does not exist',
        category=UserWarning,
    )
    warnings.filterwarnings(
        "ignore",
        message=r"A custom validator is returning a value other than `self`.",
        category=UserWarning,
        module="application.settings",
    )
    warnings.filterwarnings(
        "ignore",
        message=r"A custom validator is returning a value other than `self`.",
        category=UserWarning,
        module="pydantic_settings",
    )


def _build_silent_logger() -> logging.Logger:
    logger = logging.getLogger("tradepulse.audit.dast")
    logger.handlers = []
    logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.CRITICAL)
    logger.propagate = False
    return logger


@contextlib.contextmanager
def _suppress_audit_logging() -> Any:
    from src.audit import audit_logger as audit_module

    original_class = audit_module.AuditLogger

    class _SilentAuditLogger(audit_module.AuditLogger):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("logger", _build_silent_logger())
            super().__init__(*args, **kwargs)

    audit_module.AuditLogger = _SilentAuditLogger
    try:
        yield
    finally:
        audit_module.AuditLogger = original_class


def _create_app() -> Any:
    runtime = BackendRuntimeSettings(
        log_level="ERROR",
        force_log_configuration=True,
        log_variables_on_startup=False,
    )
    _silence_expected_warnings()
    logging.getLogger("httpx").setLevel(logging.CRITICAL)
    from application.api.service import create_app

    with (
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        return create_app(runtime_settings=runtime)


async def _check_health(client: httpx.AsyncClient, report: dict[str, Any]) -> None:
    response = await client.get("/health")
    report["health"] = {
        "status_code": response.status_code,
        "cache_control": response.headers.get("cache-control"),
    }
    if response.status_code != 200:
        raise AssertionError("/health must return 200 OK")
    payload = response.json()
    components = payload.get("components", {})
    risk = components.get("risk_manager", {})
    metrics = risk.get("metrics", {})
    if "kill_switch_engaged" not in metrics:
        raise AssertionError("Risk manager metrics missing kill_switch_engaged flag")
    cache_control = response.headers.get("cache-control", "")
    if not cache_control.startswith("private"):
        raise AssertionError(
            "Cache-Control header should be private for health endpoint"
        )


async def _check_unauthorised_features(
    client: httpx.AsyncClient, report: dict[str, Any]
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "symbol": "BTC-USD",
        "bars": [
            {
                "timestamp": now,
                "high": 101.0,
                "low": 100.0,
                "close": 100.5,
                "open": 100.2,
                "volume": 5.0,
            }
        ],
    }
    response = await client.post("/api/v1/features", json=payload)
    report["unauthorised_features"] = {
        "status_code": response.status_code,
        "body": response.json(),
    }
    if response.status_code != 401:
        raise AssertionError(
            "Unauthenticated feature request must be rejected with 401"
        )
    error = response.json().get("error", {})
    if error.get("code") != "ERR_AUTH_REQUIRED":
        raise AssertionError("Unexpected error code for unauthorised feature request")


async def _check_trusted_host(
    client: httpx.AsyncClient, *, host: str, report: dict[str, Any]
) -> None:
    response = await client.get("/health", headers={"host": host})
    report["trusted_host"] = {
        "status_code": response.status_code,
        "body": response.text,
    }
    if response.status_code != 400:
        raise AssertionError(
            "Requests with an untrusted host header should be rejected"
        )


async def _run_checks(host_header: str) -> dict[str, Any]:
    with _suppress_audit_logging():
        app = _create_app()
    audit_logger = logging.getLogger("tradepulse.audit")
    audit_logger.handlers = [logging.NullHandler()]
    audit_logger.propagate = False
    audit_logger.disabled = True
    report: dict[str, Any] = {"timestamp": datetime.now(timezone.utc).isoformat()}
    logging.disable(logging.CRITICAL)
    try:
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            timeout=5.0,
        ) as client:
            await _check_health(client, report)
            await _check_unauthorised_features(client, report)
            await _check_trusted_host(client, host=host_header, report=report)
    finally:
        logging.disable(logging.NOTSET)
    report["status"] = "passed"
    return report


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report_path = args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            report = asyncio.run(_run_checks(args.host_header))
    except AssertionError as exc:
        failure_report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "failed",
            "reason": str(exc),
        }
        report_path.write_text(
            json.dumps(failure_report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"DAST checks failed: {exc}")
        return 1

    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("DAST checks passed:", json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
