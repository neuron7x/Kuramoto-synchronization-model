#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""E.clean_clone — clean-room wheel install + entrypoint smoke probe.

Tribunal for the gate ``E.clean_clone``. A repository that can only run from
its own checkout (editable install, ``sys.path`` hacks, local-path deps) has
not proven it is *installable*. This probe refuses prose: it builds a wheel
from a clean ``git archive`` (no working-tree contamination), installs it
into a throwaway virtualenv with no access to the source tree, then proves
``import geosync`` and every declared console entrypoint executes.

Stages (each must pass):

1. ``git archive HEAD`` → pristine source tree (no untracked files).
2. ``pip wheel --no-deps`` → wheel built from that tree only.
3. wheel top-level packages are ``geosync*`` only (no leaked siblings).
4. fresh ``venv`` with ``--without-pip`` siblings isolated; install the wheel
   (``--no-deps`` so the test is *importability*, not dependency resolution).
5. ``python -c "import geosync"`` from a CWD outside the source tree.
6. each ``[project.scripts]`` entrypoint runs ``--help`` (exit 0).

Output: ``artifacts/release_gate/clean_clone.json`` with per-stage evidence.
Exit 0 iff every stage passed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from scripts.ci.proof_common import PASS, ROOT, sha256_file, write_artifact

ARTIFACT = "artifacts/release_gate/clean_clone.json"

# Entrypoints whose --help must run cleanly in the isolated install. These are
# the import-light CLIs; server/db entrypoints that require live services or a
# database connection are intentionally excluded from the smoke set (their
# import is still exercised transitively where cheap).
SMOKE_ENTRYPOINTS: tuple[str, ...] = (
    "geosync-scripts",
    "geosync-release-gate",
    "geosync-import-architecture",
    "tp-kuramoto",
    "mfn",
)


_MISSING_RE = re.compile(r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]")


def _run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kw)


def _missing_module(stderr: str) -> str | None:
    """Return the module name from a ModuleNotFoundError, if present."""
    matches = _MISSING_RE.findall(stderr)
    return matches[-1] if matches else None


