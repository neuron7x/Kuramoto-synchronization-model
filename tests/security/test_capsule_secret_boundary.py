# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the capsule secret-boundary validator (TASK 931).

The validator replaces a detect-secrets exclude zone with deterministic
structural validation. These tests prove it accepts a clean capsule and rejects
every smuggling vector: fake credentials, private keys, unbound high-entropy
tokens, binaries, hidden files, symlinks, and disallowed file types.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "security" / "validate_capsule_secret_boundary.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("vcsb_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vcsb = _load()


def _clean_capsule(root: Path) -> None:
    """A minimal structurally-clean capsule."""
    bundle = root / "cap" / "bundle"
    bundle.mkdir(parents=True)
    (root / "cap" / "manifest.json").write_text(
        '{"sha256": "' + "a" * 64 + '", "note": "clean"}\n', encoding="utf-8"
    )
    (root / "cap" / "README.md").write_text("# Capsule\nclean text only.\n", encoding="utf-8")
    (bundle / "SHA256SUMS").write_text("a" * 64 + "  data.json\n", encoding="utf-8")


def test_clean_capsule_passes(tmp_path: Path) -> None:
    _clean_capsule(tmp_path)
    assert vcsb.validate_capsule_root(tmp_path) == []


def test_digest_under_approved_field_passes(tmp_path: Path) -> None:
    (tmp_path / "m.json").write_text('{"artifact_sha256": "' + "b" * 64 + '"}\n', encoding="utf-8")
    assert vcsb.validate_file(tmp_path / "m.json", tmp_path) == []


def test_fake_api_key_fails(tmp_path: Path) -> None:
    (tmp_path / "leak.json").write_text(
        '{"aws": "AKIAIOSFODNN7EXAMPLE"}\n',  # pragma: allowlist secret
        encoding="utf-8",
    )
    violations = vcsb.validate_file(tmp_path / "leak.json", tmp_path)
    assert any("AWS access key id" in v for v in violations)


def test_private_key_block_fails(tmp_path: Path) -> None:
    (tmp_path / "key.txt").write_text(
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n"  # pragma: allowlist secret
        "-----END RSA PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    violations = vcsb.validate_file(tmp_path / "key.txt", tmp_path)
    assert any("private key block" in v for v in violations)


def test_random_token_under_non_digest_field_fails(tmp_path: Path) -> None:
    (tmp_path / "leak.json").write_text(
        '{"session": "aB3xK9pQ2mZ7wL5nR8tVcD1eF0gH7iJ"}\n',  # pragma: allowlist secret
        encoding="utf-8",
    )
    violations = vcsb.validate_file(tmp_path / "leak.json", tmp_path)
    assert any("high-entropy token under non-digest field" in v for v in violations)


def test_credential_assignment_in_text_fails(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text(
        "config:\napi_key = sk_live_0123456789abcdefABCDEF\n", encoding="utf-8"
    )
    violations = vcsb.validate_file(tmp_path / "notes.md", tmp_path)
    assert any("credential assignment" in v for v in violations)


def test_binary_file_fails(tmp_path: Path) -> None:
    (tmp_path / "blob.json").write_bytes(b'{"x": "\x00\x01\x02"}')
    violations = vcsb.validate_file(tmp_path / "blob.json", tmp_path)
    assert any("binary content" in v for v in violations)


def test_hidden_file_fails(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SECRET=abc\n", encoding="utf-8")
    violations = vcsb.validate_file(tmp_path / ".env", tmp_path)
    assert any("hidden files" in v for v in violations)


def test_unknown_extension_fails(tmp_path: Path) -> None:
    (tmp_path / "payload.bin").write_text("data\n", encoding="utf-8")
    violations = vcsb.validate_file(tmp_path / "payload.bin", tmp_path)
    assert any("disallowed file type" in v for v in violations)


def test_symlink_fails(tmp_path: Path) -> None:
    target = tmp_path / "real.json"
    target.write_text("{}\n", encoding="utf-8")
    link = tmp_path / "link.json"
    os.symlink(target, link)
    violations = vcsb.validate_file(link, tmp_path)
    assert any("symlinks are forbidden" in v for v in violations)


def test_slash_base64_secret_under_non_digest_field_fails(tmp_path: Path) -> None:
    """Regression: a standard-alphabet base64 secret (contains '/') under a
    non-digest key must be caught by the JSON token walk.

    Before the fix, _TOKEN_RE excluded '/', so an AWS secret-access-key shape
    slipped through entirely (the gate reported the capsule clean)."""
    (tmp_path / "leak.json").write_text(
        # AWS secret-access-key shape: 40 chars, base64 alphabet incl. '/'.
        '{"api_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"}\n',  # pragma: allowlist secret
        encoding="utf-8",
    )
    violations = vcsb.validate_file(tmp_path / "leak.json", tmp_path)
    assert any("high-entropy token under non-digest field" in v for v in violations)


def test_json_quoted_credential_assignment_fails(tmp_path: Path) -> None:
    """Regression: a credential assignment in JSON form ('"api_key": "…"') must
    be caught by the signature even when the value is below the token-walk
    length floor. The closing quote between the key and the colon previously
    defeated the signature regex."""
    (tmp_path / "leak.json").write_text(
        '{"api_key": "hunter2hunter2hunter2"}\n',  # pragma: allowlist secret
        encoding="utf-8",
    )
    violations = vcsb.validate_file(tmp_path / "leak.json", tmp_path)
    assert any("credential assignment" in v for v in violations)


def test_git_ref_under_non_digest_field_is_not_flagged(tmp_path: Path) -> None:
    """Regression: adding '/' to _TOKEN_RE (so slash-bearing secrets are caught)
    must NOT false-positive on a git ref / kebab path. Such values are
    single-case and fail the character-class-diversity bar, so a legitimate
    capsule carrying provenance like a branch ref under a non-digest field stays
    clean."""
    (tmp_path / "prov.json").write_text(
        '{"git_ref": "refs/heads/fix/kuramoto-damped-velocity-verlet-bbk"}\n',
        encoding="utf-8",
    )
    assert vcsb.validate_file(tmp_path / "prov.json", tmp_path) == []


def test_charclass_diversity_distinguishes_secret_from_path() -> None:
    """A base64 random blob (lower+upper+digit) is token-like; a single-case
    slash path/ref is not — even though both match the charset and clear the
    entropy floor."""
    secret_shape = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"  # pragma: allowlist secret
    assert vcsb._is_token_like(secret_shape) is True
    assert vcsb._is_token_like("refs/heads/fix/kuramoto-damped-velocity-verlet-bbk") is False


def test_real_committed_capsule_is_clean() -> None:
    """The actual repository capsule must pass the boundary with zero violations."""
    capsule_root = ROOT / "artifacts" / "reproducible_capsules"
    assert vcsb.validate_capsule_root(capsule_root) == []


def test_cli_exit_codes(tmp_path: Path) -> None:
    _clean_capsule(tmp_path)
    assert vcsb.main(["--root", str(tmp_path)]) == 0
    (tmp_path / "leak.json").write_text(
        '{"oops": "aB3xK9pQ2mZ7wL5nR8tVcD1eF0gH7iJ"}\n',  # pragma: allowlist secret
        encoding="utf-8",
    )
    assert vcsb.main(["--root", str(tmp_path)]) == 1
    assert vcsb.main(["--root", str(tmp_path / "does-not-exist")]) == 2
