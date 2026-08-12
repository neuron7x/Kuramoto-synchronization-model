#!/usr/bin/env python3
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


_GS_REPO_ROOT = _Path(__file__).resolve().parents[1]
_ensure_pkg("scripts", _GS_REPO_ROOT / "scripts")

from scripts.dopamine_contract_core import (
    ARTIFACT,
    CONTRACT,
    DENIED_EDGES_KEY,
    PROMOTION_FLAG_KEY,
    ROOT,
    VALID_STATUSES,
    load_contract,
    main,
    sha256,
    validate_contract,
    validate_required_artifacts,
    write_artifact,
)

__all__ = [
    "ARTIFACT",
    "CONTRACT",
    "DENIED_EDGES_KEY",
    "PROMOTION_FLAG_KEY",
    "ROOT",
    "VALID_STATUSES",
    "load_contract",
    "main",
    "sha256",
    "validate_contract",
    "validate_required_artifacts",
    "write_artifact",
]


if __name__ == "__main__":
    raise SystemExit(main())
