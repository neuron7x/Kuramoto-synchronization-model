#!/usr/bin/env python3
"""Version single-source-of-truth (SSOT) consistency gate — REL-008.

The canonical version string is declared once, in the repository-root ``VERSION``
file. Every other version-bound surface MUST carry the *identical* string:

  * ``VERSION``                         — the SSOT (source of the canonical value)
  * ``CITATION.cff`` ``version:``       — academic citation metadata
  * ``CITATION.cff`` ``preferred-citation.version:``
  * ``pyproject.toml`` ``[tool.setuptools_scm] fallback_version``
        — the wheel/CLI ``--version`` derivation mechanism. setuptools_scm
          derives the distribution version dynamically from git tags; when no
          version tag is reachable from HEAD this fallback governs the wheel
          version, so it must equal the SSOT.
  * ``CHANGELOG.md``                    — a ``## [<version>]`` release heading
        must exist (historical entries are preserved and ignored).

The release git tag ``v<version>`` is the *true* dynamic source of the wheel
version via setuptools_scm; it is reported as an advisory surface (not a
hard-fail, because CI checkouts may be shallow / tag-less), while the file
surfaces above are enforced fail-closed.

Exit codes:
    0  every enforced surface matches the SSOT.
    1  any mismatch, missing surface, or unreadable/absent SSOT (fail-closed).

Usage:
    python scripts/ci/check_version_ssot.py [--repo-root PATH] [--quiet]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import NamedTuple

# A conservative PEP440-ish core version: MAJOR.MINOR.PATCH with optional
# pre/post/dev suffix. Kept strict enough to reject obvious garbage.
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[.\-+][0-9A-Za-z.\-+]+)?$")


class SurfaceResult(NamedTuple):
    """Outcome of checking one version-bound surface."""

    name: str
    found: str | None
    ok: bool
    detail: str


def _repo_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    # scripts/ci/check_version_ssot.py -> repo root is two parents up.
    return Path(__file__).resolve().parents[2]


def read_canonical_version(root: Path) -> str:
    """Read the canonical version from the SSOT (VERSION file). Fail-closed."""
    version_file = root / "VERSION"
    if not version_file.exists():
        raise FileNotFoundError(f"SSOT missing: {version_file} does not exist")
    raw = version_file.read_text(encoding="utf-8").strip()
    if not raw:
        raise ValueError(f"SSOT empty: {version_file} contains no version string")
    if not _VERSION_RE.match(raw):
        raise ValueError(
            f"SSOT malformed: {version_file} = {raw!r} is not a valid version"
        )
    return raw


def _check_citation(root: Path, canonical: str) -> list[SurfaceResult]:
    """Check both `version:` and `preferred-citation.version:` in CITATION.cff.

    Parsed line-wise (no YAML dependency required) so the gate stays
    dependency-light and robust to the exact CFF structure.
    """
    path = root / "CITATION.cff"
    results: list[SurfaceResult] = []
    if not path.exists():
        return [
            SurfaceResult("CITATION.cff", None, False, f"missing file: {path}"),
        ]
    text = path.read_text(encoding="utf-8")
    # Top-level `version:` (indentation == 0). Preferred-citation nests it
    # under indentation, so match a strictly non-indented key for the primary
    # surface and any indented one for the preferred-citation surface.
    top = re.search(r"(?m)^version:\s*[\"']?([^\"'\n]+?)[\"']?\s*$", text)
    nested = re.findall(r"(?m)^[ \t]+version:\s*[\"']?([^\"'\n]+?)[\"']?\s*$", text)

    top_val = top.group(1).strip() if top else None
    results.append(
        SurfaceResult(
            "CITATION.cff:version",
            top_val,
            top_val == canonical,
            "top-level version" if top_val else "no top-level `version:` key",
        )
    )
    if nested:
        pref_val = nested[0].strip()
        results.append(
            SurfaceResult(
                "CITATION.cff:preferred-citation.version",
                pref_val,
                pref_val == canonical,
                "preferred-citation.version",
            )
        )
    else:
        results.append(
            SurfaceResult(
                "CITATION.cff:preferred-citation.version",
                None,
                False,
                "no nested `version:` (preferred-citation) key",
            )
        )
    return results


def _check_scm_fallback(root: Path, canonical: str) -> SurfaceResult:
    path = root / "pyproject.toml"
    if not path.exists():
        return SurfaceResult(
            "pyproject:setuptools_scm.fallback_version",
            None,
            False,
            f"missing file: {path}",
        )
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    fallback = (
        data.get("tool", {}).get("setuptools_scm", {}).get("fallback_version")
    )
    return SurfaceResult(
        "pyproject:setuptools_scm.fallback_version",
        fallback,
        fallback == canonical,
        "wheel/CLI version derivation fallback",
    )


def _check_changelog(root: Path, canonical: str) -> SurfaceResult:
    path = root / "CHANGELOG.md"
    if not path.exists():
        return SurfaceResult(
            "CHANGELOG.md:heading", None, False, f"missing file: {path}"
        )
    text = path.read_text(encoding="utf-8")
    # Match a Keep-a-Changelog release heading `## [<version>]` for the exact
    # canonical version. Historical headings for other versions are ignored.
    pattern = re.compile(
        r"(?m)^##\s*\[" + re.escape(canonical) + r"\]",
    )
    found = pattern.search(text) is not None
    return SurfaceResult(
        "CHANGELOG.md:heading",
        canonical if found else None,
        found,
        f"`## [{canonical}]` release heading",
    )


def _advisory_git_tag(root: Path, canonical: str) -> SurfaceResult:
    """Advisory (non-fatal) check that the release tag `v<version>` exists."""
    tag = f"v{canonical}"
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "tag", "--list", tag],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        return SurfaceResult(
            "git-tag(advisory)", None, True, f"git unavailable: {exc}"
        )
    present = out.returncode == 0 and tag in out.stdout.split()
    return SurfaceResult(
        "git-tag(advisory)",
        tag if present else None,
        True,  # advisory — never fails the gate
        (
            f"release tag {tag} present (true dynamic scm source)"
            if present
            else f"release tag {tag} NOT reachable in this checkout "
            "(advisory only; fallback_version governs the wheel here)"
        ),
    )


def check(root: Path) -> tuple[str, list[SurfaceResult]]:
    """Return (canonical_version, per-surface results including advisory)."""
    canonical = read_canonical_version(root)
    results: list[SurfaceResult] = [
        SurfaceResult("VERSION(SSOT)", canonical, True, "canonical source"),
    ]
    results.extend(_check_citation(root, canonical))
    results.append(_check_scm_fallback(root, canonical))
    results.append(_check_changelog(root, canonical))
    results.append(_advisory_git_tag(root, canonical))
    return canonical, results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=None, help="repository root path")
    parser.add_argument("--quiet", action="store_true", help="only print on failure")
    args = parser.parse_args(argv)

    root = _repo_root(args.repo_root)
    try:
        canonical, results = check(root)
    except (FileNotFoundError, ValueError) as exc:
        print(f"VERSION-SSOT FAIL: {exc}", file=sys.stderr)
        return 1

    # Advisory surfaces never fail the gate.
    enforced = [r for r in results if not r.name.endswith("(advisory)")]
    failures = [r for r in enforced if not r.ok]

    if not args.quiet or failures:
        print(f"Canonical version (SSOT VERSION file): {canonical}")
        for r in results:
            mark = "OK " if r.ok else "XX "
            shown = r.found if r.found is not None else "<absent>"
            print(f"  [{mark}] {r.name:<45} = {shown!s:<12} ({r.detail})")

    if failures:
        names = ", ".join(r.name for r in failures)
        print(
            f"VERSION-SSOT FAIL: {len(failures)} surface(s) diverge from "
            f"canonical {canonical!r}: {names}",
            file=sys.stderr,
        )
        return 1

    if not args.quiet:
        print(f"VERSION-SSOT OK: all {len(enforced)} bound surfaces == {canonical}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
