#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Executable self-test suite for the GeoSync connectome gate.

This runner intentionally avoids pytest and repository-level ``conftest.py`` so
that the architectural gate can validate its own inference boundary with only
its declared runtime dependency surface.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from tools.architecture.check_connectome import main, validate_repository


def _write_contract(path: Path, root: Path) -> None:
    path.write_text(
        f"""
version: "test"
system_name: "GeoSync-NPQ-OS-SelfTest"
scan_roots:
  - "{(root / 'geosync').as_posix()}"
domains:
  sensory:
    state: "active"
    owner: "data@geosync"
    paths:
      - "{(root / 'geosync/cortex/sensory').as_posix()}"
    import_roots:
      - "geosync/cortex/sensory"
    role: "data ingestion"
    allowed_imports: []
    forbidden_imports:
      - "geosync/cortex/motor"
  hippocampus:
    state: "active"
    owner: "memory@geosync"
    paths:
      - "{(root / 'geosync/cortex/hippocampus').as_posix()}"
    import_roots:
      - "geosync/cortex/hippocampus"
    role: "memory"
    allowed_imports:
      - "geosync/cortex/sensory"
    forbidden_imports:
      - "geosync/cortex/motor"
  motor:
    state: "reserved"
    owner: "execution@geosync"
    paths:
      - "{(root / 'geosync/cortex/motor').as_posix()}"
    import_roots:
      - "geosync/cortex/motor"
    role: "execution"
    allowed_imports: []
    forbidden_imports: []
""".strip() + "\n",
        encoding="utf-8",
    )


def _module(root: Path, rel: str, source: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _case(
    name: str,
    source_path: str,
    source: str,
    expected: int,
    expected_fragment: str,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = root / "connectome.yaml"
        _write_contract(contract, root)
        _module(root, source_path, source)
        violations = validate_repository(contract_path=contract)
        actual = len(violations)
        if actual != expected:
            raise AssertionError(
                f"{name}: expected {expected} violations, got {actual}: {violations!r}"
            )
        if expected_fragment:
            payload = json.dumps(
                [violation.to_json() for violation in violations],
                sort_keys=True,
            )
            if expected_fragment not in payload:
                raise AssertionError(
                    f"{name}: expected fragment {expected_fragment!r} in {payload}"
                )


def run() -> None:
    _case(
        "direct-forbidden",
        "geosync/cortex/sensory/feed.py",
        "from geosync.cortex.motor import venue\n",
        1,
        "strictly forbidden",
    )
    _case(
        "package-child-forbidden",
        "geosync/cortex/sensory/feed.py",
        "from geosync.cortex import motor\n",
        1,
        "geosync.cortex.motor",
    )
    _case(
        "relative-forbidden",
        "geosync/cortex/sensory/feed.py",
        "from ..motor import venue\n",
        1,
        "geosync.cortex.motor",
    )
    _case(
        "literal-dynamic-forbidden",
        "geosync/cortex/sensory/feed.py",
        "import importlib\nimportlib.import_module('geosync.cortex.motor.venue')\n",
        1,
        "dynamic import geosync.cortex.motor.venue",
    )
    _case(
        "allowed-cross-domain",
        "geosync/cortex/hippocampus/memory.py",
        "import geosync.cortex.sensory.contracts\n",
        0,
        "",
    )
    _case(
        "unlisted-cross-domain",
        "geosync/cortex/motor/execution.py",
        "import geosync.cortex.hippocampus.memory\n",
        1,
        "absent from allowed_imports",
    )
    if main(["--format", "json"]) != 0:
        raise AssertionError("canonical connectome JSON check must pass")


if __name__ == "__main__":
    run()
    print("connectome selftest passed")
