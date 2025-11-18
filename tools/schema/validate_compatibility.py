"""Validate schema compatibility across all registered event schemas."""

from __future__ import annotations

import argparse

from core.messaging.schema_registry import EventSchemaRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Avro schema compatibility")
    parser.add_argument("--registry", default="schemas/events", help="Path to registry directory")
    args = parser.parse_args()

    registry = EventSchemaRegistry.from_directory(args.registry)
    registry.validate_all()


if __name__ == "__main__":
    main()
