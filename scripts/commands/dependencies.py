"""CLI surface for dependency management workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from scripts.commands.base import CommandError, register
from scripts.dependency_management import (
    DependencyRepository,
    LicensePolicy,
    LicensePolicyError,
    Lockfile,
    PackageChangeReport,
    SemverPolicy,
    compare_lockfiles,
    detect_vulnerabilities,
    evaluate_license_compliance,
    find_duplicate_dependencies,
    generate_lockfile,
    generate_restore_plan,
    plan_constrained_updates,
    prune_lockfile,
    render_dependency_graph,
    build_compatibility_matrix,
)

DEFAULT_REQUIREMENTS = (Path("requirements.txt"),)


def build_parser(subparsers: "argparse._SubParsersAction[object]") -> None:
    parser = subparsers.add_parser(
        "dependencies",
        help="Manage dependency metadata, lock files, and compliance workflows.",
    )
    parser.set_defaults(command="dependencies", handler=handle)
    parser.add_argument("--metadata", type=Path, default=None, help="Repository metadata JSON file.")
    parser.add_argument("--cache", type=Path, default=None, help="Optional on-disk metadata cache.")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Operate strictly from cached metadata (disables network access).",
    )

    actions = parser.add_subparsers(dest="action", required=True)

    lock = actions.add_parser("lock", help="Generate a lock file from requirement inputs.")
    lock.add_argument(
        "--requirements",
        action="append",
        type=Path,
        help="Requirement file(s) to resolve. Defaults to requirements.txt when omitted.",
    )
    lock.add_argument("--output", type=Path, required=True, help="Destination lock file path.")

    dup = actions.add_parser("check-duplicates", help="Detect duplicate dependencies in a lock file.")
    dup.add_argument("--lockfile", type=Path, required=True, help="Lock file to inspect.")

    updates = actions.add_parser("plan-updates", help="Suggest updates that satisfy the semantic policy.")
    updates.add_argument("--lockfile", type=Path, required=True)
    updates.add_argument(
        "--policy",
        choices=("patch", "minor", "major"),
        default="patch",
        help="Strictness for allowed upgrades.",
    )

    graph = actions.add_parser("graph", help="Render the dependency graph in DOT format.")
    graph.add_argument("--lockfile", type=Path, required=True)
    graph.add_argument("--output", type=Path, default=None, help="Write DOT output to the given file.")

    vuln = actions.add_parser("vulnerabilities", help="List known vulnerabilities for locked dependencies.")
    vuln.add_argument("--lockfile", type=Path, required=True)

    lic = actions.add_parser("licenses", help="Validate license compliance for the lock file.")
    lic.add_argument("--lockfile", type=Path, required=True)
    lic.add_argument("--policy", type=Path, required=True, help="License policy JSON document.")

    prune = actions.add_parser("prune", help="Remove unused packages from a lock file.")
    prune.add_argument("--lockfile", type=Path, required=True)
    prune.add_argument(
        "--keep",
        action="append",
        required=True,
        help="Package(s) that should remain in the lock file (repeatable).",
    )
    prune.add_argument("--output", type=Path, required=True)

    restore = actions.add_parser("restore", help="Emit commands to restore an environment from a lock file.")
    restore.add_argument("--lockfile", type=Path, required=True)
    restore.add_argument("--python", default="python", help="Python executable to use for pip installs.")

    compatibility = actions.add_parser("compatibility", help="Build a Python version compatibility matrix.")
    compatibility.add_argument("--lockfile", type=Path, required=True)
    compatibility.add_argument(
        "--python-version",
        action="append",
        required=True,
        help="Python version(s) to evaluate (repeatable).",
    )

    report = actions.add_parser("report-changes", help="Compare two lock files and report package changes.")
    report.add_argument("--old", type=Path, required=True)
    report.add_argument("--new", type=Path, required=True)
    report.add_argument("--output", type=Path, default=None)


def _load_repository(args: argparse.Namespace) -> DependencyRepository:
    metadata_path: Path | None = getattr(args, "metadata", None)
    cache_path: Path | None = getattr(args, "cache", None)
    offline: bool = bool(getattr(args, "offline", False))
    if metadata_path:
        return DependencyRepository.from_json(metadata_path, cache_path=cache_path, offline=offline)
    return DependencyRepository(cache_path=cache_path, offline=offline)


def _read_requirements(paths: Iterable[Path]) -> list[str]:
    requirements: list[str] = []
    for path in paths:
        if not path.exists():
            raise CommandError(f"Requirement file '{path}' does not exist")
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            requirements.append(line)
    return requirements


def _resolve_policy(name: str) -> SemverPolicy:
    if name == "major":
        return SemverPolicy(allow_major=True, allow_minor=True, allow_patch=True)
    if name == "minor":
        return SemverPolicy(allow_major=False, allow_minor=True, allow_patch=True)
    return SemverPolicy()


@register("dependencies")
def handle(args: argparse.Namespace) -> int:
    action = getattr(args, "action")
    if action == "lock":
        repository = _load_repository(args)
        requirement_paths = args.requirements if args.requirements else list(DEFAULT_REQUIREMENTS)
        requirements = _read_requirements(requirement_paths)
        lockfile = generate_lockfile(requirements, repository)
        lockfile.write(args.output)
        print(f"✅ Wrote lock file to {args.output}")
        return 0

    if action == "check-duplicates":
        lockfile = Lockfile.load(args.lockfile)
        duplicates = find_duplicate_dependencies(lockfile)
        if not duplicates:
            print("✅ No duplicate dependencies detected.")
            return 0
        print("❌ Duplicate dependencies detected:")
        for name in duplicates:
            print(f"  - {name}")
        return 1

    if action == "plan-updates":
        repository = _load_repository(args)
        lockfile = Lockfile.load(args.lockfile)
        policy = _resolve_policy(args.policy)
        plans = plan_constrained_updates(lockfile, repository, policy=policy)
        if not plans:
            print("✅ Lock file is up to date for the configured policy.")
            return 0
        for plan in plans:
            print(
                f"📦 {plan.name}: {plan.current_version} → {plan.target_version} ({plan.reason})"
            )
        return 0

    if action == "graph":
        lockfile = Lockfile.load(args.lockfile)
        dot = render_dependency_graph(lockfile)
        if args.output:
            args.output.write_text(dot, encoding="utf-8")
            print(f"🧭 Wrote graph to {args.output}")
        else:
            print(dot)
        return 0

    if action == "vulnerabilities":
        repository = _load_repository(args)
        lockfile = Lockfile.load(args.lockfile)
        findings = detect_vulnerabilities(lockfile, repository)
        if not findings:
            print("✅ No known vulnerabilities for locked dependencies.")
            return 0
        for finding in findings:
            advisory = finding.advisory
            fixes = ", ".join(advisory.fix_versions) or "no patched versions"
            print(
                f"⚠️  {finding.name}=={finding.version}: {advisory.identifier} ({advisory.severity}) → fix: {fixes}"
            )
        return 1

    if action == "licenses":
        repository = _load_repository(args)
        lockfile = Lockfile.load(args.lockfile)
        try:
            payload = json.loads(args.policy.read_text(encoding="utf-8"))
            policy = LicensePolicy.from_dict(payload)
        except (json.JSONDecodeError, LicensePolicyError) as exc:
            raise CommandError(f"Failed to load license policy: {exc}") from exc
        issues = evaluate_license_compliance(lockfile, repository, policy)
        if not issues:
            print("✅ All licenses comply with policy.")
            return 0
        for issue in issues:
            licenses = ", ".join(issue.licenses)
            print(
                f"❌ {issue.dependency.name}=={issue.dependency.version}: {licenses} → {issue.classification}"
            )
        return 1

    if action == "prune":
        lockfile = Lockfile.load(args.lockfile)
        pruned = prune_lockfile(lockfile, args.keep)
        pruned.write(args.output)
        print(f"🧹 Wrote pruned lock file to {args.output}")
        return 0

    if action == "restore":
        lockfile = Lockfile.load(args.lockfile)
        commands = generate_restore_plan(lockfile, python_executable=args.python)
        for command in commands:
            print(command)
        return 0

    if action == "compatibility":
        repository = _load_repository(args)
        lockfile = Lockfile.load(args.lockfile)
        matrix = build_compatibility_matrix(lockfile, repository, args.python_version)
        for package, compat in matrix.items():
            statuses = ", ".join(f"{version}:{'✅' if supported else '❌'}" for version, supported in compat.items())
            print(f"{package}: {statuses}")
        return 0

    if action == "report-changes":
        old = Lockfile.load(args.old)
        new = Lockfile.load(args.new)
        report = compare_lockfiles(old, new)
        payload = report.to_dict()
        if args.output:
            args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(f"🗒️  Wrote change report to {args.output}")
        else:
            _print_change_report(report)
        return 0

    raise CommandError(f"Unknown dependencies action '{action}'")


def _print_change_report(report: PackageChangeReport) -> None:
    def _print_group(title: str, entries: Iterable):
        print(title)
        for entry in entries:
            old_version = entry.old_version or "-"
            new_version = entry.new_version or "-"
            print(f"  - {entry.name}: {old_version} → {new_version}")
        if not list(entries):
            print("  (none)")

    _print_group("Added", report.added)
    _print_group("Removed", report.removed)
    _print_group("Updated", report.updated)

