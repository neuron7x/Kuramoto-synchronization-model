# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Security scanning and secret detection utilities for GeoSync.

This module provides tools for detecting secrets, API keys, and sensitive
data in code and configuration files.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Pattern, Tuple

_LOGGER = logging.getLogger(__name__)

# Common secret patterns
SECRET_PATTERNS: Dict[str, Pattern[str]] = {
    "api_key": re.compile(r"(?i)(api[_-]?key|apikey)\s*[=:]\s*['\"]([a-zA-Z0-9_\-]+)['\"]"),
    "api_secret": re.compile(
        r"(?i)(api[_-]?secret|apisecret)\s*[=:]\s*['\"]([a-zA-Z0-9_\-]+)['\"]"
    ),
    "password": re.compile(r"(?i)(password|passwd|pwd)\s*[=:]\s*['\"]([^'\"]+)['\"]"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----"),
    "aws_key": re.compile(r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}"),
    "github_token": re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    "jwt_token": re.compile(r"eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*"),
    "slack_token": re.compile(r"xox[baprs]-[0-9]{10,13}-[a-zA-Z0-9-]{24,}"),
    "stripe_key": re.compile(r"(?:r|s)k_(?:test|live)_[0-9a-zA-Z]{24,}"),
    "generic_secret": re.compile(r"(?i)secret\s*[=:]\s*['\"]([^'\"]{8,})['\"]"),
}

# Files and patterns to always ignore
IGNORE_PATTERNS = [
    r"\.git/",
    r"\.mypy_cache/",
    r"__pycache__/",
    r"node_modules/",
    r"\.env\.example$",
    r"\.md$",  # Documentation
    r"\.rst$",  # Documentation
    r"(^|[\\/])test_[^/\\]*\.py$",  # Test files often have mock secrets
    r"[\\/]tests[\\/]",  # Tests directory
    r"conftest\.py$",
    r"(^|/)configs/tls/dev/",  # Dev TLS certificates for local testing
    r"(^|/)audit/artifacts/",  # Security scan artifacts/reports
]


class SecretDetector:
    """Detect secrets and sensitive data in files."""

    patterns: Dict[str, Pattern[str]]

    def __init__(self, custom_patterns: Dict[str, Pattern[str]] | None = None):
        """Initialize secret detector.

        Args:
            custom_patterns: Optional additional patterns to check
        """
        self.patterns = SECRET_PATTERNS.copy()
        if custom_patterns:
            self.patterns.update(custom_patterns)

    def scan_file(self, filepath: str | Path) -> List[Tuple[str, int, str]]:
        """Scan a file for secrets.

        Args:
            filepath: Path to file to scan

        Returns:
            List of (secret_type, line_number, matched_text) tuples
        """
        filepath = Path(filepath)

        # Check if should be ignored
        for pattern in IGNORE_PATTERNS:
            if re.search(pattern, str(filepath)):
                return []

        findings: List[Tuple[str, int, str]] = []

        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, start=1):
                    for secret_type, pattern in self.patterns.items():
                        match = pattern.search(line)
                        if match:
                            # Mask the secret in output
                            masked_line = self._mask_line(line)
                            findings.append((secret_type, line_num, masked_line))
        except OSError as exc:
            _LOGGER.debug("Skipping unreadable file during secret scan", exc_info=exc)

        return findings

    def scan_directory(
        self,
        directory: str | Path,
        extensions: List[str] | None = None,
    ) -> Dict[str, List[Tuple[str, int, str]]]:
        """Scan a directory recursively for secrets.

        Args:
            directory: Directory to scan
            extensions: Optional list of file extensions to check

        Returns:
            Dictionary mapping filenames to findings
        """
        directory = Path(directory)

        if extensions is None:
            extensions = [
                ".py",
                ".js",
                ".ts",
                ".java",
                ".go",
                ".yml",
                ".yaml",
                ".json",
                ".env",
                ".env.local",
                ".env.production",
            ]

        normalized_extensions = {ext.lower() for ext in extensions}

        results: Dict[str, List[Tuple[str, int, str]]] = {}

        for filepath in directory.rglob("*"):
            if not filepath.is_file():
                continue

            file_name = filepath.name.lower()

            if normalized_extensions:
                matches_extension = any(
                    file_name == ext or file_name.endswith(ext) for ext in normalized_extensions
                )
                if not matches_extension:
                    continue

            findings = self.scan_file(filepath)
            if findings:
                relative_path = str(filepath.relative_to(directory))
                results[relative_path] = findings

        return results

    def _mask_line(self, line: str) -> str:
        """Mask secrets in a line for safe display."""
        # Replace any quoted strings longer than 8 chars with asterisks
        masked = re.sub(r'["\'][^"\']{8,}["\']', '"********"', line)
        return masked.strip()


def check_for_hardcoded_secrets(root_dir: str = ".") -> bool:
    """Check repository for hardcoded secrets.

    Args:
        root_dir: Root directory to scan

    Returns:
        True if secrets found, False otherwise
    """
    detector = SecretDetector()
    results = detector.scan_directory(root_dir)

    if not results:
        print("✓ No hardcoded secrets detected")
        return False

    print("⚠️  Potential secrets detected:")
    for filename, findings in results.items():
        print(f"\n  {filename}:")
        for secret_type, line_num, line in findings:
            print(f"    Line {line_num} ({secret_type}): {line}")

    print("\n⚠️  Review these findings and remove any hardcoded secrets")
    print("   Use environment variables or secret management systems instead")
    return True


__all__ = [
    "SecretDetector",
    "check_for_hardcoded_secrets",
    "SECRET_PATTERNS",
]
