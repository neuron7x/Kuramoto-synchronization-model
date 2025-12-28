"""Utility to run pip-audit with consistent settings and provide actionable summaries."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Sequence

DEFAULT_REQUIREMENTS = ("requirements.txt",)
DEFAULT_DEV_REQUIREMENTS = ("requirements-dev.txt",)
SAFE_PATH_RE = re.compile(r"[A-Za-z0-9_./+-]+")
SAFE_EXTRA_ARG_RE = re.compile(
    r"-{1,2}[A-Za-z0-9][A-Za-z0-9_.-]*(?:=[A-Za-z0-9_./:+-]+)?"
)


class DependencyAuditError(RuntimeError):
    """Raised when pip-audit cannot be executed successfully."""


def _validate_requirement_path(value: str) -> str:
    if not SAFE_PATH_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "Requirement paths may only contain letters, numbers, and ./_-+ characters."
        )
    return value


def _validate_pip_audit_bin(value: str) -> str:
    if not SAFE_PATH_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "pip-audit executable may only contain letters, numbers, and ./_-+ characters."
        )
    return value


def _validate_extra_arg(value: str) -> str:
    if not SAFE_EXTRA_ARG_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "Extra arguments must be flag-style values like --option or --option=value."
        )
    return value


def _validate_write_json_path(value: str) -> Path:
    if not SAFE_PATH_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "JSON output path may only contain letters, numbers, and ./_-+ characters."
        )
    path = Path(value)
    if path.suffix.lower() != ".json":
        raise argparse.ArgumentTypeError("JSON output path must end with .json.")
    return path


def _resolve_requirements(paths: Sequence[str | Path]) -> List[Path]:
    resolved: List[Path] = []
    for raw in paths:
        candidate = Path(raw)
        if not candidate.exists():
            raise DependencyAuditError(f"Requirement file '{candidate}' does not exist")
        resolved.append(candidate)
    return resolved


def _run_pip_audit(
    pip_audit_bin: str,
    requirements: Sequence[Path],
    include_transitive: bool,
    extra_args: Sequence[str],
) -> subprocess.CompletedProcess[str]:
    if shutil.which(pip_audit_bin) is None:
        raise DependencyAuditError(
            "pip-audit is not installed. Install it via `pip install pip-audit` or use the development requirements."
        )

    cmd: list[str] = [pip_audit_bin, "--progress-spinner", "off", "--format", "json"]
    if not include_transitive:
        cmd.append("--no-deps")
    for req in requirements:
        cmd.extend(["-r", str(req)])
    cmd.extend(extra_args)

    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode not in (0, 1):
        stderr = result.stderr.strip()
        raise DependencyAuditError(
            "pip-audit execution failed with exit code "
            f"{result.returncode}: {stderr or 'no additional diagnostics available'}"
        )
    return result


def _parse_vulnerabilities(stdout: str) -> list[dict[str, object]]:
    payload = stdout.strip()
    if not payload:
        return []

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise DependencyAuditError(f"Failed to parse pip-audit output: {exc}") from exc

    dependencies = parsed.get("dependencies", [])
    findings: list[dict[str, object]] = []
    for entry in dependencies:
        vulns = entry.get("vulns", [])
        if not vulns:
            continue
        for vuln in vulns:
            finding = {
                "name": entry.get("name", "<unknown>"),
                "version": entry.get("version", "<unknown>"),
                "id": vuln.get("id", "<unknown>"),
                "aliases": tuple(vuln.get("aliases", ())),
                "fix_versions": tuple(vuln.get("fix_versions", ())),
                "description": vuln.get("description", ""),
                "severity": (vuln.get("severity") or "unknown").lower(),
            }
            if _is_mitigated(finding):
                continue
            findings.append(finding)
    return findings


def _is_mitigated(finding: dict[str, object]) -> bool:
    """Determine whether a vulnerability is already mitigated locally."""

    if finding.get("name") != "pip":
        return False
    if finding.get("id") != "GHSA-4xh5-x5gv-qwph":
        return False

    try:
        import pip
        from packaging.version import InvalidVersion, Version
        from pip._internal.utils import unpacking
    except ImportError:
        # Required modules not available - cannot verify mitigation
        return False

    try:
        version = Version(pip.__version__)
    except InvalidVersion:
        return False

    if version >= Version("25.3"):
        return True

    return bool(getattr(unpacking, "_tradepulse_symlink_patch", False))


def _print_summary(findings: Sequence[dict[str, object]]) -> None:
    if not findings:
        print("✅ No known vulnerabilities found across the supplied dependency sets.")
        return

    print(
        "❌ Found "
        f"{len(findings)} known vulnerabilities across {len({(f['name'], f['version']) for f in findings})} packages."
    )

    grouped: defaultdict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for finding in findings:
        grouped[(finding["name"], finding["version"])] += [finding]

    for name, version in sorted(grouped):
        print(f"\n{name}=={version}")
        for vuln in grouped[(name, version)]:
            fix = ", ".join(vuln["fix_versions"]) or "no patched release available"
            aliases = ", ".join(vuln["aliases"]) or "no aliases"
            description = (
                vuln["description"].strip().splitlines()[0]
                if vuln["description"]
                else ""
            )
            print(f"  - {vuln['id']} (aliases: {aliases})")
            print(f"    ↳ upgrade to: {fix}")
            if description:
                print(f"    ↳ summary: {description}")

    severities = Counter(vuln.get("severity", "unknown") for vuln in findings)
    if severities:
        print("\nSeverity distribution:")
        for severity, count in sorted(severities.items(), key=lambda item: item[0]):
            label = severity or "unknown"
            print(f"  • {label}: {count}")


def _write_report(findings: Sequence[dict[str, object]], destination: Path) -> None:
    structured = {
        "total_findings": len(findings),
        "packages": sorted(
            (
                {
                    "name": finding["name"],
                    "version": finding["version"],
                    "advisory": finding["id"],
                    "aliases": list(finding["aliases"]),
                    "fix_versions": list(finding["fix_versions"]),
                    "severity": finding.get("severity", "unknown"),
                    "description": finding.get("description", ""),
                }
                for finding in findings
            ),
            key=lambda item: (item["name"], item["advisory"]),
        ),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(structured, indent=2), encoding="utf-8")
    print(f"✍️  Wrote machine-readable report to {destination}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run pip-audit across pinned dependency manifests and emit actionable summaries.",
    )
    parser.add_argument(
        "-r",
        "--requirement",
        action="append",
        dest="requirements",
        default=list(DEFAULT_REQUIREMENTS),
        type=_validate_requirement_path,
        help="Requirement file(s) to audit. Defaults to requirements.txt",
    )
    parser.add_argument(
        "--include-dev",
        action="store_true",
        help="Also include the default development requirements (requirements-dev.txt).",
    )
    parser.add_argument(
        "--include-transitive",
        action="store_true",
        help="Include transitive dependencies when invoking pip-audit (drops --no-deps).",
    )
    parser.add_argument(
        "--pip-audit-bin",
        default="pip-audit",
        type=_validate_pip_audit_bin,
        help="Custom pip-audit executable to invoke (defaults to 'pip-audit').",
    )
    parser.add_argument(
        "--write-json",
        type=_validate_write_json_path,
        help="Optional path to persist the aggregated vulnerability report as JSON.",
    )
    parser.add_argument(
        "--extra-arg",
        dest="extra_args",
        action="append",
        default=[],
        type=_validate_extra_arg,
        help="Additional raw arguments forwarded to pip-audit.",
    )
    parser.add_argument(
        "--fail-on",
        choices=("none", "any"),
        default="any",
        help="Control the exit status: 'any' (default) fails when vulnerabilities are present; 'none' always exits 0.",
    )

    args = parser.parse_args(argv)

    requirements = [_validate_requirement_path(str(req)) for req in args.requirements]
    pip_audit_bin = _validate_pip_audit_bin(str(args.pip_audit_bin))
    extra_args = [_validate_extra_arg(str(arg)) for arg in args.extra_args]
    write_json = (
        _validate_write_json_path(str(args.write_json)) if args.write_json else None
    )

    requirements = list(requirements)
    if args.include_dev and DEFAULT_DEV_REQUIREMENTS[0] not in requirements:
        requirements.append(_validate_requirement_path(DEFAULT_DEV_REQUIREMENTS[0]))

    try:
        resolved = _resolve_requirements(requirements)
        result = _run_pip_audit(
            pip_audit_bin=pip_audit_bin,
            requirements=resolved,
            include_transitive=args.include_transitive,
            extra_args=extra_args,
        )
        findings = _parse_vulnerabilities(result.stdout)
    except DependencyAuditError as exc:  # pragma: no cover - CLI surface
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    _print_summary(findings)

    if write_json:
        _write_report(findings, write_json)

    if args.fail_on == "none":
        return 0

    return 1 if findings else 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
