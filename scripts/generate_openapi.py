#!/usr/bin/env python3
"""Generate the TradePulse OpenAPI specification on disk."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("TRADEPULSE_AUDIT_SECRET", "openapi-generation-secret")
os.environ.setdefault("TRADEPULSE_OAUTH2_ISSUER", "https://openapi.tradepulse.local")
os.environ.setdefault("TRADEPULSE_OAUTH2_AUDIENCE", "tradepulse-api")
os.environ.setdefault(
    "TRADEPULSE_OAUTH2_JWKS_URI", "https://openapi.tradepulse.local/jwks"
)

from application.api.service import create_app  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("schemas/openapi/tradepulse-online-inference-v1.json"),
        help="Path where the OpenAPI document will be written.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = create_app()
    schema = app.openapi()
    output_path: Path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(schema, indent=2, sort_keys=True), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
