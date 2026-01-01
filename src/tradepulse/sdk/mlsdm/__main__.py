import argparse
import json
import logging
from typing import Any, Dict

from .core.memory_manager import MemoryManager
from .utils.config_loader import ConfigLoader


class JSONFormatter(logging.Formatter):
    """Simple JSON log formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        log_record: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "logger": record.name,
        }
        if record.exc_info:
            # keep exception info explicit in logs
            log_record["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(log_record, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure root logger with JSON formatter and return module logger."""
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        root.addHandler(handler)
    root.setLevel(level)
    return logging.getLogger(__name__)


logger = configure_logging()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="mlsdm-governed-cognitive-memory CLI",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/default_config.yaml",
        help="Path to YAML config for MemoryManager.",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=100,
        help="Number of simulation steps to run.",
    )
    parser.add_argument(
        "--api",
        action="store_true",
        help="Run HTTP API instead of local simulation.",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host for API server (used only with --api).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for API server (used only with --api).",
    )
    parser.add_argument(
        "--override",
        action="append",
        default=[],
        metavar="PATH=VALUE",
        help=(
            "Override configuration value using dotted path (e.g., "
            "--override agent.state_dim=32 or "
            "--override db.url='postgres://user:pw=1@host/db'). "
            "CLI overrides have highest precedence."
        ),
    )
    return parser


def parse_cli_overrides(overrides: list[str]) -> Dict[str, Any]:
    """Parse CLI overrides provided as PATH=VALUE pairs."""
    parsed: Dict[str, Any] = {}
    for override in overrides:
        if "=" not in override:
            logger.error("Override must be in PATH=VALUE format: %s", override)
            raise SystemExit(1)
        # value may legitimately contain '='; split only on the first occurrence
        path, raw_value = override.split("=", 1)
        if not path:
            logger.error("Override path must be non-empty: %s", override)
            raise SystemExit(1)
        parsed[path] = ConfigLoader._parse_override_value(raw_value, source=path)
    return parsed


def load_config_from_cli(config_path: str, overrides: list[str]) -> Dict[str, Any]:
    """Load MLSDM config with env and CLI overrides applied."""
    cli_overrides = parse_cli_overrides(overrides)
    return ConfigLoader.load_config_with_defaults(
        config_path, env_prefix="MLSDM__", overrides=cli_overrides
    )


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.api:
        try:
            import uvicorn  # type: ignore[import]

            from .api.app import app
        except (ImportError, ModuleNotFoundError) as exc:
            logger.exception("Failed to import API app or uvicorn: %s", exc)
            raise SystemExit(1) from exc

        logger.info("Starting API server")
        uvicorn.run(app, host=args.host, port=args.port)
        return

    try:
        config = load_config_from_cli(args.config, args.override)
    except (FileNotFoundError, OSError) as exc:
        logger.exception("Failed to load config '%s': %s", args.config, exc)
        raise SystemExit(1) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error loading config '%s': %s", args.config, exc)
        raise SystemExit(1) from exc

    try:
        manager = MemoryManager(config)
    except (ValueError, KeyError, AttributeError) as exc:
        logger.exception("Failed to initialize MemoryManager: %s", exc)
        raise SystemExit(1) from exc

    logger.info("Running simulation...", extra={"steps": args.steps})
    try:
        manager.run_simulation(args.steps)
    except (RuntimeError, ValueError) as exc:
        logger.exception("Simulation failed: %s", exc)
        raise SystemExit(1) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected simulation error: %s", exc)
        raise SystemExit(1) from exc
    logger.info("Simulation finished successfully.")


if __name__ == "__main__":
    raise SystemExit(
        "Deprecated entrypoint. Use: python -m application.runtime.server --config <path>"
    )
