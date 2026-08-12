# SPDX-License-Identifier: MIT
"""ENV-009 environment preflight — the fail-closed guard that runs BEFORE the suite.

This is the *pre-suite gatekeeper* for TST-001. Where ENV-001
(``check_env_preflight.py``) answers a narrow "is this the canonical 3.12
interpreter with resolvable deps" question, ENV-009 is the broader, ordered,
fail-closed guard that a CI job runs *before* invoking any gate or ``pytest``.
If the environment is wrong, the suite never starts, and the caller learns
*which class* of environment fault stopped it from a distinct, stable exit code.

Design contract
---------------
* The verdict lives in a single pure function, :func:`evaluate`, taking a plain
  ``env_facts`` dict and a ``requirements`` dict. Nothing in :func:`evaluate`
  touches the real interpreter, filesystem, or process table, so every failure
  class can be simulated by injecting a doctored ``env_facts`` — no need to
  mutate the real environment, uninstall pandas, or downgrade Python.
* :func:`probe_env_facts` is the *only* impure half: it reads the live
  interpreter, installed-distribution metadata, ``PATH``, disk/memory, and the
  editable-install descriptors, and packs them into the same dict shape that
  tests inject.
* Fail-closed: any HARD failure yields a non-zero exit code that is *specific to
  the failure class* (see :data:`EXIT_CODES`). A correct environment is the only
  path to exit 0.

Exit-code map (class -> code)
-----------------------------
    0   PASS
    10  PYTHON_RANGE       interpreter outside supported [min, max) range
    11  PANDAS_FLOOR       pandas missing or below the named floor
    12  MISSING_DEPENDENCY a required dependency is absent (aiolimiter/tenacity/...)
    13  ARCHITECTURE       CPU architecture not in the supported set
    14  LOCALE             preferred encoding is not UTF-8
    15  TIMEZONE           no timezone resolvable
    16  MISSING_BINARY     a required binary (e.g. git) is not on PATH
    17  FORBIDDEN_EDITABLE a rogue editable install of the package points outside the repo

Advisory (reported, never change the exit code in a sandbox):
    20  DISK               free disk below the advisory threshold
    21  MEMORY             free memory below the advisory threshold

When several HARD classes fail at once the exit code is the *lowest* code among
them (the earliest, most fundamental class), so the reported code is
deterministic regardless of probe order.
"""

from __future__ import annotations

import argparse
import importlib.metadata as importlib_metadata
import json
import locale as _locale
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parents[2]

# --------------------------------------------------------------------------- #
# Exit-code contract — one stable code per failure class.
# --------------------------------------------------------------------------- #
EXIT_PASS = 0
EXIT_CODES: dict[str, int] = {
    "PYTHON_RANGE": 10,
    "PANDAS_FLOOR": 11,
    "MISSING_DEPENDENCY": 12,
    "ARCHITECTURE": 13,
    "LOCALE": 14,
    "TIMEZONE": 15,
    "MISSING_BINARY": 16,
    "FORBIDDEN_EDITABLE": 17,
    # Advisory classes — reported, but do not fail the gate in a sandbox.
    "DISK": 20,
    "MEMORY": 21,
}
ADVISORY_CLASSES = frozenset({"DISK", "MEMORY"})


# --------------------------------------------------------------------------- #
# Default requirements (the second argument to ``evaluate``). Kept explicit so a
# caller — or a test — can override any single floor without editing the source.
# --------------------------------------------------------------------------- #
def default_requirements() -> dict[str, Any]:
    """The canonical ENV-009 requirement set, mirroring ``pyproject.toml``."""
    return {
        # requires-python = ">=3.11,<3.13"
        "python_min": (3, 11),
        "python_max_exclusive": (3, 13),
        # pandas is the named gatekeeper floor.
        "pandas_min": "2.3.3",
        # Presence + (where a floor is given) minimum version.
        "required_dependencies": {
            "pandas": "2.3.3",
            "numpy": None,
            "aiolimiter": None,
            "tenacity": None,
        },
        "package_name": "geosync",
        "supported_architectures": (
            "x86_64",
            "amd64",
            "aarch64",
            "arm64",
        ),
        "required_locale_encodings": ("utf-8", "utf8"),
        "require_timezone": True,
        "required_binaries": ("git",),
        # Recorded for the descriptor; never fail the gate on their absence.
        "optional_binaries": ("docker", "make", "gh"),
        # Advisory thresholds — see ADVISORY_CLASSES.
        "min_free_disk_gb": 2.0,
        "min_free_memory_gb": 1.0,
    }


