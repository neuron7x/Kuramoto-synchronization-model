"""Validate dataset sample contracts against on-disk artifacts.

This utility scans dataset contract markdown files (by default under
``docs/data`` and ``docs/datasets``) and verifies that the declared sample
artifacts exist, remain within the repository root, and match their documented
checksums and sizes.  It is designed to be CI friendly – returning a non-zero
exit code whenever a contract is invalid – while still being lightweight
enough to run as a local pre-flight check for documentation authors.

Dataset contracts are expected to expose metadata in the YAML front matter with
an ``artifacts`` list containing entries of the form:

.. code-block:: yaml

   ---
   owner: data@tradepulse
   review_cadence: quarterly
   artifacts:
     - path: data/sample.csv
       checksum: sha256:4a54...
       size_bytes: 1024  # optional
   ---

``path`` values are resolved relative to the repository root (falling back to
the directory of the contract file).  Supported checksum algorithms currently
include ``sha256``, ``sha512``, ``blake2b``, and ``blake2s``.  Additional
algorithms can be added by extending :data:`SUPPORTED_ALGORITHMS`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, MutableSequence, Sequence

import yaml

LOGGER = logging.getLogger(__name__)

SUPPORTED_ALGORITHMS = {"sha256", "sha512", "blake2b", "blake2s"}

DEFAULT_CONTRACT_DIRS = (Path("docs/data"), Path("docs/datasets"))


class ValidationError(Exception):
    """Raised when a contract cannot be parsed or validated."""


@dataclass(frozen=True)
class ArtifactSpec:
    """Declarative representation of a documented artifact."""

    path: Path
    checksum: str
    algorithm: str
    digest: str
    size_bytes: int | None


@dataclass(frozen=True)
class ArtifactValidation:
    """Validation outcome for a single artifact."""

    spec: ArtifactSpec
    resolved_path: Path | None
    actual_checksum: str | None
    actual_size: int | None
    errors: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class ContractReport:
    """Aggregate validation result for a dataset contract."""

    path: Path
    artifacts: tuple[ArtifactValidation, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    def valid(self, *, treat_warnings_as_errors: bool = False) -> bool:
        if self.errors:
            return False
        if any(not artifact.valid for artifact in self.artifacts):
            return False
        if treat_warnings_as_errors and (
            self.warnings or any(artifact.warnings for artifact in self.artifacts)
        ):
            return False
        return True


def _split_front_matter(text: str) -> tuple[Mapping[str, object], str]:
    """Return (front_matter, body) for markdown with optional YAML preamble."""

    lines = text.splitlines()
    if not lines:
        return {}, ""
    if lines[0].strip() != "---":
        return {}, text
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            yaml_text = "\n".join(lines[1:idx])
            body = "\n".join(lines[idx + 1 :])
            try:
                data = yaml.safe_load(yaml_text) or {}
            except yaml.YAMLError as exc:
                raise ValidationError("invalid YAML front matter") from exc
            if not isinstance(data, Mapping):
                raise ValidationError("front matter must be a mapping")
            return data, body
    raise ValidationError("unterminated YAML front matter")


def _normalise_checksum(raw: str, algorithm: str | None = None) -> tuple[str, str]:
    """Extract algorithm and digest from a checksum specification."""

    text = raw.strip()
    if not text:
        raise ValidationError("checksum value cannot be empty")
    if ":" in text:
        algo, digest = text.split(":", 1)
        algo = algo.strip().lower()
        digest = digest.strip()
    else:
        algo = algorithm.strip().lower() if algorithm else "sha256"
        digest = text
    if algo not in SUPPORTED_ALGORITHMS:
        raise ValidationError(
            f"unsupported checksum algorithm '{algo}'. Supported: {sorted(SUPPORTED_ALGORITHMS)}"
        )
    if not digest:
        raise ValidationError("checksum digest cannot be empty")
    if any(ch not in "0123456789abcdefABCDEF" for ch in digest):
        raise ValidationError("checksum digest must be hexadecimal")
    return algo, digest.lower()


def _parse_artifact_specs(
    contract_path: Path, front_matter: Mapping[str, object]
) -> tuple[ArtifactSpec, ...]:
    raw_artifacts = front_matter.get("artifacts")
    if raw_artifacts is None:
        raise ValidationError("front matter missing 'artifacts' list")
    if not isinstance(raw_artifacts, Sequence) or isinstance(
        raw_artifacts, (str, bytes)
    ):
        raise ValidationError("'artifacts' must be a sequence of mappings")

    specs: list[ArtifactSpec] = []
    for index, entry in enumerate(raw_artifacts):
        if not isinstance(entry, Mapping):
            raise ValidationError(f"artifacts[{index}] must be a mapping")
        path_value = entry.get("path")
        checksum_value = entry.get("checksum")
        algorithm_value = entry.get("algorithm")
        size_value = entry.get("size_bytes")

        if not isinstance(path_value, str) or not path_value.strip():
            raise ValidationError(f"artifacts[{index}] has invalid 'path'")
        if not isinstance(checksum_value, str) or not checksum_value.strip():
            raise ValidationError(f"artifacts[{index}] has invalid 'checksum'")
        algorithm, digest = _normalise_checksum(
            checksum_value,
            algorithm_value if isinstance(algorithm_value, str) else None,
        )

        size_bytes: int | None
        if size_value is None:
            size_bytes = None
        elif isinstance(size_value, (int, float)):
            size_bytes = int(size_value)
        else:
            raise ValidationError(f"artifacts[{index}] has invalid 'size_bytes'")

        specs.append(
            ArtifactSpec(
                path=Path(path_value),
                checksum=checksum_value.strip(),
                algorithm=algorithm,
                digest=digest,
                size_bytes=size_bytes,
            )
        )

    if not specs:
        raise ValidationError("'artifacts' list is empty")
    return tuple(specs)


def _resolve_artifact_path(
    spec: ArtifactSpec, *, contract_path: Path, repo_root: Path
) -> Path:
    """Resolve an artifact path within the repository root."""

    candidates = []
    path_value = spec.path
    if path_value.is_absolute():
        candidates.append(path_value)
    else:
        candidates.append(repo_root / path_value)
        candidates.append(contract_path.parent / path_value)

    for candidate in candidates:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(repo_root.resolve())
        except ValueError as exc:
            # Only reject when the candidate exists; otherwise try next fallback.
            if resolved.exists():
                raise ValidationError(
                    f"artifact path '{spec.path}' resolves outside repository root: {resolved}"
                ) from exc
            continue
        if resolved.exists():
            return resolved
    # If no candidate exists we still resolve relative to repo root for error reporting.
    return (repo_root / path_value).resolve()


def _compute_checksum(path: Path, algorithm: str) -> str:
    hasher = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def validate_contract(path: Path, *, repo_root: Path) -> ContractReport:
    """Validate a single dataset contract."""

    text = path.read_text(encoding="utf-8")
    errors: MutableSequence[str] = []
    warnings: MutableSequence[str] = []
    artifacts: list[ArtifactValidation] = []

    try:
        front_matter, _ = _split_front_matter(text)
        specs = _parse_artifact_specs(path, front_matter)
    except ValidationError as exc:
        errors.append(str(exc))
        return ContractReport(
            path=path,
            artifacts=tuple(artifacts),
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    for spec in specs:
        artifact_errors: list[str] = []
        artifact_warnings: list[str] = []
        resolved = None
        actual_checksum: str | None = None
        actual_size: int | None = None

        try:
            resolved = _resolve_artifact_path(
                spec, contract_path=path, repo_root=repo_root
            )
        except ValidationError as exc:
            artifact_errors.append(str(exc))
            artifacts.append(
                ArtifactValidation(
                    spec=spec,
                    resolved_path=None,
                    actual_checksum=None,
                    actual_size=None,
                    errors=tuple(artifact_errors),
                    warnings=tuple(artifact_warnings),
                )
            )
            continue

        if not resolved.exists():
            artifact_errors.append(f"artifact file not found: {resolved}")
        else:
            actual_size = resolved.stat().st_size
            try:
                actual_checksum = _compute_checksum(resolved, spec.algorithm)
            except (OSError, ValueError) as exc:
                artifact_errors.append(
                    f"failed to compute checksum for {resolved}: {exc}"
                )

            if actual_checksum and actual_checksum.lower() != spec.digest:
                artifact_errors.append(
                    "checksum mismatch: expected "
                    f"{spec.algorithm}:{spec.digest} got {spec.algorithm}:{actual_checksum}"
                )
            if spec.size_bytes is not None and actual_size is not None:
                if actual_size != spec.size_bytes:
                    artifact_warnings.append(
                        f"size mismatch: expected {spec.size_bytes} bytes, got {actual_size}"
                    )

        artifacts.append(
            ArtifactValidation(
                spec=spec,
                resolved_path=resolved,
                actual_checksum=actual_checksum,
                actual_size=actual_size,
                errors=tuple(artifact_errors),
                warnings=tuple(artifact_warnings),
            )
        )

    return ContractReport(
        path=path,
        artifacts=tuple(artifacts),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def discover_contracts(
    directories: Sequence[Path] | None = None, *, repo_root: Path
) -> list[Path]:
    """Return all markdown contracts from the provided directories."""

    dirs = directories if directories is not None else DEFAULT_CONTRACT_DIRS
    discovered: list[Path] = []
    for directory in dirs:
        base = directory if directory.is_absolute() else repo_root / directory
        if not base.exists():
            LOGGER.debug("Skipping missing contracts directory: %s", base)
            continue
        for path in sorted(base.rglob("*.md")):
            if path.is_file():
                discovered.append(path)
    return discovered


def validate_contracts(
    paths: Iterable[Path], *, repo_root: Path
) -> list[ContractReport]:
    """Validate multiple contracts returning per-contract reports."""

    reports: list[ContractReport] = []
    for path in sorted(set(Path(p) for p in paths)):
        reports.append(validate_contract(path, repo_root=repo_root))
    return reports


def _render_text_report(
    reports: Sequence[ContractReport], *, warn_as_error: bool
) -> str:
    lines: list[str] = []
    for report in reports:
        status = (
            "OK" if report.valid(treat_warnings_as_errors=warn_as_error) else "FAIL"
        )
        lines.append(f"[{status}] {report.path}")
        for error in report.errors:
            lines.append(f"  ERROR: {error}")
        for warning in report.warnings:
            lines.append(f"  WARNING: {warning}")
        for artifact in report.artifacts:
            prefix = "    OK"
            if artifact.errors:
                prefix = "    ERROR"
            elif warn_as_error and artifact.warnings:
                prefix = "    WARNING"
            lines.append(f"{prefix}: {artifact.spec.path}")
            for error in artifact.errors:
                lines.append(f"      ERROR: {error}")
            for warning in artifact.warnings:
                lines.append(f"      WARNING: {warning}")
    if not lines:
        lines.append("No dataset contracts found.")
    return "\n".join(lines)


def _render_json_report(reports: Sequence[ContractReport]) -> str:
    payload = [
        {
            "path": str(report.path),
            "valid": report.valid(),
            "errors": list(report.errors),
            "warnings": list(report.warnings),
            "artifacts": [
                {
                    "path": str(artifact.spec.path),
                    "resolved_path": (
                        str(artifact.resolved_path) if artifact.resolved_path else None
                    ),
                    "algorithm": artifact.spec.algorithm,
                    "expected_digest": artifact.spec.digest,
                    "actual_checksum": artifact.actual_checksum,
                    "actual_size": artifact.actual_size,
                    "size_bytes": artifact.spec.size_bytes,
                    "errors": list(artifact.errors),
                    "warnings": list(artifact.warnings),
                }
                for artifact in report.artifacts
            ],
        }
        for report in reports
    ]
    return json.dumps(payload, indent=2, sort_keys=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--contracts-dir",
        action="append",
        type=Path,
        help=(
            "Directory containing dataset contracts. Can be provided multiple "
            "times. Defaults to docs/data and docs/datasets when omitted."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root used to resolve relative artifact paths.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format for the validation report.",
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Treat size mismatches and warnings as failures.",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    reports = validate_contracts(
        discover_contracts(args.contracts_dir, repo_root=args.repo_root),
        repo_root=args.repo_root,
    )

    if args.format == "json":
        output = _render_json_report(reports)
    else:
        output = _render_text_report(reports, warn_as_error=args.fail_on_warning)
    print(output)

    treat_warnings_as_errors = args.fail_on_warning
    if reports and all(
        report.valid(treat_warnings_as_errors=treat_warnings_as_errors)
        for report in reports
    ):
        return 0
    if not reports:
        # No contracts found is treated as success to keep the script usable in new repositories.
        return 0
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())


__all__ = [
    "ArtifactSpec",
    "ArtifactValidation",
    "ContractReport",
    "ValidationError",
    "discover_contracts",
    "validate_contract",
    "validate_contracts",
    "main",
]
