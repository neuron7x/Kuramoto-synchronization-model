"""Container-friendly application launcher for TradePulse."""

from __future__ import annotations

import logging
import os
from typing import Final

import uvicorn

_LOGGER = logging.getLogger(__name__)

_DEFAULT_HOST: Final[str] = "0.0.0.0"
_DEFAULT_PORT: Final[int] = 8000
_PORT_ENV_VAR: Final[str] = "TRADEPULSE_HTTP_PORT"


def _resolve_port(env_var: str = _PORT_ENV_VAR, fallback: int = _DEFAULT_PORT) -> int:
    """Return an integer port derived from *env_var* or *fallback*.

    Raises a :class:`ValueError` if the environment value is not a valid
    TCP port number. This keeps misconfiguration failures obvious and
    surfaces them early during container startup.
    """

    raw_value = os.getenv(env_var)
    if raw_value is None:
        return fallback

    try:
        port = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Environment variable {env_var} must be an integer port, got {raw_value!r}."
        ) from exc

    if not (1 <= port <= 65535):
        raise ValueError(
            f"Environment variable {env_var} must resolve to a port between 1 and 65535, got {port}."
        )

    return port


def main() -> None:
    """Boot the FastAPI application under uvicorn using runtime configuration."""

    port = _resolve_port()
    _LOGGER.info("Starting TradePulse API", extra={"port": port, "host": _DEFAULT_HOST})
    uvicorn.run("application.api.service:app", host=_DEFAULT_HOST, port=port)


if __name__ == "__main__":
    main()
