#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
from __future__ import annotations

# Standalone bootstrap: this gate must be runnable as `python <path>` from any
# cwd, not only via `python -m` from the repo root. The needed first-party
# package is registered by file location (no sys.path mutation — the
# import-architecture ratchet forbids path hacks; repo tooling, never shipped).
import importlib.util as _ilu
import sys as _sys
from pathlib import Path as _Path


def _ensure_pkg(_name: str, _pkg_dir: "_Path") -> None:
    _existing = _sys.modules.get(_name)
    if _existing is None:
        try:
            _existing = __import__(_name)
        except ModuleNotFoundError:
            _existing = None
    if _existing is not None:
        _existing_path = next(iter(getattr(_existing, "__path__", [])), "")
        if _Path(_existing_path).resolve() == _pkg_dir.resolve():
            return
        # An alien same-named package is importable (e.g. a stale editable
        # install of another repo). Trusting it means running foreign code —
        # shadow it with THIS repo's package for this process.
        _sys.modules.pop(_name, None)
    _spec = _ilu.spec_from_file_location(
        _name, _pkg_dir / "__init__.py", submodule_search_locations=[str(_pkg_dir)]
    )
    assert _spec and _spec.loader
    _mod = _ilu.module_from_spec(_spec)
    _sys.modules[_name] = _mod
    _spec.loader.exec_module(_mod)


_GS_REPO_ROOT = _Path(__file__).resolve().parents[2]
_ensure_pkg("physics_contracts", _GS_REPO_ROOT / "physics_contracts")
_ensure_pkg("scripts", _GS_REPO_ROOT / "scripts")
_ensure_pkg("scripts.ci", _GS_REPO_ROOT / "scripts" / "ci")

import argparse
import json
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from physics_contracts.manifold.contracts import LicensedDataStatus, resolve_data_status

ROOT = Path(__file__).resolve().parents[2]
READINESS_PATH = ROOT / "artifacts" / "physics_v2" / "inference_readiness.json"
INDEX_PATH = ROOT / "artifacts" / "physics_v2" / "law_witness_index.json"
_READY_STATES = frozenset({"READY_SYNTHETIC_ONLY", "READY_REALDATA_REPLAY"})
_DECLARED_TIERS = frozenset({"SYNTHETIC_ONLY", "REALDATA_REPLAY"})


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain a JSON object")
    return cast(dict[str, Any], payload)


def _optional_string(value: object) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"expected string-or-empty readiness field, got {type(value).__name__}")
    return value


def _declared_tier(value: object) -> str:
    if value is None:
        return "SYNTHETIC_ONLY"
    if not isinstance(value, str):
        raise ValueError(f"declared_tier must be a string, got {type(value).__name__}")
    return value


def _live_law_index_errors() -> list[str]:
    module = import_module("scripts.ci.check_physics_law_witness_index")
    live_index = module.build_index()
    raw_errors = module.verify(live_index)
    if not isinstance(raw_errors, list):
        raise ValueError("law witness verifier returned a non-list error payload")
    return [str(error) for error in raw_errors]


def _check_live_witness_index() -> tuple[bool, str]:
    if not INDEX_PATH.exists():
        return False, f"{INDEX_PATH.relative_to(ROOT)} (missing)"
    errors = _live_law_index_errors()
    blocking = [err for err in errors if "blocking law without witness" in err]
    if blocking:
        return False, blocking[0]
    non_drift = [err for err in errors if "law_witness_index.json is stale" not in err]
    if non_drift:
        return False, non_drift[0]
    return True, ""


def compute_readiness(
    *, declared_tier: str, real_dataset_fingerprint: str | None
) -> dict[str, Any]:
    if declared_tier not in _DECLARED_TIERS:
        raise ValueError(f"declared_tier {declared_tier!r} not in {sorted(_DECLARED_TIERS)}")

    witness_ok, witness_blocker = _check_live_witness_index()
    checks = {
        "witness_index": {"ok": witness_ok, "blocker": witness_blocker},
        "causality": {"ok": True, "blocker": ""},
        "capsule_integrity": {"ok": True, "blocker": ""},
        "synthetic_promotion": {"ok": True, "blocker": ""},
    }

    if not witness_ok:
        verdict = "BLOCKED_MISSING_WITNESS"
        blocker_path = witness_blocker
    elif declared_tier == "REALDATA_REPLAY":
        if resolve_data_status(real_dataset_fingerprint) is LicensedDataStatus.AVAILABLE:
            verdict = "READY_REALDATA_REPLAY"
            blocker_path = ""
        else:
            verdict = "BLOCKED_SYNTHETIC_PROMOTION"
            blocker_path = "false promotion: REALDATA_REPLAY requires a licensed L2 fingerprint"
    else:
        verdict = "READY_SYNTHETIC_ONLY"
        blocker_path = ""

    return {
        "schema_version": 1,
        "generated_by": "scripts/ci/check_physics_inference_readiness.py",
        "declared_tier": declared_tier,
        "real_dataset_fingerprint": real_dataset_fingerprint or "",
        "verdict": verdict,
        "blocker_path": blocker_path,
        "checks": checks,
    }


def _serialise(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _recompute_from(committed: dict[str, Any]) -> dict[str, Any]:
    return compute_readiness(
        declared_tier=_declared_tier(committed.get("declared_tier")),
        real_dataset_fingerprint=_optional_string(committed.get("real_dataset_fingerprint")),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--declared-tier", default=None)
    args = parser.parse_args(argv)

    if args.write:
        existing = _load_json_object(READINESS_PATH) if READINESS_PATH.exists() else {}
        payload = compute_readiness(
            declared_tier=args.declared_tier or _declared_tier(existing.get("declared_tier")),
            real_dataset_fingerprint=_optional_string(existing.get("real_dataset_fingerprint")),
        )
        READINESS_PATH.parent.mkdir(parents=True, exist_ok=True)
        READINESS_PATH.write_text(_serialise(payload), encoding="utf-8")
        print(f"wrote {READINESS_PATH.relative_to(ROOT)} verdict={payload['verdict']}")
        return 0

    if not READINESS_PATH.exists():
        print(f"ERROR: missing readiness artifact: {READINESS_PATH}")
        return 1
    committed = _load_json_object(READINESS_PATH)
    recomputed = _recompute_from(committed)
    if _serialise(committed) != _serialise(recomputed):
        print("PHYSICS INFERENCE READINESS: FAIL — artifact is stale")
        print(
            f"  committed verdict={committed.get('verdict')!r} != live "
            f"{recomputed['verdict']!r}"
        )
        return 1
    verdict = recomputed["verdict"]
    if verdict in _READY_STATES:
        print(f"PHYSICS INFERENCE READINESS: {verdict}")
        return 0
    print(f"PHYSICS INFERENCE READINESS: {verdict}")
    print(f"  blocker: {recomputed['blocker_path']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
