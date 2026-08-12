"""Security reachability graph.

Static / semi-static reachability classifier for dependency advisories.
Distinguishes:

  declared          (in a manifest)
  locked            (pinned in a lockfile)
  imported          (used in a Python source file)
  used in runtime   (called by code reachable from a server entry-point)
  route mounted     (an HTTP / WS route exists)
  external surface  (the route is reachable from a network boundary)
  auth boundary     (a FastAPI dependency or middleware enforces authn)
  exploit confirmed (an integration / red-team test reproduced the path)

Reachability tiers (ordinal, ascending):

  UNUSED                    package not installed or imported
  PACKAGE_PRESENT           imported, but no runtime usage detected
  ROUTE_PRESENT             a route is mounted using the package
  AUTH_SURFACE_PRESENT      a route is mounted AND auth/dependency is wired
  EXPLOIT_PATH_CONFIRMED    a test reproduces the exploit (never set by
                            this static tool — only by a manual link to a
                            confirmed reproduction)

The classifier is deliberately CONSERVATIVE:

  - It does NOT promote a tier without source-level evidence.
  - It refuses to set EXPLOIT_PATH_CONFIRMED. That tier is reserved for
    the human-curated `confirmed_exploit_paths` block in the report —
    populated only by a runtime test that actually reproduced the
    advisory.

First-case wiring: strawberry-graphql / GraphQLRouter / /graphql, with a
link to issue #446 (the WS handshake authn follow-up).

The tool is stdlib + PyYAML only. Output is deterministic JSON.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Reachability tiers (ordered)
# ---------------------------------------------------------------------------
TIERS: tuple[str, ...] = (
    "UNUSED",
    "PACKAGE_PRESENT",
    "ROUTE_PRESENT",
    "AUTH_SURFACE_PRESENT",
    "EXPLOIT_PATH_CONFIRMED",
)


def _max_tier(*tiers: str) -> str:
    rank = {t: i for i, t in enumerate(TIERS)}
    return max(tiers, key=lambda t: rank.get(t, -1))


# ---------------------------------------------------------------------------
# Advisory inventory.
#
# This block is machine-curated by hand because:
#   (1) the reachability classifier is a structural tool, not a CVE feed
#   (2) we want every entry to carry an explicit followup_issue when the
#       reachability tier is below EXPLOIT_PATH_CONFIRMED
#
# Add new entries when an advisory needs reachability classification.
# Run pip-audit / osv-scanner separately for the full version inventory.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Advisory:
    advisory_id: str
    package_name: str
    fixed_version: str
    description: str
    affected_modules: tuple[str, ...]
    affected_constructs: tuple[str, ...]
    notes: str = ""


# Two seed advisories — strawberry-graphql GHSA-vpwc-v33q-mq89
# (auth bypass) and GHSA-hv3w-m4g2-5x77 (DoS). Both target the
# WebSocket subscription surface registered by GraphQLRouter.
SEED_ADVISORIES: tuple[Advisory, ...] = (
    Advisory(
        advisory_id="GHSA-vpwc-v33q-mq89",
        package_name="strawberry-graphql",
        fixed_version="0.312.3",
        description=("Authentication bypass via legacy graphql-ws WebSocket subprotocol"),
        affected_modules=("strawberry.fastapi",),
        affected_constructs=("GraphQLRouter",),
        notes="Triggered at WebSocket handshake; needs route + auth analysis.",
    ),
    Advisory(
        advisory_id="GHSA-hv3w-m4g2-5x77",
        package_name="strawberry-graphql",
        fixed_version="0.312.3",
        description="Denial of Service via unbounded WebSocket subscriptions",
        affected_modules=("strawberry.fastapi",),
        affected_constructs=("GraphQLRouter",),
        notes="Triggered after WS handshake; subscription operations.",
    ),
)


@dataclass(frozen=True)
class ReachabilityFact:
    package_name: str
    advisory_id: str
    locked_version: str | None
    fixed_version: str
    imported: bool
    runtime_route: bool
    websocket_surface: bool
    auth_boundary: str  # YES / NO / UNKNOWN
    exploit_path_confirmed: bool
    reachability: str
    evidence_paths: tuple[str, ...] = ()
    followup_issue: int | None = None
    notes: str = ""


@dataclass
class ReachabilityReport:
    facts: list[ReachabilityFact] = field(default_factory=list)
    confirmed_exploit_paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "facts": [asdict(f) for f in sorted(self.facts, key=lambda x: x.advisory_id)],
            "confirmed_exploit_paths": dict(self.confirmed_exploit_paths),
        }


# ---------------------------------------------------------------------------
# Static analysis helpers (line-grep level, deliberately simple)
# ---------------------------------------------------------------------------


def _lock_pin_for(repo_root: Path, package_name: str) -> str | None:
    """Look for `name==X.Y.Z` in the standard lockfiles."""
    for lock_name in ("requirements.lock", "requirements-dev.lock", "requirements-scan.lock"):
        path = repo_root / lock_name
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for raw in text.splitlines():
            stripped = raw.split("#", 1)[0].strip()
            if not stripped:
                continue
            m = re.match(
                r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]+\])?\s*==\s*([0-9][0-9A-Za-z.+\-_!]*)",
                stripped,
            )
            if m and m.group(1).lower() == package_name.lower():
                return m.group(2)
    return None


def _imports_of(repo_root: Path, modules: Iterable[str]) -> list[str]:
    """Return relative paths of source files that import any of `modules`.

    Skips `tools/`, `tests/`, `docs/`, and other non-runtime trees so the
    classifier counts only real runtime callers.
    """
    hits: list[str] = []
    skip_dirs = {
        ".venv",
        "node_modules",
        "__pycache__",
        "build",
        "dist",
        ".git",
        "tools",
        "tests",
        "docs",
        "scripts",
        "spikes",
        "benchmarks",
        "fixtures",
        "research",
        ".claude",
    }
    patterns = []
    for m in modules:
        # Match `from m`, `from m.x`, `import m`, `import m.x`
        patterns.append(re.compile(rf"^\s*(?:from|import)\s+{re.escape(m)}(?:\s|\.|$)", re.M))
    for path in sorted(repo_root.rglob("*.py")):
        if any(part in skip_dirs for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(p.search(text) for p in patterns):
            hits.append(str(path.relative_to(repo_root)))
    return hits


def _has_construct_usage(
    repo_root: Path, files: Iterable[str], constructs: Iterable[str]
) -> tuple[bool, tuple[str, ...]]:
    """Return (any_match, files_that_match)."""
    matched: list[str] = []
    pattern = re.compile(r"\b(" + "|".join(re.escape(c) for c in constructs) + r")\b")
    for f in files:
        path = repo_root / f
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if pattern.search(text):
            matched.append(f)
    return (bool(matched), tuple(matched))


def _has_websocket_surface(text: str) -> bool:
    return any(
        kw in text
        for kw in (
            "WebSocket",
            "websocket",
            "graphql-ws",
            "subscriptions_enabled",
            "SubscriptionProtocol",
        )
    ) or bool(re.search(r"\.websocket\(", text))


_AUTH_DEP_PATTERN = re.compile(
    r"Depends\s*\(\s*("
    r"enforce_[A-Za-z_]*?(?:auth|rate)[A-Za-z_]*"
    r"|require_[A-Za-z_]*?auth[A-Za-z_]*"
    r"|.*permission.*"
    r"|.*identity.*"
    r")\s*\)",
    re.IGNORECASE,
)


def _route_mount_evidence(
    repo_root: Path, files: Iterable[str], constructs: Iterable[str]
) -> dict[str, Any]:
    """Look for include_router(...) usage that mounts the construct.

    Two pass strategy:

      Pass A — direct: files that already use the construct AND call
               include_router in the same file.

      Pass B — factory-mediated: discover factory function names defined
               in the construct-using files (e.g. `create_graphql_router`),
               then scan ALL files for `include_router(<factory>(...))` or
               `include_router(<router_var>)` after a `<router_var> =
               <factory>(...)` assignment.

    Pass B fixes the case where the construct is wrapped in a factory
    (the GeoSync pattern: `application/api/graphql_api.py` defines
    `create_graphql_router` and `application/api/service.py` calls
    `app.include_router(graphql_router, ...)` after
    `graphql_router = create_graphql_router(...)`).
    """
    out: dict[str, Any] = {
        "mounted_in": [],
        "ws_surface": False,
        "auth_boundary": "UNKNOWN",
        "evidence": [],
    }
    construct_re = re.compile(r"\b(" + "|".join(re.escape(c) for c in constructs) + r")\b")
    include_re = re.compile(r"\binclude_router\s*\(")
    factory_re = re.compile(r"^\s*def\s+(create_[A-Za-z0-9_]*router[A-Za-z0-9_]*)\s*\(", re.M)

    files_set = set(files)

    # Pass A — direct.
    for f in sorted(files_set):
        path = repo_root / f
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not construct_re.search(text):
            continue
        if not include_re.search(text):
            continue
        out["mounted_in"].append(f)
        out["evidence"].append(f)
        if _has_websocket_surface(text):
            out["ws_surface"] = True
        if _AUTH_DEP_PATTERN.search(text):
            out["auth_boundary"] = "YES"
        elif "Depends(" in text:
            out["auth_boundary"] = "UNKNOWN"
        else:
            out["auth_boundary"] = "NO"

    # Pass B — factory-mediated. Find factory names first.
    factory_names: set[str] = set()
    for f in sorted(files_set):
        path = repo_root / f
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not construct_re.search(text):
            continue
        for m in factory_re.finditer(text):
            factory_names.add(m.group(1))

    if not factory_names:
        return out

    factory_use_re = re.compile(r"\b(" + "|".join(re.escape(fn) for fn in factory_names) + r")\b")

    skip_dirs = {
        ".venv",
        "node_modules",
        "__pycache__",
        "build",
        "dist",
        ".git",
        "tools",
        "tests",
        "docs",
        "scripts",
        "spikes",
        "benchmarks",
        "fixtures",
        "research",
        ".claude",
    }
    for path in sorted(repo_root.rglob("*.py")):
        if any(part in skip_dirs for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not factory_use_re.search(text):
            continue
        if not include_re.search(text):
            continue
        rel = str(path.relative_to(repo_root))
        if rel in out["mounted_in"]:
            continue
        out["mounted_in"].append(rel)
        out["evidence"].append(rel)
        if _has_websocket_surface(text):
            out["ws_surface"] = True
        # Auth boundary: prefer the strongest signal across all evidence
        # files. YES wins over UNKNOWN; UNKNOWN wins over NO.
        if _AUTH_DEP_PATTERN.search(text):
            out["auth_boundary"] = "YES"
        elif out["auth_boundary"] != "YES":
            out["auth_boundary"] = "UNKNOWN" if "Depends(" in text else "NO"
    return out


# ---------------------------------------------------------------------------
# Confirmed-exploit registry. Hand-curated. Empty by default.
# Add an entry only when a runtime test has actually reproduced the path.
# ---------------------------------------------------------------------------
CONFIRMED_EXPLOIT_PATHS: dict[str, str] = {
    # advisory_id -> path/to/the/test/that/reproduces/it
}


# ---------------------------------------------------------------------------
# Followup-issue registry. Hand-curated.
# ---------------------------------------------------------------------------
FOLLOWUP_ISSUES: dict[str, int] = {
    "GHSA-vpwc-v33q-mq89": 446,
    "GHSA-hv3w-m4g2-5x77": 446,
}


def classify(repo_root: Path, advisories: Iterable[Advisory]) -> ReachabilityReport:
    facts: list[ReachabilityFact] = []
    for adv in advisories:
        locked = _lock_pin_for(repo_root, adv.package_name)
        importing_files = _imports_of(repo_root, adv.affected_modules)
        used_in_files: tuple[str, ...] = ()
        used_match = False
        if importing_files:
            used_match, used_in_files = _has_construct_usage(
                repo_root, importing_files, adv.affected_constructs
            )

        # Tier resolution.
        tier = "UNUSED"
        if locked is not None or importing_files:
            tier = _max_tier(tier, "PACKAGE_PRESENT")

        route_data: dict[str, Any] = {
            "mounted_in": [],
            "ws_surface": False,
            "auth_boundary": "UNKNOWN",
            "evidence": [],
        }
        if used_match:
            route_data = _route_mount_evidence(repo_root, used_in_files, adv.affected_constructs)
            if route_data["mounted_in"]:
                tier = _max_tier(tier, "ROUTE_PRESENT")
                if route_data["auth_boundary"] in {"YES", "UNKNOWN"}:
                    # We promote to AUTH_SURFACE_PRESENT only when SOME
                    # evidence of an auth boundary exists; a confirmed YES
                    # AND a confirmed UNKNOWN both mean an auth dependency
                    # is wired. NO does not promote.
                    if route_data["auth_boundary"] == "YES":
                        tier = _max_tier(tier, "AUTH_SURFACE_PRESENT")

        confirmed = adv.advisory_id in CONFIRMED_EXPLOIT_PATHS
        if confirmed:
            tier = "EXPLOIT_PATH_CONFIRMED"

        evidence: list[str] = []
        evidence.extend(importing_files)
        evidence.extend(route_data["mounted_in"])

        facts.append(
            ReachabilityFact(
                package_name=adv.package_name,
                advisory_id=adv.advisory_id,
                locked_version=locked,
                fixed_version=adv.fixed_version,
                imported=bool(importing_files),
                runtime_route=bool(route_data["mounted_in"]),
                websocket_surface=bool(route_data["ws_surface"]),
                auth_boundary=route_data["auth_boundary"],
                exploit_path_confirmed=confirmed,
                reachability=tier,
                evidence_paths=tuple(sorted(set(evidence))),
                followup_issue=FOLLOWUP_ISSUES.get(adv.advisory_id),
                notes=adv.notes,
            )
        )

    return ReachabilityReport(
        facts=facts,
        confirmed_exploit_paths=dict(CONFIRMED_EXPLOIT_PATHS),
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Static reachability classifier for dependency advisories",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--exit-on-confirmed-exploit",
        action="store_true",
        help="exit non-zero if any advisory has reachability = EXPLOIT_PATH_CONFIRMED",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = classify(args.repo_root, SEED_ADVISORIES)
    payload = json.dumps(report.to_dict(), indent=2, sort_keys=True)
    if args.output is not None:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload)
    if args.exit_on_confirmed_exploit and any(f.exploit_path_confirmed for f in report.facts):
        print("FAIL: at least one confirmed exploit path", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