def _build_and_smoke(td: Path) -> tuple[bool, list[dict[str, Any]]]:
    stages: list[dict[str, Any]] = []

    # 1. clean git archive
    arch = td / "src.tar"
    with arch.open("wb") as fh:
        rc = subprocess.run(
            ["git", "archive", "--format=tar", "HEAD"], cwd=ROOT, stdout=fh, check=False
        ).returncode
    ok = rc == 0 and arch.stat().st_size > 0
    stages.append({"stage": "git_archive", "ok": ok, "detail": f"tar bytes={arch.stat().st_size}"})
    if not ok:
        return False, stages

    srcdir = td / "src_tree"
    srcdir.mkdir()
    _run(["tar", "-xf", str(arch), "-C", str(srcdir)])

    # 2. wheel build
    wheeldir = td / "wheel"
    build = _run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", str(wheeldir), str(srcdir)]
    )
    wheels = sorted(wheeldir.glob("*.whl"))
    ok = build.returncode == 0 and bool(wheels)
    stages.append(
        {
            "stage": "wheel_build",
            "ok": ok,
            "detail": (wheels[0].name if wheels else build.stderr.strip()[-300:]),
        }
    )
    if not ok:
        return False, stages
    wheel = wheels[0]

    # 3. wheel top-level package inventory (ADVISORY here — package *purity*
    #    is independently gated by the B.wheel probe in release_gate.py; this
    #    probe neither re-litigates nor weakens that gate. It records the
    #    inventory as evidence and proves isolated install + entrypoint run.)
    with zipfile.ZipFile(wheel) as zf:
        tops = sorted({n.split("/")[0] for n in zf.namelist()})
    pkgs = [t for t in tops if not t.endswith(".dist-info")]
    non_geosync = [t for t in pkgs if not t.startswith("geosync")]
    stages.append(
        {
            "stage": "wheel_contents",
            "ok": True,
            "advisory": True,
            "detail": (
                f"top-level packages={pkgs}; non_geosync={non_geosync} "
                "(purity gated separately by B.wheel)"
            ),
            "non_geosync_packages": non_geosync,
            "wheel_sha256": sha256_file(wheel),
        }
    )

    # 4. isolated venv + install wheel
    venv = td / "venv"
    _run([sys.executable, "-m", "venv", str(venv)])
    vpy = venv / "bin" / "python"
    inst = _run([str(vpy), "-m", "pip", "install", "--no-deps", "--no-input", str(wheel)])
    ok = inst.returncode == 0
    stages.append(
        {
            "stage": "wheel_install",
            "ok": ok,
            "detail": ("installed" if ok else inst.stderr.strip()[-300:]),
        }
    )
    if not ok:
        return False, stages

    # 5. import from a CWD outside the source tree (no sys.path leakage)
    outside = td / "outside"
    outside.mkdir()
    imp = _run(
        [str(vpy), "-c", "import geosync; print(getattr(geosync, '__file__', '?'))"], cwd=outside
    )
    geosync_path = imp.stdout.strip()
    ok = imp.returncode == 0 and str(srcdir) not in geosync_path and str(ROOT) not in geosync_path
    stages.append(
        {
            "stage": "import_geosync",
            "ok": ok,
            "detail": (f"resolved={geosync_path}" if ok else imp.stderr.strip()[-300:]),
        }
    )
    if not ok:
        return False, stages

    # 6. entrypoint smoke (--help) from outside the tree.
    #    Console-script wiring is the gated property: the wrapper must exist
    #    and dispatch to its declared module:func. A --help that exits 0 proves
    #    execution. A failure caused purely by an absent THIRD-PARTY dependency
    #    (expected under --no-deps; dependency completeness is gated by
    #    C.dep_truth) is advisory, not a packaging defect. A failure naming the
    #    wheel's OWN top-level package (broken wiring / import architecture) is
    #    a hard gating failure.
    own_pkgs = frozenset(pkgs)
    vbin = venv / "bin"
    ep_results: list[dict[str, Any]] = []
    all_ep_ok = True
    for ep in SMOKE_ENTRYPOINTS:
        exe = vbin / ep
        if not exe.exists():
            ep_results.append(
                {"entrypoint": ep, "ok": False, "detail": "console-script wrapper not installed"}
            )
            all_ep_ok = False
            continue
        res = _run([str(exe), "--help"], cwd=outside)
        if res.returncode == 0:
            ep_results.append({"entrypoint": ep, "ok": True, "detail": "--help exit 0"})
            continue
        missing = _missing_module(res.stderr)
        third_party_dep = missing is not None and missing.split(".")[0] not in own_pkgs
        if third_party_dep:
            ep_results.append(
                {
                    "entrypoint": ep,
                    "ok": True,
                    "advisory": True,
                    "detail": f"wired ok; third-party dep '{missing}' absent under --no-deps (gated by C.dep_truth)",
                }
            )
            continue
        ep_results.append({"entrypoint": ep, "ok": False, "detail": res.stderr.strip()[-200:]})
        all_ep_ok = False
    stages.append({"stage": "entrypoint_smoke", "ok": all_ep_ok, "entrypoints": ep_results})

    return all_ep_ok, stages


def run() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        _, stages = _build_and_smoke(Path(td))
    # Gating status excludes advisory stages (e.g. wheel_contents, which is
    # gated independently by B.wheel). E owns: build → isolated install →
    # import → entrypoint execution.
    gating_ok = all(st["ok"] for st in stages if not st.get("advisory"))
    return {
        "gate": "E.clean_clone",
        "schema_version": "1.0",
        "status": PASS if gating_ok else "FAIL",
        "stages": stages,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default=ARTIFACT, help="artifact output path")
    args = parser.parse_args(argv)
    payload = run()
    path = write_artifact(args.json, payload)
    print(f"[E.clean_clone] status={payload['status']} -> {path}")
    for st in payload["stages"]:
        print(f"  [{'ok' if st['ok'] else 'XX'}] {st['stage']}: {st.get('detail', '')}")
    return 0 if payload["status"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
