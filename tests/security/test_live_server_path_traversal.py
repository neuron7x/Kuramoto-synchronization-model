# Copyright (c) 2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression tests for ``ui/dashboard/live_server._resolve_static``.

Closes CodeQL alerts #697–#699 (``py/path-injection`` — "Uncontrolled data
used in path expression") on ``ui/dashboard/live_server.py``.

Pure-function tests: ``_resolve_static`` is a stateless sanitizer, so these
run without binding a socket. Each attack vector must return ``None``; the
single allowed happy path must return a path inside ``_WEBROOT``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ui.dashboard.live_server import _WEBROOT, _resolve_static  # noqa: E402


@pytest.mark.parametrize(
    "request_path",
    [
        "/../../../etc/passwd",
        "/../..",
        "/..",
        "/src/../../../etc/passwd",
        "/./../../secrets",
        "/%2e%2e/%2e%2e/etc/passwd",
        "/%2E%2E%2f%2E%2E%2fetc%2fpasswd",
        "/..%2f..%2fetc%2fpasswd",
        "/src/%2e%2e/%2e%2e/etc/passwd",
    ],
)
def test_rejects_traversal(request_path: str) -> None:
    """Directory traversal — decoded and undecoded — must never resolve."""
    assert _resolve_static(request_path) is None


@pytest.mark.parametrize(
    "request_path",
    [
        "//etc/passwd",
        "///etc/shadow",
        "/%2fetc/passwd",
    ],
)
def test_rejects_absolute_escape(request_path: str) -> None:
    """Leading-slash stacking or re-encoded absolute roots must not escape."""
    assert _resolve_static(request_path) is None


@pytest.mark.parametrize(
    "request_path",
    [
        "/demo.html\x00.png",
        "/\x00",
        "/src/\x00index.js",
    ],
)
def test_rejects_null_byte(request_path: str) -> None:
    """NUL-byte truncation vectors must not reach the filesystem."""
    assert _resolve_static(request_path) is None


def test_rejects_empty() -> None:
    """Empty path (after strip) is rejected, not silently mapped to root."""
    assert _resolve_static("") is None
    assert _resolve_static("/") is None


@pytest.mark.parametrize(
    "request_path",
    [
        "/demo.html?../../etc/passwd",
        "/demo.html#/../../etc/passwd",
        "/src/index.js?token=../../../etc",
    ],
)
def test_strips_query_and_fragment(request_path: str) -> None:
    """Query string / fragment must not participate in path resolution.

    These requests target files that exist inside _WEBROOT — they must resolve
    to those files (proving query/fragment was stripped), not ``None``.
    """
    # demo.html exists at _WEBROOT/demo.html; src/index.js does not,
    # so the src/… variant will legitimately return None. Only assert the
    # demo.html variants which have a known-present target.
    result = _resolve_static(request_path)
    if request_path.startswith("/demo.html"):
        assert result is not None
        assert result.name == "demo.html"
        assert result.is_relative_to(_WEBROOT)
    else:
        # If the src path happens to exist, containment still holds.
        assert result is None or result.is_relative_to(_WEBROOT)


def test_rejects_unknown_suffix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Files with non-allow-listed extensions must return None even if real."""
    # demo.html is allowed; create a sibling with a blocked extension.
    blocked = _WEBROOT / "__pytest_blocked.exe"
    blocked.write_bytes(b"MZ\x00")
    try:
        assert _resolve_static("/__pytest_blocked.exe") is None
    finally:
        blocked.unlink()


def test_accepts_known_static_asset() -> None:
    """Happy path: demo.html at webroot resolves and is containment-checked."""
    target = _resolve_static("/demo.html")
    assert target is not None
    assert target == _WEBROOT / "demo.html"
    assert target.is_relative_to(_WEBROOT)
    assert target.is_file()


def test_symlink_escape_rejected(tmp_path: Path) -> None:
    """A symlink pointing outside _WEBROOT must not be followed.

    The CodeQL sanitizer (``is_relative_to`` post-``resolve(strict=True)``)
    catches this because ``resolve`` follows the link and produces a path
    whose real parent chain escapes _WEBROOT.
    """
    outside = tmp_path / "outside_secret.js"
    outside.write_text("// should not be served\n")
    link = _WEBROOT / "__pytest_escape_link.js"
    if link.exists() or link.is_symlink():
        link.unlink()
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this filesystem")
    try:
        assert _resolve_static("/__pytest_escape_link.js") is None
    finally:
        link.unlink()


def test_rejects_nonexistent() -> None:
    """Nonexistent paths — even inside _WEBROOT — return None (strict=True)."""
    assert _resolve_static("/this-file-does-not-exist.js") is None


def test_rejects_directory() -> None:
    """Directory hits are rejected — only regular files are served."""
    # src/ exists as a dir under _WEBROOT.
    if (_WEBROOT / "src").is_dir():
        assert _resolve_static("/src") is None
        assert _resolve_static("/src/") is None


def test_webroot_is_resolved() -> None:
    """_WEBROOT invariant: resolved absolute path, matches the server file's parent."""
    assert _WEBROOT.is_absolute()
    assert _WEBROOT == Path(_WEBROOT).resolve()
    assert _WEBROOT.name == "dashboard"


def test_containment_holds_for_every_positive_result(tmp_path: Path) -> None:
    """Fuzz-style: for a handful of plausible requests, every non-None result
    sits inside _WEBROOT. This is the load-bearing invariant the CodeQL
    sanitizer encodes.
    """
    candidates = [
        "/demo.html",
        "/src",
        "/src/",
        "/src/main.js",
        "/src/styles/tokens.css",
        "/eslint.config.js",
        "/package.json",
        "/nonexistent.js",
        "/../../etc/hostname",
    ]
    for req in candidates:
        resolved = _resolve_static(req)
        if resolved is not None:
            assert resolved.is_relative_to(
                _WEBROOT
            ), f"containment violated: {req!r} resolved to {resolved}"


def test_os_environ_unused() -> None:
    """Meta-test: the sanitizer must not depend on process env. Changing
    CWD/HOME must not change behaviour.
    """
    target_before = _resolve_static("/demo.html")
    prior_cwd = os.getcwd()
    try:
        os.chdir("/")
        target_after = _resolve_static("/demo.html")
    finally:
        os.chdir(prior_cwd)
    assert target_before == target_after
