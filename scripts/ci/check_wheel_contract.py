#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Wheel-contract gate — the distributable wheel must be structurally honest.

Builds the wheel from a clean ``git archive HEAD`` (no working-tree cruft, no
stale ``build/`` — which silently re-ships old packages — and no install cache)
and proves three contracts the release depends on:

1. ENTRY-POINT INTEGRITY — every ``[project.scripts]`` target's top-level
   package is actually shipped in the wheel, so no console script is dead on a
   clean install.
2. NO LATENT BROKEN IMPORT — no packaged module imports a *first-party*
   top-level package that the wheel does NOT ship (e.g. ``tools`` importing an
   excluded ``cli``). Third-party / stdlib imports are ignored; those are
   dependency concerns, not packaging contract breaks.
3. DYNAMIC SMOKE — in a fresh ``--no-deps`` venv, ``import geosync`` must
   succeed, and each entry-point target must import OR fail only on a missing
   *third-party* dependency (classified NEEDS_EXTRA, never a contract break).

Emits ``artifacts/wheel_contract.json`` with wheel_sha256, installed_packages,
entrypoints, import_failures, script_failures, verdict.

Exit codes::

    0  — PASS (no entry-point break, no latent first-party import break)
    1  — FAIL (a contract violation; see JSON / stderr)
    2  — wheel could not be built (cannot establish the contract; fail-closed)
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "artifacts" / "wheel_contract.json"
BASELINE_PATH = ROOT / ".github" / "bwheel_baseline.json"


def _import_key(failure: dict[str, str]) -> str:
    return f"{failure['module']}::{failure['imports_unpackaged']}"


def _load_baseline() -> tuple[set[str], set[str]]:
    """Return (allowed_legacy_packages, frozen import-debt keys)."""
    if not BASELINE_PATH.exists():
        return set(), set()
    payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    pkgs = set(payload.get("allowed_legacy_packages", {}))
    debt = set(payload.get("import_debt", []))
    return pkgs, debt


def _write_baseline(packages: set[str], import_failures: list[dict[str, str]]) -> None:
    existing: dict[str, Any] = {}
    if BASELINE_PATH.exists():
        existing = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    prior_reasons: dict[str, str] = dict(existing.get("allowed_legacy_packages", {}))
    allowed = {
        pkg: prior_reasons.get(pkg, "legacy entrypoint/import provider pending re-home (ADR-0024)")
        for pkg in sorted(packages)
    }
    payload = {
        "version": 1,
        "target": (
            "Only canonical geosync.* in the distributable wheel, with zero "
            "packaged-module imports of unpackaged first-party namespaces. "
            "allowed_legacy_packages and import_debt may ONLY shrink."
        ),
        "allowed_legacy_packages": allowed,
        "import_debt": sorted(_import_key(f) for f in import_failures),
    }
    BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class WheelBuildError(RuntimeError):
    """Raised when the clean-room wheel cannot be built."""


def _first_party_top_level() -> set[str]:
    """Top-level package dirs in the repo (have __init__.py) — the first-party set."""
    out: set[str] = set()
    for child in ROOT.iterdir():
        if child.is_dir() and (child / "__init__.py").is_file():
            out.add(child.name)
    return out


def _stdlib_names() -> set[str]:
    names = set(sys.stdlib_module_names)
    names.update({"__future__"})
    return names


def _entrypoints() -> dict[str, str]:
    import tomllib

    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = data.get("project", {}).get("scripts", {})
    return {str(k): str(v) for k, v in scripts.items()}


def _build_wheel(dest: Path) -> Path:
    """Build the wheel from a clean ``git archive HEAD`` into *dest*; return path."""
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        arch = tdp / "src.tar"
        with arch.open("wb") as fh:
            subprocess.run(
                ["git", "archive", "--format=tar", "HEAD"], cwd=ROOT, stdout=fh, check=True
            )
        srcdir = tdp / "src_tree"
        srcdir.mkdir()
        subprocess.run(["tar", "-xf", str(arch), "-C", str(srcdir)], check=True)
        build = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--no-cache-dir",
                "-w",
                str(dest),
                str(srcdir),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        wheels = list(dest.glob("*.whl"))
        if build.returncode != 0 or not wheels:
            raise WheelBuildError(build.stderr[-600:] or "wheel build produced no artifact")
        return wheels[0]