# --------------------------------------------------------------------------- #
# Pure verdict — no I/O, no interpreter introspection.
# --------------------------------------------------------------------------- #
def _as_version(raw: str | None) -> Version | None:
    if raw is None:
        return None
    try:
        return Version(str(raw))
    except InvalidVersion:
        return None


def evaluate(env_facts: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    """Pure evaluation of environment facts against requirements.

    ``env_facts`` and ``requirements`` are plain dicts; nothing here reads the
    real environment. Returns a report dict with:

    * ``failures``  — ordered list of ``{"class", "code", "detail"}`` for HARD
      classes only (these drive the exit code).
    * ``advisories`` — same shape, for advisory classes (never change exit).
    * ``exit_code`` — 0 when there are no HARD failures, else the *lowest*
      failing class code (deterministic).
    * ``ok``        — ``exit_code == 0``.
    """
    failures: list[dict[str, Any]] = []
    advisories: list[dict[str, Any]] = []

    def fail(cls: str, detail: str) -> None:
        bucket = advisories if cls in ADVISORY_CLASSES else failures
        bucket.append({"class": cls, "code": EXIT_CODES[cls], "detail": detail})

    # --- Python version range ------------------------------------------- #
    py = env_facts.get("python", {})
    have = (py.get("major"), py.get("minor"))
    lo = tuple(requirements["python_min"])
    hi = tuple(requirements["python_max_exclusive"])
    if None in have:
        fail("PYTHON_RANGE", f"python version facts incomplete: {py!r}")
    elif not (lo <= have < hi):
        fail(
            "PYTHON_RANGE",
            f"python {have[0]}.{have[1]} outside supported "
            f"range >={lo[0]}.{lo[1]},<{hi[0]}.{hi[1]}",
        )

    deps: dict[str, str | None] = dict(env_facts.get("dependencies", {}))

    # --- pandas floor (named gatekeeper) -------------------------------- #
    pandas_min = _as_version(requirements["pandas_min"])
    pandas_ver = _as_version(deps.get("pandas"))
    if deps.get("pandas") is None:
        fail("PANDAS_FLOOR", f"pandas not installed (required floor >= {requirements['pandas_min']})")
    elif pandas_ver is None:
        fail("PANDAS_FLOOR", f"pandas version unparseable: {deps.get('pandas')!r}")
    elif pandas_min is not None and pandas_ver < pandas_min:
        fail("PANDAS_FLOOR", f"pandas {pandas_ver} < required floor {pandas_min}")

    # --- other required dependencies (presence + optional floor) -------- #
    for name, floor in requirements["required_dependencies"].items():
        if name == "pandas":
            continue  # already handled by its dedicated class
        installed = deps.get(name)
        if installed is None:
            fail("MISSING_DEPENDENCY", f"required dependency missing: {name}")
            continue
        floor_v = _as_version(floor)
        inst_v = _as_version(installed)
        if floor_v is not None and inst_v is not None and inst_v < floor_v:
            fail("MISSING_DEPENDENCY", f"{name} {inst_v} < required floor {floor_v}")

    # --- architecture --------------------------------------------------- #
    arch = str(env_facts.get("architecture", "")).lower()
    supported = {a.lower() for a in requirements["supported_architectures"]}
    if not arch:
        fail("ARCHITECTURE", "architecture fact missing")
    elif arch not in supported:
        fail("ARCHITECTURE", f"architecture {arch!r} not in supported set {sorted(supported)}")

    # --- locale --------------------------------------------------------- #
    enc = str(env_facts.get("locale_encoding", "")).lower()
    allowed_enc = {e.lower() for e in requirements["required_locale_encodings"]}
    if enc not in allowed_enc:
        fail("LOCALE", f"preferred encoding {enc!r} is not UTF-8 (need one of {sorted(allowed_enc)})")

    # --- timezone ------------------------------------------------------- #
    if requirements.get("require_timezone", True):
        tz = env_facts.get("timezone")
        if not tz:
            fail("TIMEZONE", "no timezone resolvable from the environment")

    # --- required binaries ---------------------------------------------- #
    binaries: dict[str, str | None] = dict(env_facts.get("binaries", {}))
    for name in requirements["required_binaries"]:
        if not binaries.get(name):
            fail("MISSING_BINARY", f"required binary not found on PATH: {name}")

    # --- forbidden editable install of the package ---------------------- #
    pkg = requirements.get("package_name")
    editables: dict[str, str] = dict(env_facts.get("editable_installs", {}))
    allowed_roots = [
        os.path.realpath(str(r)) for r in env_facts.get("allowed_editable_roots", [])
    ]
    if pkg and pkg in editables:
        target = os.path.realpath(editables[pkg])
        inside = any(
            target == root or target.startswith(root.rstrip("/") + "/")
            for root in allowed_roots
        )
        if not inside:
            fail(
                "FORBIDDEN_EDITABLE",
                f"editable install of {pkg!r} points to {target!r}, "
                f"outside allowed repo roots {allowed_roots}",
            )

    # --- advisory: disk / memory ---------------------------------------- #
    free_disk = env_facts.get("free_disk_gb")
    if free_disk is not None and free_disk < requirements["min_free_disk_gb"]:
        fail("DISK", f"free disk {free_disk:.2f} GB < advisory floor {requirements['min_free_disk_gb']} GB")
    free_mem = env_facts.get("free_memory_gb")
    if free_mem is not None and free_mem < requirements["min_free_memory_gb"]:
        fail("MEMORY", f"free memory {free_mem:.2f} GB < advisory floor {requirements['min_free_memory_gb']} GB")

    exit_code = EXIT_PASS if not failures else min(f["code"] for f in failures)
    return {
        "ok": exit_code == EXIT_PASS,
        "exit_code": exit_code,
        "failures": failures,
        "advisories": advisories,
        "checks": {
            "python": have,
            "pandas": deps.get("pandas"),
            "dependencies_present": sorted(k for k, v in deps.items() if v is not None),
            "architecture": env_facts.get("architecture"),
            "locale_encoding": env_facts.get("locale_encoding"),
            "timezone": env_facts.get("timezone"),
            "binaries_present": sorted(k for k, v in binaries.items() if v),
            "editable_installs": editables,
        },
    }


# --------------------------------------------------------------------------- #
# Impure probe — the only half that reads the real world.
# --------------------------------------------------------------------------- #
def _resolved_version(name: str) -> str | None:
    try:
        return importlib_metadata.version(name)
    except importlib_metadata.PackageNotFoundError:
        return None


def _timezone_name() -> str | None:
    # tzname is a 2-tuple; an empty/UTC-less libc still reports ('UTC','UTC').
    names = [n for n in time.tzname if n]
    if names:
        return names[0]
    return os.environ.get("TZ") or None


def _collect_editable_installs(package_names: list[str]) -> dict[str, str]:
    """Return {name: target_dir} for packages installed as `pip install -e`.

    Reads the installed distribution's ``direct_url.json`` (PEP 610); an
    ``editable`` dir_info marks an editable install and ``url`` is its source.
    """
    out: dict[str, str] = {}
    for name in package_names:
        try:
            dist = importlib_metadata.distribution(name)
        except importlib_metadata.PackageNotFoundError:
            continue
        try:
            raw = dist.read_text("direct_url.json")
        except (FileNotFoundError, OSError):
            raw = None
        if not raw:
            continue
        try:
            info = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not info.get("dir_info", {}).get("editable"):
            continue
        url = str(info.get("url", ""))
        prefix = "file://"
        target = url[len(prefix):] if url.startswith(prefix) else url
        if target:
            out[name] = target
    return out


def _allowed_editable_roots() -> list[str]:
    """Repo roots an editable install of the package may legitimately target.

    This worktree's toplevel *and* the canonical repo that owns the shared
    ``.git`` (a ``git worktree`` shares one common dir). An editable pointing at
    either is legitimate; anything else is a rogue install.
    """
    roots: list[str] = []

    def _git(*args: str) -> str | None:
        try:
            res = subprocess.run(
                ["git", "-C", str(ROOT), *args],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return res.stdout.strip() if res.returncode == 0 else None

    roots.append(str(ROOT))
    top = _git("rev-parse", "--show-toplevel")
    if top:
        roots.append(top)
    common = _git("rev-parse", "--git-common-dir")
    if common:
        common_path = Path(common)
        if not common_path.is_absolute():
            common_path = (ROOT / common_path).resolve()
        roots.append(str(common_path.parent))
    # De-dupe on realpath.
    seen: dict[str, None] = {}
    for r in roots:
        seen.setdefault(os.path.realpath(r), None)
    return list(seen.keys())


def probe_env_facts(requirements: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read the live environment into the ``env_facts`` dict ``evaluate`` expects."""
    reqs = requirements or default_requirements()
    vi = sys.version_info

    dep_names = set(reqs["required_dependencies"]) | {"pandas"}
    dependencies = {name: _resolved_version(name) for name in sorted(dep_names)}

    binaries = {
        name: shutil.which(name)
        for name in (*reqs["required_binaries"], *reqs.get("optional_binaries", ()))
    }

    try:
        du = shutil.disk_usage(str(ROOT))
        free_disk_gb: float | None = du.free / (1024**3)
    except OSError:
        free_disk_gb = None

    free_memory_gb: float | None = None
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        avail_pages = os.sysconf("SC_AVPHYS_PAGES")
        if page_size > 0 and avail_pages > 0:
            free_memory_gb = (page_size * avail_pages) / (1024**3)
    except (ValueError, OSError, AttributeError):
        free_memory_gb = None

    pkg = reqs.get("package_name")
    editable_targets = _collect_editable_installs([pkg] if pkg else [])

    return {
        "python": {"major": vi.major, "minor": vi.minor, "micro": vi.micro},
        "dependencies": dependencies,
        "architecture": platform.machine(),
        "locale_encoding": _locale.getpreferredencoding(False),
        "timezone": _timezone_name(),
        "binaries": binaries,
        "free_disk_gb": free_disk_gb,
        "free_memory_gb": free_memory_gb,
        "editable_installs": editable_targets,
        "allowed_editable_roots": _allowed_editable_roots(),
    }


# --------------------------------------------------------------------------- #
# Rendering / CLI
# --------------------------------------------------------------------------- #
def render(report: dict[str, Any]) -> str:
    lines: list[str] = []
    status = "PASS" if report["ok"] else "FAIL"
    lines.append(f"ENV-009 environment preflight: {status} (exit {report['exit_code']})")
    checks = report["checks"]
    py = checks["python"]
    lines.append(f"  python {py[0]}.{py[1]}  pandas {checks['pandas']}")
    lines.append(f"  deps present: {', '.join(checks['dependencies_present']) or '(none)'}")
    lines.append(
        f"  arch={checks['architecture']} locale={checks['locale_encoding']} tz={checks['timezone']}"
    )
    lines.append(f"  binaries: {', '.join(checks['binaries_present']) or '(none)'}")
    if checks["editable_installs"]:
        lines.append(f"  editable installs: {checks['editable_installs']}")
    for adv in report["advisories"]:
        lines.append(f"  [advisory {adv['class']} code {adv['code']}] {adv['detail']}")
    if report["failures"]:
        lines.append("  HARD FAILURES:")
        for f in report["failures"]:
            lines.append(f"      - [{f['class']} exit {f['code']}] {f['detail']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="ENV-009 fail-closed environment preflight (pre-suite gatekeeper).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the preflight report as JSON instead of text.",
    )
    args = parser.parse_args(argv)

    requirements = default_requirements()
    env_facts = probe_env_facts(requirements)
    report = evaluate(env_facts, requirements)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print(render(report))
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
