#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic environment digest for evidence-grade artifact provenance.

``env_sha256`` in the research-inference artifact is the sha256 of a canonical
lock manifest: the interpreter version, the frozen dependency closure, and the
BLAS/LAPACK identity. It exists so a PASS artifact pins the numeric stack that
produced it — two clean checkouts at the same ``git_sha`` can resolve different
NumPy/SciPy/BLAS builds and yield different float bits (SLSA Provenance v1
``resolvedDependencies``; Pineau et al., JMLR 22(164), 2021, "computing
infrastructure used").

The manifest is serialised with ``sort_keys=True`` so the digest is stable for a
fixed environment regardless of dict ordering. Run::

    python -m tools.provenance.env_digest          # prints the 64-hex digest
    python -m tools.provenance.env_digest --manifest   # prints the canonical manifest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from importlib import metadata


def _interpreter() -> str:
    v = sys.version_info
    return f"cpython-{v.major}.{v.minor}.{v.micro}"


def _frozen_dependencies() -> list[str]:
    """Sorted ``name==version`` for every installed distribution (lowercased name)."""
    seen: dict[str, str] = {}
    for dist in metadata.distributions():
        name = (dist.metadata["Name"] or "").strip().lower()
        version = (dist.version or "").strip()
        if name:
            seen[name] = version
    return sorted(f"{name}=={version}" for name, version in seen.items())


def _blas_identity() -> str:
    """A stable string identifying the BLAS/LAPACK backend NumPy is linked against."""
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - numpy is a sci-core dep
        return "numpy:absent"
    cfg = getattr(np, "__config__", None)
    get_info = getattr(cfg, "get_info", None) if cfg is not None else None
    if callable(get_info):
        try:
            info = get_info("blas_opt")
            libs = info.get("libraries") if isinstance(info, dict) else None
            if libs:
                return "blas:" + ",".join(sorted(str(library) for library in libs))
        except Exception:  # pragma: no cover - backend-specific probing
            pass
    return f"numpy:{getattr(np, '__version__', 'unknown')}"


def environment_manifest() -> dict[str, object]:
    """The canonical, ordering-independent environment description."""
    return {
        "interpreter": _interpreter(),
        "dependencies": _frozen_dependencies(),
        "blas": _blas_identity(),
    }


def env_sha256(manifest: dict[str, object] | None = None) -> str:
    """sha256 of the canonical (sort_keys=True) environment manifest."""
    payload = manifest if manifest is not None else environment_manifest()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        action="store_true",
        help="Print the canonical manifest instead of the digest.",
    )
    args = parser.parse_args(argv)
    manifest = environment_manifest()
    if args.manifest:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    else:
        print(env_sha256(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
