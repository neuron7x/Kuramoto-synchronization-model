"""Tests for the security reachability graph.

Three contracts:

1. The shipping classifier reports the correct seed result for the
   strawberry-graphql / GraphQLRouter / /graphql case (the F03
   reachability follow-up tracked in issue #446).

2. Each tier promotion happens on the right synthetic input, and NOT on
   inputs that lack the structural signal. Specifically: a package that is
   only `PACKAGE_PRESENT` does not get promoted to `EXPLOIT_PATH_CONFIRMED`
   without a hand-curated entry in `CONFIRMED_EXPLOIT_PATHS`.

3. Output is deterministic JSON; CLI exits zero in report-only mode.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from textwrap import dedent
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPO_ROOT / "tools" / "security" / "reachability_graph.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("rg", TOOL_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["rg"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rg() -> ModuleType:
    return _load()


# ---------------------------------------------------------------------------
# Contract 1 — first-case wiring (strawberry / GraphQLRouter / /graphql)
# ---------------------------------------------------------------------------


def test_seed_advisories_present(rg: ModuleType) -> None:
    seeds = list(rg.SEED_ADVISORIES)
    assert any(a.advisory_id == "GHSA-vpwc-v33q-mq89" for a in seeds)
    assert any(a.advisory_id == "GHSA-hv3w-m4g2-5x77" for a in seeds)
    for a in seeds:
        assert "GraphQLRouter" in a.affected_constructs
        assert "strawberry.fastapi" in a.affected_modules


def test_live_repo_classifies_strawberry_at_least_route_present(
    rg: ModuleType,
) -> None:
    """The /graphql route IS mounted in this codebase. The classifier
    must surface that, not stop at PACKAGE_PRESENT."""
    report = rg.classify(REPO_ROOT, rg.SEED_ADVISORIES)
    sb = [f for f in report.facts if f.package_name == "strawberry-graphql"]
    assert sb, "no strawberry-graphql facts produced"
    rank = {t: i for i, t in enumerate(rg.TIERS)}
    for f in sb:
        assert (
            rank[f.reachability] >= rank["ROUTE_PRESENT"]
        ), f"{f.advisory_id}: tier {f.reachability} below ROUTE_PRESENT"
        assert f.imported is True
        assert f.runtime_route is True
        assert f.followup_issue == 446
        assert f.locked_version is not None


def test_live_repo_does_not_falsely_confirm_exploit(rg: ModuleType) -> None:
    """No advisory may carry exploit_path_confirmed=True without an entry
    in CONFIRMED_EXPLOIT_PATHS."""
    report = rg.classify(REPO_ROOT, rg.SEED_ADVISORIES)
    for f in report.facts:
        if f.exploit_path_confirmed:
            assert (
                f.advisory_id in rg.CONFIRMED_EXPLOIT_PATHS
            ), f"{f.advisory_id}: marked confirmed, but no entry in CONFIRMED_EXPLOIT_PATHS"


# ---------------------------------------------------------------------------
# Contract 2 — tier mechanics on synthetic trees
# ---------------------------------------------------------------------------


def _seed_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "application" / "api").mkdir(parents=True)
    (repo / "requirements.lock").write_text("", encoding="utf-8")
    (repo / "requirements-dev.lock").write_text("", encoding="utf-8")
    (repo / "requirements-scan.lock").write_text("", encoding="utf-8")
    return repo


def _make_advisory(rg: ModuleType, **overrides: object) -> object:
    base: dict[str, object] = {
        "advisory_id": "GHSA-test",
        "package_name": "testpkg",
        "fixed_version": "1.0.0",
        "description": "test",
        "affected_modules": ("testpkg.fastapi",),
        "affected_constructs": ("TestRouter",),
        "notes": "",
    }
    base.update(overrides)
    return rg.Advisory(**base)


def test_tier_unused_when_no_import(rg: ModuleType, tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    adv = _make_advisory(rg)
    facts = rg.classify(repo, [adv]).facts
    assert facts[0].reachability == "UNUSED"


def test_tier_package_present_when_imported_only(rg: ModuleType, tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    (repo / "application" / "api" / "x.py").write_text(
        "from testpkg.fastapi import TestRouter  # noqa: F401\n",
        encoding="utf-8",
    )
    adv = _make_advisory(rg)
    facts = rg.classify(repo, [adv]).facts
    # Imported but no include_router / factory ⇒ PACKAGE_PRESENT
    assert facts[0].reachability == "PACKAGE_PRESENT"
    assert facts[0].imported is True
    assert facts[0].runtime_route is False


def test_tier_route_present_when_factory_mounted(rg: ModuleType, tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    (repo / "application" / "api" / "x.py").write_text(
        dedent("""
            from testpkg.fastapi import TestRouter

            def create_test_router():
                return TestRouter()
            """),
        encoding="utf-8",
    )
    (repo / "application" / "api" / "service.py").write_text(
        dedent("""
            from application.api.x import create_test_router

            def setup(app):
                router = create_test_router()
                app.include_router(router, prefix="/test")
            """),
        encoding="utf-8",
    )
    adv = _make_advisory(rg)
    facts = rg.classify(repo, [adv]).facts
    assert facts[0].runtime_route is True
    assert facts[0].reachability in {"ROUTE_PRESENT", "AUTH_SURFACE_PRESENT"}


def test_tier_auth_surface_present_when_auth_wired(rg: ModuleType, tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    (repo / "application" / "api" / "x.py").write_text(
        dedent("""
            from testpkg.fastapi import TestRouter

            def create_test_router():
                return TestRouter()
            """),
        encoding="utf-8",
    )
    (repo / "application" / "api" / "service.py").write_text(
        dedent("""
            from fastapi import Depends
            from application.api.x import create_test_router

            def enforce_auth():
                ...

            def setup(app):
                router = create_test_router()
                app.include_router(
                    router,
                    prefix="/test",
                    dependencies=[Depends(enforce_auth)],
                )
            """),
        encoding="utf-8",
    )
    adv = _make_advisory(rg)
    facts = rg.classify(repo, [adv]).facts
    # Auth dependency wired ⇒ AUTH_SURFACE_PRESENT
    assert facts[0].reachability == "AUTH_SURFACE_PRESENT"
    assert facts[0].auth_boundary == "YES"


def test_no_promotion_to_exploit_confirmed_without_entry(rg: ModuleType, tmp_path: Path) -> None:
    """Even when route + auth + everything is set, the static classifier
    must NOT promote to EXPLOIT_PATH_CONFIRMED without a hand-curated entry."""
    repo = _seed_repo(tmp_path)
    (repo / "application" / "api" / "x.py").write_text(
        dedent("""
            from testpkg.fastapi import TestRouter

            def create_test_router():
                return TestRouter()
            """),
        encoding="utf-8",
    )
    (repo / "application" / "api" / "service.py").write_text(
        dedent("""
            from fastapi import Depends
            from application.api.x import create_test_router

            def enforce_auth():
                ...

            def setup(app):
                router = create_test_router()
                app.include_router(
                    router, prefix="/test",
                    dependencies=[Depends(enforce_auth)],
                )
            """),
        encoding="utf-8",
    )
    adv = _make_advisory(rg)
    facts = rg.classify(repo, [adv]).facts
    assert facts[0].exploit_path_confirmed is False
    assert facts[0].reachability != "EXPLOIT_PATH_CONFIRMED"


# ---------------------------------------------------------------------------
# Contract 3 — output determinism + CLI
# ---------------------------------------------------------------------------


def test_classify_is_deterministic(rg: ModuleType) -> None:
    a = rg.classify(REPO_ROOT, rg.SEED_ADVISORIES).to_dict()
    b = rg.classify(REPO_ROOT, rg.SEED_ADVISORIES).to_dict()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_main_exits_zero_in_report_only_mode(rg: ModuleType) -> None:
    rc = rg.main(["--repo-root", str(REPO_ROOT)])
    assert rc == 0


def test_main_exits_nonzero_when_a_path_is_confirmed(
    rg: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When `CONFIRMED_EXPLOIT_PATHS` carries an entry AND the
    --exit-on-confirmed-exploit flag is passed, the CLI exits non-zero.
    Verifies the classifier honours the explicit confirmed-exploit signal.
    """
    monkeypatch.setitem(
        rg.CONFIRMED_EXPLOIT_PATHS,
        "GHSA-vpwc-v33q-mq89",
        "tests/integration/_synthetic.py",
    )
    rc = rg.main(["--repo-root", str(REPO_ROOT), "--exit-on-confirmed-exploit"])
    assert rc == 1
