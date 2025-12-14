from __future__ import annotations

import logging
from typing import Callable

import pytest

from observability.logging import configure_logging


@pytest.fixture()
def restore_logging() -> Callable[[], None]:
    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level

    def _restore() -> None:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in handlers:
            root.addHandler(handler)
        root.setLevel(level)

    try:
        yield _restore
    finally:
        _restore()


def test_configure_logging_emits_structured_payload(
    restore_logging: Callable[[], None],
) -> None:
    records: list[dict[str, object]] = []
    configure_logging(level="DEBUG", sink=records.append)

    logger = logging.getLogger("tradepulse.test")
    logger.debug("debug event", extra={"component": "test"})
    logger.error("error event", extra={"error_code": 500})

    restore_logging()

    assert len(records) == 2
    assert records[0]["level"] == "debug"
    assert records[0]["component"] == "test"
    assert records[1]["level"] == "error"
    assert records[1]["error_code"] == 500


def test_configure_logging_accepts_numeric_string_level(
    restore_logging: Callable[[], None],
) -> None:
    records: list[dict[str, object]] = []

    configure_logging(level="20", sink=records.append)

    logger = logging.getLogger("tradepulse.test")
    logger.info("info event")

    restore_logging()

    assert records
    assert records[0]["level"] == "info"
