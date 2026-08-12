"""Coverage honesty regression test.

Contract under test:

    A path under [run] omit MUST NOT erase a path declared under
    [run] source.

This is the structural form of the F02 closure. The companion detector
class (`C1` in `tools/audit/false_confidence_detector.py`) enforces the
same rule with structured findings; this test enforces it from the
opposite end (parses .coveragerc directly, asserts the file is honest).

Both checks block the same lie:

    "coverage number = real coverage"

If the lie returns (someone smuggles a `core/utils/**` back into [run]
omit), the test below fails AND C1 fires. Two independent witnesses.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COVERAGERC = REPO_ROOT / ".coveragerc"


def _parse_coveragerc_section(text: str, section: str, key: str) -> list[str]:
    """Return the list-valued entry for `section.key` from a .coveragerc.

    coverage.py uses INI semantics with newline-separated list values; the
    block below the `key =` line indents continuation entries.
    """
    lines = text.splitlines()
    in_section = False
    in_key = False
    out: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        # Strip ; and # comments to a separate variable so we don't lose
        # the leading-whitespace check below.
        if not stripped or stripped.startswith(";") or stripped.startswith("#"):
            continue
        # Section header.
        if re.match(r"^\[[^\]]+\]\s*$", stripped):
            in_section = stripped == f"[{section}]"
            in_key = False
            continue
        if not in_section:
            continue
        # Key line.
        if "=" in raw and raw.lstrip() == raw:
            this_key, _, value = raw.partition("=")
            if this_key.strip().lower() == key.lower():
                in_key = True
                v = value.strip()
                if v:
                    out.append(v)
            else:
                in_key = False
            continue
        if in_key:
            entry = stripped
            if entry:
                out.append(entry)
    return out


def _omit_erases_source(omit: str, sources: list[str]) -> bool:
    """An omit pattern erases declared source if its leading path
    component lies under a source root.

    Treat `**`-prefixed globs as global filters (they don't ERASE a
    specific source root — they apply uniformly).
    """
    head = omit.rstrip("/").rstrip("*").rstrip("/")
    if not head or head.startswith("**"):
        return False
    norm_sources = [s.rstrip("/").rstrip("*").rstrip("/") for s in sources]
    for src in norm_sources:
        if head == src:
            return True
        if head.startswith(src + "/"):
            return True
    return False


def test_coveragerc_exists() -> None:
    assert COVERAGERC.exists(), f".coveragerc not found at {COVERAGERC}"


def test_run_source_is_non_empty() -> None:
    text = COVERAGERC.read_text(encoding="utf-8")
    sources = _parse_coveragerc_section(text, "run", "source")
    assert sources, "[run] source must declare at least one path"


@pytest.mark.parametrize("section", ["run", "report"])
def test_no_omit_erases_declared_source(section: str) -> None:
    """The structural F02 contract.

    Holds for both [run] omit and [report] omit, because both must
    agree on what counts as source.
    """
    text = COVERAGERC.read_text(encoding="utf-8")
    sources = _parse_coveragerc_section(text, "run", "source")
    omits = _parse_coveragerc_section(text, section, "omit")
    erasing = [o for o in omits if _omit_erases_source(o, sources)]
    assert not erasing, (
        f"[{section}] omit erases declared source root(s) — F02 has "
        f"returned. Erasing patterns:\n  - "
        + "\n  - ".join(erasing)
        + f"\n\nDeclared source: {sources}\n"
        "If a sub-package is intentionally not measured by this profile, "
        "drop it from `source` instead of smuggling it into `omit`."
    )


def test_run_and_report_omit_agree() -> None:
    """Drift between [run] omit and [report] omit is its own honesty
    failure: a lie at report time."""
    text = COVERAGERC.read_text(encoding="utf-8")
    run_omit = sorted(_parse_coveragerc_section(text, "run", "omit"))
    report_omit = sorted(_parse_coveragerc_section(text, "report", "omit"))
    assert run_omit == report_omit, (
        "[run] omit and [report] omit must match exactly:\n"
        f"  in [run] only:    {sorted(set(run_omit) - set(report_omit))}\n"
        f"  in [report] only: {sorted(set(report_omit) - set(run_omit))}"
    )


def test_omit_only_targets_non_source_paths() -> None:
    """Every omit pattern must be either:
    - a non-source-root path (e.g. tests/**, conftest.py), OR
    - a global glob (**/...).

    No exceptions. If a sub-package needs exclusion, it leaves source —
    it does not get smuggled into omit.
    """
    text = COVERAGERC.read_text(encoding="utf-8")
    sources = _parse_coveragerc_section(text, "run", "source")
    omits = _parse_coveragerc_section(text, "run", "omit")
    bad = [o for o in omits if _omit_erases_source(o, sources)]
    assert not bad, f"omit erases declared source: {bad}"


# --------------------------------------------------------------------------- #
# The canonical RELEASE profile (release_90.coveragerc) must obey the same
# honesty contract as .coveragerc — it is the single authority for the 90 gate,
# so a lie smuggled into ITS omit is the higher-stakes lie.
# --------------------------------------------------------------------------- #
RELEASE_COVERAGERC = REPO_ROOT / "configs" / "quality" / "release_90.coveragerc"


def test_release_coveragerc_exists() -> None:
    assert RELEASE_COVERAGERC.exists(), "canonical release_90.coveragerc is missing"


def test_release_run_source_is_non_empty() -> None:
    text = RELEASE_COVERAGERC.read_text(encoding="utf-8")
    sources = _parse_coveragerc_section(text, "run", "source")
    assert sources, "release_90 [run] source must declare at least one path"


@pytest.mark.parametrize("section", ["run", "report"])
def test_release_no_omit_erases_declared_source(section: str) -> None:
    text = RELEASE_COVERAGERC.read_text(encoding="utf-8")
    sources = _parse_coveragerc_section(text, "run", "source")
    omits = _parse_coveragerc_section(text, section, "omit")
    erasing = [o for o in omits if _omit_erases_source(o, sources)]
    assert not erasing, (
        f"release_90 [{section}] omit erases declared source — the canonical "
        f"profile must not lie.\n  source: {sources}\n  erasing omit: {erasing}"
    )


def test_release_run_and_report_omit_agree() -> None:
    text = RELEASE_COVERAGERC.read_text(encoding="utf-8")
    run_omit = sorted(_parse_coveragerc_section(text, "run", "omit"))
    report_omit = sorted(_parse_coveragerc_section(text, "report", "omit"))
    assert run_omit == report_omit, (
        "release_90 [run] omit and [report] omit must match exactly:\n"
        f"  in [run] only:    {sorted(set(run_omit) - set(report_omit))}\n"
        f"  in [report] only: {sorted(set(report_omit) - set(run_omit))}"
    )
