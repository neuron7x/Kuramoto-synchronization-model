#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Generate the GeoSync OpenAPI specification on disk."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "openapi-generation-secret")
os.environ.setdefault("GEOSYNC_OAUTH2_ISSUER", "https://openapi.geosync.local")
os.environ.setdefault("GEOSYNC_OAUTH2_AUDIENCE", "geosync-api")
os.environ.setdefault("GEOSYNC_OAUTH2_JWKS_URI", "https://openapi.geosync.local/jwks")

from application.api.service import create_app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("schemas/openapi/geosync-online-inference-v1.json"),
        help="Path where the OpenAPI document will be written.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = create_app()
    schema = app.openapi()
    output_path: Path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(schema, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
