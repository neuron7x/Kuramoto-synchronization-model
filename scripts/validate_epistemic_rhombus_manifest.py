# mypy: ignore-errors
# SPDX-License-Identifier: MIT
"""Compatibility wrapper for the Epistemic Rhombus manifest validator."""

from __future__ import annotations

import runpy
from pathlib import Path

_symbols = runpy.run_path(str(Path(__file__).with_suffix(".impl")))
iter_jsonl = _symbols["iter_jsonl"]
load_schema = _symbols["load_schema"]
required_axis_order = _symbols["required_axis_order"]
required_axes = _symbols["required_axes"]
format_schema_error = _symbols["format_schema_error"]
command_target_exists = _symbols["command_target_exists"]
validate_external_gate = _symbols["validate_external_gate"]
validate_manifest = _symbols["validate_manifest"]
build_report = _symbols["build_report"]
write_report = _symbols["write_report"]
main = _symbols["main"]

if __name__ == "__main__":
    raise SystemExit(main())
