#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Capsule secret-boundary validator (TASK 931).

PR #929 excluded ``artifacts/reproducible_capsules/`` from the entropy-based
detect-secrets scan, because a reproducible capsule's SHA-256 manifest digests
are public content hashes that the entropy plugin false-positives on. An exclude
zone is a liability: it could silently become a place to smuggle a real secret.

This validator replaces the blanket exclusion with *deterministic structural
validation*. Instead of guessing entropy, it asserts a closed structure:

* only an allow-list of text file types may exist (no binaries, no hidden files,
  no symlinks, no absolute paths);
* no file may contain a private-key block or a known credential signature;
* inside JSON, any high-entropy token MUST be bound to an approved digest field
  name — a hash under ``sha256`` is fine; the same hash under ``api_key`` is not.

Fail-closed: any violation exits non-zero with a named reason.

Run::

    python tools/security/validate_capsule_secret_boundary.py
    python tools/security/validate_capsule_secret_boundary.py --root <dir>

Exit codes::

    0  — every capsule file is structurally clean
    1  — at least one boundary violation
    2  — usage error (capsule root missing)
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CAPSULE_ROOT = REPO_ROOT / "artifacts" / "reproducible_capsules"

# Allowed file types inside a capsule. Everything else is rejected — a capsule is
# a text-only, human-auditable artifact graph.
ALLOWED_SUFFIXES: frozenset[str] = frozenset({".json", ".md", ".txt", ".sha256"})
ALLOWED_EXACT_NAMES: frozenset[str] = frozenset({"SHA256SUMS"})

# JSON keys under which a high-entropy hash/token is legitimate. Extends the
# TASK 931 base list with the provenance/digest fields the reproducible-capsule
# schema actually defines (git_sha, sha256_manifest), so the real manifest is
# clean while any other field carrying a token is rejected.
APPROVED_DIGEST_FIELDS: frozenset[str] = frozenset(
    {
        "sha256",
        "digest",
        "artifact_sha256",
        "config_sha256",
        "output_sha256",
        "env_sha256",
        "data_sha256",
        "sha256_manifest",
        "git_sha",
    }
)

# A token-like string: a long base64/hex blob. The charset is exactly the
# base64 alphabet (incl. '+' '/' '=') plus '-' (base64url), and deliberately
# excludes '_', '.', ':' and whitespace, so config identifiers
# ('reproducible_capsule.v1', 'last_price_persistence'), timestamps and repo
# paths — which carry one of those separators — are never mistaken for
# credentials. '/' MUST be included: standard-alphabet base64 secrets (e.g. an
# AWS secret-access-key shape 'wJalr.../...') contain '/', and excluding it left
# them invisible to the JSON token walk. Real-path false positives are still
# screened out by the '_'/'.'/':' exclusion above and the entropy floor below.
_TOKEN_RE = re.compile(r"^[A-Za-z0-9+/=-]{24,}$")
_HEX_RE = re.compile(r"^[A-Fa-f0-9]{32,}$")
_MIN_ENTROPY_BITS = 3.5

# Credential signatures that must never appear in any capsule file.
_SECRET_SIGNATURES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private key block", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[posru]_[A-Za-z0-9]{36,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("private key in env assignment", re.compile(r"PRIVATE_KEY\s*=")),
    (
        "credential assignment",
        re.compile(
            r"(?i)\b(api[_-]?key|secret|token|password|passwd|access[_-]?key)\b"
            # Tolerate a closing quote/space between the key and the separator so
            # JSON ('"api_key": "…"') and YAML are covered, not only bare 'k=v'.
            r"['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9+/_=-]{16,}"
        ),
    ),
)


def _shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for ch in value:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(value)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _has_charclass_diversity(value: str) -> bool:
    """True iff *value* draws on >=3 of {lowercase, uppercase, digit}.

    A base64/base64url encoding of random bytes draws uniformly from a 64-symbol
    alphabet, so for any realistic key length it contains lowercase AND uppercase
    AND digits with overwhelming probability. Human-authored slash-bearing
    strings — git refs ('refs/heads/fix/...'), kebab paths, slugs — are typically
    single-case and miss this bar. Requiring it lets '/' stay in _TOKEN_RE (so
    slash-bearing secrets are caught) without false-positiving on path/ref values
    under a non-digest field.
    """
    classes = (
        any(c.islower() for c in value)
        + any(c.isupper() for c in value)
        + any(c.isdigit() for c in value)
    )
    return classes >= 3


def _is_token_like(value: str) -> bool:
    """True iff *value* looks like a credential/hash token (not a path or id)."""
    if _HEX_RE.match(value):
        return True
    if (
        _TOKEN_RE.match(value)
        and _shannon_entropy(value) >= _MIN_ENTROPY_BITS
        and _has_charclass_diversity(value)
    ):
        return True
    return False


def _iter_files(root: Path) -> Iterable[Path]:
    yield from sorted(p for p in root.rglob("*") if p.is_symlink() or p.is_file())


def _walk_json_tokens(node: Any, key: str | None, path: str) -> list[str]:
    """Return violations for any token-like string not bound to an approved key."""
    violations: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            violations.extend(_walk_json_tokens(v, str(k), path))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            violations.extend(_walk_json_tokens(v, key, path))
    elif isinstance(node, str):
        if _is_token_like(node) and key not in APPROVED_DIGEST_FIELDS:
            field = key if key is not None else "<root>"
            violations.append(
                f"{path}: high-entropy token under non-digest field '{field}' "
                f"(approved fields: {sorted(APPROVED_DIGEST_FIELDS)})"
            )
    return violations


def validate_file(file_path: Path, root: Path) -> list[str]:
    rel = file_path.relative_to(root).as_posix()
    violations: list[str] = []

    if file_path.is_symlink():
        return [f"{rel}: symlinks are forbidden in a capsule"]
    if any(part.startswith(".") for part in file_path.relative_to(root).parts):
        return [f"{rel}: hidden files/dirs are forbidden in a capsule"]

    name = file_path.name
    if name not in ALLOWED_EXACT_NAMES and file_path.suffix not in ALLOWED_SUFFIXES:
        return [
            f"{rel}: disallowed file type (allowed: "
            f"{sorted(ALLOWED_SUFFIXES) + sorted(ALLOWED_EXACT_NAMES)})"
        ]

    raw = file_path.read_bytes()
    if b"\x00" in raw:
        return [f"{rel}: binary content (NUL byte) is forbidden in a capsule"]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return [f"{rel}: non-UTF-8 (binary) content is forbidden in a capsule"]

    for label, pattern in _SECRET_SIGNATURES:
        if pattern.search(text):
            violations.append(f"{rel}: contains {label}")

    if file_path.suffix == ".json":
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as exc:
            violations.append(f"{rel}: invalid JSON ({exc})")
        else:
            violations.extend(_walk_json_tokens(doc, None, rel))

    return violations


def validate_capsule_root(root: Path) -> list[str]:
    violations: list[str] = []
    for file_path in _iter_files(root):
        violations.extend(validate_file(file_path, root))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_CAPSULE_ROOT,
        help="Capsule root to validate (default: artifacts/reproducible_capsules).",
    )
    args = parser.parse_args(argv)
    root: Path = args.root
    if not root.exists():
        print(f"capsule root not found: {root}", file=sys.stderr)
        return 2

    violations = validate_capsule_root(root)
    if violations:
        print("Capsule secret-boundary violations:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1

    n = sum(1 for _ in _iter_files(root))
    print(f"Capsule secret boundary clean: {n} files structurally validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
