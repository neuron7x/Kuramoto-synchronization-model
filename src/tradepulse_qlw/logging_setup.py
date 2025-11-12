"""Logging configuration with PII masking."""

import hashlib
import logging
import logging.config
import os

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class MaskFilter(logging.Filter):
    """Filter to mask sensitive payload data in logs."""

    def filter(self, record):
        try:
            if isinstance(record.args, dict) and "payload" in record.args:
                payload = str(record.args["payload"]).encode()
                record.args["payload"] = hashlib.sha256(payload).hexdigest()
        except Exception:
            pass
        return True


def setup_logging(path: str | None = None) -> None:
    """
    Setup logging configuration from file or defaults.

    Parameters
    ----------
    path : str, optional
        Path to logging config file (YAML)
    """
    path = path or os.getenv("QLW_LOG_CFG", "configs/logging.yml")
    if YAML_AVAILABLE and os.path.exists(path):
        with open(path, "r") as f:
            cfg = yaml.safe_load(f)
        cfg.setdefault("filters", {})["mask_payload"] = {
            "()": "tradepulse_qlw.logging_setup.MaskFilter"
        }
        logging.config.dictConfig(cfg)
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
