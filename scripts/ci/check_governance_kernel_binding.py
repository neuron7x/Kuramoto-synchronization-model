#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Enforce that the verification-protocol governance kernel stays bound to runtime.

``data/governance/neuron7x_verification_protocol_v2026_8.json`` was policy-theater
until ``governance.verification_protocol`` started loading and executing it. This
gate makes that binding permanent: it fails closed if the kernel drifts away from
its schema, or if the engine can no longer load and execute the declared contract.

Checks::

    1. The kernel JSON is schema-valid
       (schemas/governance/neuron7x_verification_protocol.schema.json).
    2. governance.verification_protocol can load it fail-closed.
    3. The declared score weights sum to 1.0 and the thresholds partition [0, 1].
    4. A round-trip evaluation produces a declared conformance state, and the
       weakest-link rule actually clamps a perfect score below a weak proof link.

Exit codes::

    0  — kernel is schema-valid and executably bound
    1  — kernel drifted, malformed, or no longer executable
    2  — schema or kernel file missing
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "governance" / "neuron7x_verification_protocol.schema.json"
KERNEL_PATH = ROOT / "data" / "governance" / "neuron7x_verification_protocol_v2026_8.json"


def _ensure_pkg(_name: str, _pkg_dir: Path) -> None:
    """Register a first-party package by file location — no sys.path mutation
    (the import-architecture ratchet forbids path hacks; repo tooling only)."""
    import importlib.util as _ilu

    if _name in sys.modules:
        _existing = next(iter(getattr(sys.modules[_name], "__path__", [])), "")
        if _existing and Path(_existing).resolve() == _pkg_dir.resolve():
            return
    _spec = _ilu.spec_from_file_location(
        _name, _pkg_dir / "__init__.py", submodule_search_locations=[str(_pkg_dir)]
    )
    if _spec and _spec.loader:
        _mod = _ilu.module_from_spec(_spec)
        sys.modules[_name] = _mod
        _spec.loader.exec_module(_mod)


def main() -> int:
    if not SCHEMA_PATH.exists():
        print(f"schema not found: {SCHEMA_PATH}", file=sys.stderr)
        return 2
    if not KERNEL_PATH.exists():
        print(f"kernel not found: {KERNEL_PATH}", file=sys.stderr)
        return 2

    # 1) schema validity
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft7Validator.check_schema(schema)
    kernel = json.loads(KERNEL_PATH.read_text(encoding="utf-8"))
    errors = sorted(
        jsonschema.Draft7Validator(schema).iter_errors(kernel),
        key=lambda e: list(e.path),
    )
    if errors:
        for err in errors:
            loc = "/".join(str(p) for p in err.path) or "<root>"
            print(f"  ✗ schema: {loc}: {err.message}", file=sys.stderr)
        print("FAIL: verification kernel violates its schema.", file=sys.stderr)
        return 1

    # 2-4) the engine must load and execute the kernel (the actual binding).
    # ImportError ⇒ the engine was deleted; ValueError ⇒ the kernel drifted out
    # of the executable contract. Either means the binding regressed.
    try:
        if (ROOT / "governance" / "__init__.py").exists():
            _ensure_pkg("governance", ROOT / "governance")
        from governance.verification_protocol import VerificationProtocol

        vp = VerificationProtocol.load(KERNEL_PATH)
        weight_sum = sum(w for _, w in vp.weights)
        if abs(weight_sum - 1.0) > 1e-9:
            raise ValueError(f"weights sum to {weight_sum!r}, not 1.0")
        full = dict.fromkeys(vp.variables, 1.0)
        top_state = vp.quantize(vp.score(full))
        if top_state not in vp.conformance_order:
            raise ValueError(f"perfect score quantized to undeclared state {top_state!r}")
        weakest = vp.conformance_order[1]  # any non-bottom proof link
        verdict = vp.evaluate(full, weakest_link_state=weakest)
        if not verdict.clamped or verdict.final_state != weakest:
            raise ValueError("weakest-link rule did not clamp a perfect score")
    except (ImportError, ValueError) as exc:
        print(f"FAIL: kernel is not executably bound: {exc}", file=sys.stderr)
        return 1

    print(
        f"PASS: {vp.kernel_id} v{vp.version} is schema-valid and executably bound "
        f"({len(vp.variables)} weighted axes, {len(vp.thresholds)} conformance bands)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
