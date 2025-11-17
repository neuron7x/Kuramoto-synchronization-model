"""Repository secret scanner for continuous compliance workflows."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

_COMMON_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "aws_access_key_id",
        re.compile(r"AKIA[0-9A-Z]{16}"),
    ),
    (
        "aws_secret_access_key",
        re.compile(r"(?i)aws(.{0,20})?(secret|access)[^\n]*[0-9A-Za-z/+]{40}"),
    ),
    (
        "generic_api_key",
        re.compile(r"(?i)api[_-]?key['\"]?\s*[:=]\s*['\"]?[0-9A-Za-z-_]{20,}"),
    ),
    (
        "slack_token",
        re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,48}"),
    ),
    (
        "private_key_block",
        re.compile(r"-----BEGIN (RSA|DSA|EC|OPENSSH) PRIVATE KEY-----"),
    ),
)


@dataclass(slots=True)
class SecretFinding:
    path: str
    line: int
    detector: str
    context: str
    entropy: float | None = None


class SecretScanner:
    """Static scanner that heuristically identifies potential secrets."""

    def __init__(
        self,
        *,
        min_entropy: float = 4.0,
        min_length: int = 20,
        ignore_file: str = ".secretsignore",
        include_patterns: Sequence[str] | None = None,
    ) -> None:
        self._min_entropy = min_entropy
        self._min_length = min_length
        self._ignore_file = ignore_file
        self._include_patterns = tuple(include_patterns or ())
        self._ignored_paths: set[str] = set()
        self._ignored_patterns: tuple[re.Pattern[str], ...] = ()

    def load_ignore_rules(self, root: Path) -> None:
        ignore_path = root / self._ignore_file
        if not ignore_path.exists():
            return
        patterns: list[re.Pattern[str]] = []
        for line in ignore_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("regex:"):
                patterns.append(re.compile(line.partition(":")[2]))
            else:
                self._ignored_paths.add(line)
        self._ignored_patterns = tuple(patterns)

    def scan(self, root: Path) -> list[SecretFinding]:
        """Scan *root* for potential secrets."""

        if not root.exists():
            raise FileNotFoundError(f"scan root '{root}' does not exist")
        self.load_ignore_rules(root)
        findings: list[SecretFinding] = []
        for path in self._iter_paths(root):
            findings.extend(self._scan_file(path))
        return findings

    def _iter_paths(self, root: Path) -> Iterator[Path]:
        for dirpath, dirnames, filenames in os.walk(root):
            # Mutate dirnames in-place to control traversal.
            dirnames[:] = [
                name
                for name in dirnames
                if not name.startswith(".") or name == ".well-known"
            ]
            relative_dir = str(Path(dirpath).relative_to(root))
            if any(relative_dir.startswith(ignored) for ignored in self._ignored_paths):
                continue
            for filename in filenames:
                candidate = Path(dirpath) / filename
                rel_path = str(candidate.relative_to(root))
                if any(rel_path.startswith(ignored) for ignored in self._ignored_paths):
                    continue
                if self._include_patterns and not any(
                    re.search(pattern, rel_path) for pattern in self._include_patterns
                ):
                    continue
                if candidate.suffix in {
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".gif",
                    ".bmp",
                    ".ico",
                }:
                    continue
                yield candidate

    def _scan_file(self, path: Path) -> list[SecretFinding]:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []
        findings: list[SecretFinding] = []
        for lineno, line in enumerate(content.splitlines(), start=1):
            if self._is_ignored_line(line):
                continue
            stripped = line.strip()
            for detector, pattern in _COMMON_PATTERNS:
                if pattern.search(stripped):
                    findings.append(
                        SecretFinding(
                            path=str(path),
                            line=lineno,
                            detector=detector,
                            context=stripped[:200],
                            entropy=None,
                        )
                    )
                    break
            else:
                token = self._extract_candidate(stripped)
                if token and self._high_entropy(token):
                    findings.append(
                        SecretFinding(
                            path=str(path),
                            line=lineno,
                            detector="high_entropy",
                            context=token[:200],
                            entropy=self._entropy(token),
                        )
                    )
        return findings

    def _is_ignored_line(self, line: str) -> bool:
        return any(pattern.search(line) for pattern in self._ignored_patterns)

    def _extract_candidate(self, line: str) -> str | None:
        match = re.search(r"(['\"])([A-Za-z0-9/+_=\-]{20,})(['\"])", line)
        if match:
            return match.group(2)
        match = re.search(r"[:=]\s*([A-Za-z0-9/+_=\-]{20,})", line)
        if match:
            return match.group(1)
        return None

    def _entropy(self, token: str) -> float:
        probabilities = [token.count(ch) / len(token) for ch in set(token)]
        return -sum(p * math.log2(p) for p in probabilities)

    def _high_entropy(self, token: str) -> bool:
        if len(token) < self._min_length:
            return False
        return self._entropy(token) >= self._min_entropy


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan for potential secrets")
    parser.add_argument("path", nargs="?", default=".", help="Root path to scan")
    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON output"
    )
    parser.add_argument(
        "--min-entropy",
        type=float,
        default=4.0,
        help="Minimum Shannon entropy for high-entropy detector",
    )
    parser.add_argument(
        "--min-length",
        type=int,
        default=20,
        help="Minimum token length considered for entropy detection",
    )
    return parser.parse_args(argv)


def _print_findings(findings: Iterable[SecretFinding], *, emit_json: bool) -> None:
    findings_list = list(findings)
    if emit_json:
        print(json.dumps([asdict(finding) for finding in findings_list], indent=2))
        return
    if not findings_list:
        print("No secrets detected.")
        return
    for finding in findings_list:
        entropy_display = (
            f" entropy={finding.entropy:.2f}" if finding.entropy is not None else ""
        )
        print(
            f"{finding.path}:{finding.line} [{finding.detector}]{entropy_display} -> {finding.context}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    namespace = _parse_args(argv or sys.argv[1:])
    scanner = SecretScanner(
        min_entropy=namespace.min_entropy,
        min_length=namespace.min_length,
    )
    findings = scanner.scan(Path(namespace.path).resolve())
    _print_findings(findings, emit_json=namespace.json)
    return 1 if findings else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