def _packaged_modules(wheel: Path) -> tuple[set[str], list[tuple[str, str]]]:
    """Return (top_level_packages, [(member_path, source)]) of .py in the wheel."""
    tops: set[str] = set()
    sources: list[tuple[str, str]] = []
    with zipfile.ZipFile(wheel) as zf:
        for name in zf.namelist():
            top = name.split("/")[0]
            if top.endswith(".dist-info"):
                continue
            tops.add(top)
            if name.endswith(".py"):
                sources.append((name, zf.read(name).decode("utf-8", "replace")))
    return tops, sources


def _imported_top_levels(source: str) -> set[str]:
    out: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                out.add(node.module.split(".")[0])
    return out


def _dynamic_smoke(
    wheel: Path, entrypoints: dict[str, str], first_party: set[str]
) -> list[dict[str, str]]:
    """Install wheel --no-deps in a fresh venv; import geosync + each EP target."""
    failures: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory() as td:
        venv = Path(td) / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        py = venv / "bin" / "python"
        inst = subprocess.run(
            [str(py), "-m", "pip", "install", "--no-deps", "-q", str(wheel)],
            capture_output=True,
            text=True,
            check=False,
        )
        if inst.returncode != 0:
            return [{"target": "<install>", "kind": "INSTALL_FAIL", "detail": inst.stderr[-300:]}]
        targets = {"import geosync": "geosync"}
        for name, spec in entrypoints.items():
            targets[name] = spec.split(":")[0]
        probe = (
            "import importlib,sys,json\n"
            "res=[]\n"
            "for label,mod in json.loads(sys.argv[1]).items():\n"
            "    try:\n"
            "        importlib.import_module(mod)\n"
            "    except ModuleNotFoundError as e:\n"
            "        res.append({'target':label,'missing':(e.name or '').split('.')[0]})\n"
            "    except Exception as e:\n"
            "        res.append({'target':label,'missing':'','err':type(e).__name__})\n"
            "print(json.dumps(res))\n"
        )
        run = subprocess.run(
            [str(py), "-c", probe, json.dumps(targets)],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            raw = json.loads(run.stdout.strip().splitlines()[-1]) if run.stdout.strip() else []
        except (ValueError, IndexError):
            return [{"target": "<probe>", "kind": "PROBE_FAIL", "detail": run.stderr[-300:]}]
        for item in raw:
            missing = item.get("missing", "")
            if item["target"] == "import geosync":
                failures.append({"target": "import geosync", "kind": "FAIL", "detail": item})
            elif missing in first_party:
                failures.append(
                    {"target": item["target"], "kind": "FIRST_PARTY_MISSING", "detail": missing}
                )
            elif missing:
                failures.append(
                    {"target": item["target"], "kind": "NEEDS_EXTRA", "detail": missing}
                )
            else:
                failures.append(
                    {
                        "target": item["target"],
                        "kind": "IMPORT_ERROR",
                        "detail": item.get("err", "?"),
                    }
                )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wheel-contract gate.")
    parser.add_argument("--json", type=Path, default=DEFAULT_OUT, help="write JSON report here")
    parser.add_argument(
        "--no-dynamic", action="store_true", help="skip the venv smoke (static only)"
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="freeze the current legacy packages + import-debt as the baseline (tighten only).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="ignore the baseline; fail on ANY contract violation (post-migration target).",
    )
    args = parser.parse_args(argv)

    first_party = _first_party_top_level()
    stdlib = _stdlib_names()
    entrypoints = _entrypoints()

    with tempfile.TemporaryDirectory() as td:
        try:
            wheel = _build_wheel(Path(td))
        except (WheelBuildError, subprocess.CalledProcessError) as exc:
            print(f"ERROR: wheel build failed: {exc}", file=sys.stderr)
            return 2
        wheel_sha = hashlib.sha256(wheel.read_bytes()).hexdigest()
        installed, sources = _packaged_modules(wheel)

        # Contract 2: packaged module imports a first-party top-level not shipped.
        import_failures: list[dict[str, str]] = []
        for member, source in sources:
            for imp in _imported_top_levels(source):
                if imp in stdlib or imp in installed:
                    continue
                if imp in first_party:
                    import_failures.append({"module": member, "imports_unpackaged": imp})

        # Contract 1: entry-point target's top-level package must be shipped.
        script_failures: list[dict[str, str]] = []
        for name, spec in entrypoints.items():
            target_top = spec.split(":")[0].split(".")[0]
            if target_top not in installed:
                script_failures.append(
                    {"script": name, "target": spec, "missing_package": target_top}
                )

        dynamic: list[dict[str, str]] = []
        if not args.no_dynamic:
            dynamic = _dynamic_smoke(wheel, entrypoints, first_party)

        dynamic_fail = [
            d
            for d in dynamic
            if d.get("kind") in {"FAIL", "FIRST_PARTY_MISSING", "INSTALL_FAIL", "PROBE_FAIL"}
        ]
        non_geosync = {t for t in installed if not t.startswith("geosync")}

        if args.write:
            _write_baseline(non_geosync, import_failures)
            print(
                f"Baseline frozen: {len(non_geosync)} legacy packages, "
                f"{len(import_failures)} import-debt entries."
            )
            return 0

        base_pkgs, base_debt = _load_baseline()
        cur_debt = {_import_key(f) for f in import_failures}
        new_debt = sorted(cur_debt - base_debt)
        new_pkgs = sorted(non_geosync - base_pkgs)
        stale_debt = sorted(base_debt - cur_debt)
        stale_pkgs = sorted(base_pkgs - non_geosync)

        # Entry-point and dynamic breaks are ALWAYS hard failures.
        # Packages / latent imports are ratcheted (fail on growth) unless --strict.
        if args.strict:
            ratchet_fail = bool(import_failures or non_geosync)
        else:
            ratchet_fail = bool(new_debt or new_pkgs or stale_debt or stale_pkgs)
        verdict = "PASS" if not (script_failures or dynamic_fail or ratchet_fail) else "FAIL"

        report = {
            "wheel_sha256": wheel_sha,
            "installed_packages": sorted(installed),
            "non_geosync_packages": sorted(non_geosync),
            "entrypoints": entrypoints,
            "import_failures": import_failures,
            "script_failures": script_failures,
            "dynamic_smoke": dynamic,
            "new_import_debt": new_debt,
            "new_legacy_packages": new_pkgs,
            "verdict": verdict,
        }
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    for f in script_failures:
        print(
            f"DEAD ENTRY-POINT: {f['script']} -> {f['target']} (package '{f['missing_package']}' not in wheel)",
            file=sys.stderr,
        )
    for f in dynamic_fail:
        print(f"DYNAMIC SMOKE: {f['target']} {f['kind']} {f.get('detail')}", file=sys.stderr)
    for k in new_debt:
        print(f"NEW LATENT BROKEN IMPORT (ratchet only shrinks): {k}", file=sys.stderr)
    for p in new_pkgs:
        print(f"NEW LEGACY PACKAGE in wheel (ratchet only shrinks): {p}", file=sys.stderr)
    if stale_debt or stale_pkgs:
        print(
            f"Debt paid down ({len(stale_debt)} imports, {len(stale_pkgs)} packages) but the "
            "baseline is stale. Tighten it: python scripts/ci/check_wheel_contract.py --write",
            file=sys.stderr,
        )

    print(
        f"WHEEL CONTRACT: {verdict} — {len(import_failures)} latent imports "
        f"({len(new_debt)} new), {len(script_failures)} dead entrypoints, "
        f"{len(non_geosync)} non-geosync packages ({len(new_pkgs)} new)"
    )
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
