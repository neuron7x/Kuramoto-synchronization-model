"""Cross-platform data synchronisation helper with resilience features."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import argparse
import json
import sys
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from scripts.runtime import (
    EXIT_CODES,
    ArtifactManager,
    ChecksumMismatchError,
    ProgressBar,
    create_artifact_manager,
    create_resilient_session,
    task_queue,
    transfer_with_resume,
)
from scripts.runtime.pathfinder import find_resources
from scripts.runtime.transfer import TransferError


@dataclass(slots=True)
class ResolvedSource:
    """Normalized representation of an input target for synchronization."""

    source: str
    destination_key: str
    checksum_keys: tuple[str, ...]


@dataclass(slots=True)
class SyncResult:
    source: str
    destination: Path
    checksum: str | None
    status: str


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "sources",
        nargs="+",
        help="Source URLs or file paths. Directories are walked recursively when used with --pattern.",
    )
    parser.add_argument(
        "--pattern",
        default="*",
        help="Pattern passed to Path.rglob when expanding directory sources (default: *).",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=None,
        help="Override the root directory used for storing artefacts (default: reports/scripts).",
    )
    parser.add_argument(
        "--script-name",
        default="resilient-data-sync",
        help="Name used when constructing the artefact directory (default: resilient-data-sync).",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="Maximum number of concurrent transfers (default: 1).",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=5,
        help="Number of HTTP retries applied to remote transfers (default: 5).",
    )
    parser.add_argument(
        "--checksum",
        action="append",
        default=[],
        metavar="SOURCE=HASH",
        help="Expected checksum for a given source expressed as SOURCE=HEX.",
    )
    parser.add_argument(
        "--checksum-algorithm",
        default="sha256",
        help="Hash algorithm used for checksum verification (default: sha256).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON summary of transfer results to stdout.",
    )
    return parser.parse_args(argv)


def _resolve_sources(raw_sources: list[str], pattern: str) -> list[ResolvedSource]:
    resolved: list[ResolvedSource] = []
    for raw in raw_sources:
        parsed = urlparse(raw)
        if parsed.scheme in {"http", "https", "file"}:
            name = _destination_name(raw)
            resolved.append(
                ResolvedSource(source=raw, destination_key=name, checksum_keys=(raw,))
            )
            continue
        path = Path(raw)
        if path.is_file():
            name = path.name or _destination_name(raw)
            resolved.append(
                ResolvedSource(
                    source=str(path),
                    destination_key=name,
                    checksum_keys=(str(path), str(path.resolve())),
                )
            )
        elif path.is_dir():
            root = path.resolve()
            for candidate in find_resources(pattern, [path]):
                try:
                    relative = candidate.relative_to(root)
                except ValueError:
                    relative_key = candidate.name
                    checksum_keys = (str(candidate), relative_key)
                else:
                    relative_key = relative.as_posix()
                    checksum_keys = (
                        str(candidate),
                        relative_key,
                        str(relative),
                    )
                resolved.append(
                    ResolvedSource(
                        source=str(candidate),
                        destination_key=relative_key,
                        checksum_keys=checksum_keys,
                    )
                )
        else:
            fallback = _destination_name(raw)
            resolved.append(
                ResolvedSource(
                    source=str(path),
                    destination_key=fallback,
                    checksum_keys=(str(path),),
                )
            )
    return resolved


def _parse_checksum_pairs(pairs: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise argparse.ArgumentTypeError(
                f"Invalid checksum specification '{pair}'. Expected SOURCE=HEX."
            )
        source, checksum = pair.split("=", 1)
        mapping[source] = checksum
    return mapping


def _destination_name(source: str) -> str:
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https", "file"}:
        name = Path(parsed.path).name
    else:
        name = Path(source).name
    if not name:
        name = "artifact"
    return name


def _transfer_one(
    source: str,
    destination: Path,
    *,
    checksum: str | None,
    checksum_algorithm: str,
    retries: int,
) -> SyncResult:
    session = create_resilient_session(total_retries=retries)
    progress = ProgressBar(label=f"{Path(destination).name}")
    with progress:
        try:
            transfer_with_resume(
                source,
                destination,
                session=session,
                expected_checksum=checksum,
                checksum_algorithm=checksum_algorithm,
                progress=progress,
            )
        except ChecksumMismatchError:
            return SyncResult(
                source=source,
                destination=destination,
                checksum=checksum,
                status="checksum_mismatch",
            )
        except TransferError as exc:
            return SyncResult(
                source=source,
                destination=destination,
                checksum=checksum,
                status=f"transfer_error:{exc}",
            )
    return SyncResult(
        source=source, destination=destination, checksum=checksum, status="ok"
    )


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.sources:
        print("No sources provided.", file=sys.stderr)
        return EXIT_CODES["invalid_arguments"]

    try:
        checksums = _parse_checksum_pairs(args.checksum)
    except argparse.ArgumentTypeError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_CODES["invalid_arguments"]

    manager: ArtifactManager = create_artifact_manager(
        args.script_name, root=args.artifact_root
    )
    resolved_sources = _resolve_sources(args.sources, args.pattern)
    if not resolved_sources:
        print("No matching sources found.", file=sys.stderr)
        return EXIT_CODES["missing_resource"]

    results: list[SyncResult] = []

    destinations: dict[str, Path] = {}
    for spec in resolved_sources:
        destinations[spec.source] = manager.path_for(spec.destination_key)

    with task_queue(max_workers=max(1, args.max_workers)) as queue:
        futures: list[tuple[ResolvedSource, str | None, Future[SyncResult]]] = []
        for spec in resolved_sources:
            destination = destinations[spec.source]
            checksum_value: str | None = None
            for key in spec.checksum_keys:
                checksum_value = checksums.get(key)
                if checksum_value is not None:
                    break
            future = queue.submit(
                _transfer_one,
                spec.source,
                destination,
                checksum=checksum_value,
                checksum_algorithm=args.checksum_algorithm,
                retries=max(1, args.retries),
            )
            futures.append((spec, checksum_value, future))

        for spec, checksum_value, future in futures:
            try:
                result = future.result()
            except (
                Exception
            ) as exc:  # pragma: no cover - defensive catch for unexpected failures
                results.append(
                    SyncResult(
                        source=spec.source,
                        destination=destinations[spec.source],
                        checksum=checksum_value,
                        status=f"internal_error:{exc}",
                    )
                )
            else:
                results.append(result)

    has_failures = False
    for result in results:
        if result.status != "ok":
            has_failures = True
        status_message = "✅" if result.status == "ok" else "❌"
        print(
            f"{status_message} {result.source} → {result.destination} ({result.status})"
        )

    if args.json:
        payload = [
            {
                "source": result.source,
                "destination": str(result.destination),
                "checksum": result.checksum,
                "status": result.status,
            }
            for result in results
        ]
        print(json.dumps(payload, indent=2))

    if has_failures:
        for result in results:
            if result.status == "checksum_mismatch":
                return EXIT_CODES["checksum_mismatch"]
            if result.status.startswith("transfer_error"):
                return EXIT_CODES["network_failure"]
            if result.status.startswith("internal_error"):
                return EXIT_CODES["internal_error"]
        return EXIT_CODES["internal_error"]

    return EXIT_CODES["success"]


if __name__ == "__main__":
    raise SystemExit(main())
