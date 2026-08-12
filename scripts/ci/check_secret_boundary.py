#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed secret & sensitive-data boundary gate (SEC-006).

A repository has a *secret boundary* only if it can be mechanically proven that
no live credential has crossed it into the committed tree. This gate proves that
property and — crucially — proves that the prover itself has *teeth*: a planted
fake credential must be detected, otherwise the whole exercise is theatre.

It enforces four independent invariants:

    1. NO HIGH-CONFIDENCE SECRET  — after subtracting a documented allowlist of
       placeholder/fixture/baseline surfaces, the scanner finds zero credentials
       in the working tree.
    2. ENV EXAMPLE IS PLACEHOLDER-ONLY  — ``.env.example`` carries no real-looking
       value; every credential slot is a visible placeholder.
    3. SCANNER HAS TEETH  — a negative fixture (a planted fake, non-example AWS
       key + PEM private-key block) is DETECTED by the same scan path. A scanner
       that cannot catch a planted secret cannot vouch for a clean tree.
    4. NO SECRET IN THE AUDIT ARTIFACT  — the emitted report records only path +
       rule + a redacted match; it never persists a raw secret value.

Scanner selection (in order):
    * ``gitleaks`` binary + repo ``.gitleaks.toml`` (preferred; mature ruleset and
      the repo's own allowlist / .gitleaksignore are honored by gitleaks itself);
    * else a focused high-signal regex fallback (AWS keys, PEM private-key blocks,
      bearer tokens, ``password=``/``api_key=`` with real-looking values). The
      fallback is deliberately conservative and skips placeholder values.

The allowlist is by *surface root*, documented in docs/SECRET_BOUNDARY_POLICY.md:
    * ``.github/detect-secrets.baseline`` — detect-secrets' own hashed baseline;
    * ``docs/``                          — documentation examples (example.com);
    * ``tests/``                         — test fixtures (planted fakes for the
                                           security suites themselves);
    * ``scripts/eval/fixtures/``         — red-team fixtures (deliberately fake).
A credential in any *other* path (application, runtime, configs, core, a stray
``.env``) is high-confidence and fails the gate. This is the deliberate residual:
the gate trusts the four fixture/doc surfaces to hold only fakes and does not
deep-verify them; it has full teeth everywhere else, which is where a real leak
would land.

Exit codes:
    0  — clean tree + placeholder-only env example + negative fixture detected
    1  — a high-confidence secret found, a real value in .env.example, or the
         scanner failed to detect the planted negative fixture (no teeth)
    2  — required file/tooling missing or malformed (fail-closed)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

# --- allowlisted surface roots (paths relative to repo root) --------------------
ALLOWLIST_PREFIXES: tuple[str, ...] = (
    ".github/detect-secrets.baseline",
    "docs/",
    "tests/",
    "scripts/eval/fixtures/",
)

# --- placeholder tokens: a value containing any of these is NOT a real secret ---
_PLACEHOLDER_TOKENS = (
    "change", "replace", "your_", "your-", "_here", "example", "placeholder",
    "dummy", "todo", "provide_", "optional_", "xxx", "redact", "changeme",
    "<", ">", "${", "sample", "fixme", "insert_", "notreal", "fake",
)

# --- high-signal regex fallback (used only when gitleaks is unavailable) --------
# AWS access key id, excluding the documented AKIAIOSFODNN7EXAMPLE-style examples.
_RE_AWS = re.compile(r"\b((?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA)[0-9A-Z]{16})\b")
_RE_PEM = re.compile(
    r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----"
)
_RE_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]{20,}={0,2}")
_RE_STRIPE_LIVE = re.compile(r"\b(?:sk|rk)_live_[0-9A-Za-z]{16,}\b")
_RE_ASSIGN = re.compile(
    r"(?i)(?:api[_-]?key|secret[_-]?key|secret|token|password|passwd|pwd|"
    r"access[_-]?key)\s*[:=]\s*['\"]?([A-Za-z0-9/+=_\-]{16,})['\"]?"
)

_BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".gz", ".whl", ".so",
    ".pyc", ".npy", ".npz", ".parquet", ".bin", ".ico", ".woff", ".woff2",
}


def _fingerprint(secret: str) -> str:
    """Return a redacted, non-reversible fingerprint of a secret value."""
    return "sha256:" + hashlib.sha256(secret.encode("utf-8", "replace")).hexdigest()[:12]


def _is_placeholder(value: str) -> bool:
    low = value.lower()
    return any(tok in low for tok in _PLACEHOLDER_TOKENS)


def _norm_rel(rel_path: str) -> str:
    rel = rel_path.replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def _is_allowlisted(rel_path: str) -> bool:
    return _norm_rel(rel_path).startswith(ALLOWLIST_PREFIXES)


# --- scanner backends -----------------------------------------------------------

def gitleaks_available() -> bool:
    return shutil.which("gitleaks") is not None


def _gitleaks_version() -> str:
    try:
        out = subprocess.run(
            ["gitleaks", "version"], capture_output=True, text=True, timeout=30
        )
        return (out.stdout or out.stderr).strip().splitlines()[0] if out.stdout or out.stderr else "unknown"
    except Exception:  # pragma: no cover - defensive
        return "unknown"


def scan_with_gitleaks(source: Path, config: Path | None) -> list[dict[str, Any]]:
    """Run ``gitleaks detect --no-git --redact`` over ``source``; return findings.

    ``--redact`` guarantees no raw secret is emitted into the JSON we parse, so no
    raw credential ever enters this process.
    """
    with tempfile.TemporaryDirectory() as td:
        report = Path(td) / "report.json"
        cmd = [
            "gitleaks", "detect", "--no-git", "--redact",
            "--source", str(source),
            "--report-format", "json",
            "--report-path", str(report),
        ]
        if config is not None and config.exists():
            cmd += ["--config", str(config)]
        subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if not report.exists():
            return []
        raw = report.read_text(encoding="utf-8").strip()
        if not raw:
            return []
        data = json.loads(raw)
    findings: list[dict[str, Any]] = []
    for item in data:
        findings.append(
            {
                "file": item.get("File", ""),
                "line": item.get("StartLine", 0),
                "rule": item.get("RuleID", "unknown"),
                "match": item.get("Match", "")[:80],  # already redacted by gitleaks
            }
        )
    return findings


def _iter_files(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    files: list[Path] = []
    for root, dirs, names in os.walk(source):
        dirs[:] = [
            d for d in dirs
            if d not in {".git", "__pycache__", ".venv", "venv", "node_modules",
                         ".mypy_cache", ".ruff_cache", ".pytest_cache"}
        ]
        for name in names:
            p = Path(root) / name
            if p.suffix.lower() in _BINARY_EXT:
                continue
            files.append(p)
    return files


def scan_with_regex(source: Path) -> list[dict[str, Any]]:
    """Focused high-signal regex fallback. Returns redacted findings."""
    findings: list[dict[str, Any]] = []
    for path in _iter_files(source):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for rule, rx in (("aws-access-token", _RE_AWS),
                             ("private-key", _RE_PEM),
                             ("bearer-token", _RE_BEARER),
                             ("stripe-live", _RE_STRIPE_LIVE)):
                m = rx.search(line)
                if m:
                    secret = m.group(0)
                    if rule == "aws-access-token" and "EXAMPLE" in secret:
                        continue
                    findings.append({
                        "file": str(path), "line": lineno, "rule": rule,
                        "match": _fingerprint(secret),
                    })
            m = _RE_ASSIGN.search(line)
            if m and not _is_placeholder(m.group(1)):
                findings.append({
                    "file": str(path), "line": lineno, "rule": "generic-api-key",
                    "match": _fingerprint(m.group(1)),
                })
    return findings


def scan(source: Path, config: Path | None) -> tuple[list[dict[str, Any]], str]:
    """Scan ``source`` with the preferred backend. Returns (findings, scanner)."""
    if gitleaks_available():
        return scan_with_gitleaks(source, config), f"gitleaks ({_gitleaks_version()})"
    return scan_with_regex(source), "regex-fallback"


# --- .env.example placeholder audit --------------------------------------------

_ENV_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)\s*=\s*(.*)$")
# values that look real but are actually one-way hashes or documented hosts
_ENV_ADVISORY_HINTS = ("$2a$", "$2b$", "$2y$", "$argon2", "$pbkdf2")


def audit_env_example(path: Path) -> dict[str, Any]:
    """Verify ``.env.example`` holds only placeholder values.

    Returns a dict with ``real_values`` (blocking) and ``advisories`` (non-blocking,
    e.g. a concrete one-way password hash shipped as a demo default).
    """
    result: dict[str, Any] = {"file": path.name, "real_values": [], "advisories": []}
    if not path.exists():
        result["status"] = "MISSING"
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = _ENV_LINE.match(s)
        if not m:
            continue
        key, raw = m.group(1), m.group(2)
        value = raw.split("#", 1)[0].strip().strip('"').strip("'")
        if not value or _is_placeholder(value):
            continue
        # one-way hash shipped as a demo default: not a live credential, but ideally
        # a placeholder — surface as advisory, not a hard failure.
        if any(h in value for h in _ENV_ADVISORY_HINTS):
            result["advisories"].append({
                "key": key,
                "note": "concrete one-way hash shipped as demo default; prefer a placeholder",
                "fingerprint": _fingerprint(value),
            })
            continue
        # High-signal only: a value that trips the secret scanner is a real leak.
        for rule, rx in (("aws-access-token", _RE_AWS), ("private-key", _RE_PEM),
                         ("bearer-token", _RE_BEARER), ("stripe-live", _RE_STRIPE_LIVE)):
            if rx.search(value) and not (rule == "aws-access-token" and "EXAMPLE" in value):
                result["real_values"].append({"key": key, "rule": rule,
                                              "fingerprint": _fingerprint(value)})
    result["status"] = "OK" if not result["real_values"] else "LEAK"
    return result


# --- negative fixture (proves the scanner has teeth) ---------------------------

# A planted fake, non-example AWS key + a synthetic PEM block. NOT a real secret.
# Every constant is ASSEMBLED FROM FRAGMENTS so that no literal credential (and no
# `secret = "..."` keyword pairing, no intact PEM header) rests in this source file
# — otherwise the gate would flag its own negative fixture. The fragments only ever
# form a complete token at runtime, inside negative_fixture_text().
_NEG_AWS_ID = "AKIA" + "4ZKJQX7NRTVWLMPD"        # non-example AWS access key id
_NEG_AWS_SK = "7Hk9Lp2QwErTy8UiOp3a" + "SdFgHjKlZxCvBnM4qWeR"  # 40 chars, synthetic
_PEM_BEGIN = "-----" + "BEGIN RSA PRIVATE KEY" + "-----"
_PEM_END = "-----" + "END RSA PRIVATE KEY" + "-----"
_PEM_BODY = "MIIEpAIBAAKCAQEA" + ("Zm9vYmFyMTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1u" * 3)


def negative_fixture_text() -> str:
    """Materialize the planted fake credential (AWS key + PEM) — runtime only."""
    pem = f"{_PEM_BEGIN}\n{_PEM_BODY}\n{_PEM_END}\n"
    return (
        f"AWS_ACCESS_KEY_ID = {_NEG_AWS_ID}\n"
        f"AWS_SECRET_ACCESS_KEY = {_NEG_AWS_SK}\n"
        f"{pem}"
    )


def run_negative_selftest(config: Path | None) -> bool:
    """Plant the fake credential in a temp file, scan it, return True iff detected."""
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "planted_fake_credential.txt"
        f.write_text(negative_fixture_text(), encoding="utf-8")
        findings, _ = scan(Path(td), config)
    return len(findings) > 0


# --- report + gate --------------------------------------------------------------

def _rel_to_repo(file_path: str) -> str:
    """Return ``file_path`` relative to the repo root (gitleaks emits absolute)."""
    try:
        return str(Path(file_path).resolve().relative_to(REPO_ROOT))
    except (ValueError, OSError):
        return _norm_rel(file_path)


def _git_ignored(rel_paths: list[str]) -> set[str]:
    """Return the subset of ``rel_paths`` that git ignores (compiled/VCS noise).

    The gate protects the *committable* tree; VCS-ignored artifacts (``__pycache__``
    bytecode, local ``.env``, caches) are never committed and are out of scope.
    Note: the Python compiler constant-folds split string fragments, so a ``.pyc``
    of this very module would otherwise resurrect an intact PEM header — filtering
    ignored paths is what keeps the gate from flagging its own bytecode.
    """
    if not rel_paths:
        return set()
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "check-ignore", "--stdin"],
            input="\n".join(rel_paths), capture_output=True, text=True, timeout=60,
        )
        return {_norm_rel(p) for p in proc.stdout.splitlines() if p.strip()}
    except Exception:  # pragma: no cover - defensive: fall back to heuristic
        return {p for p in rel_paths if "__pycache__/" in p or p.endswith(".pyc")}


def build_audit(findings: list[dict[str, Any]], scanner: str,
                env_audit: dict[str, Any], neg_detected: bool,
                head_rev: str | None) -> dict[str, Any]:
    # Normalize to repo-relative paths so the allowlist matches regardless of how
    # the scanner reported them (gitleaks --source <abs> yields absolute paths).
    findings = [{**f, "file": _rel_to_repo(f["file"])} for f in findings]
    # Drop VCS-ignored artifacts (bytecode, caches, local .env): out of scope for
    # the committable tree the boundary protects.
    ignored = _git_ignored([f["file"] for f in findings])
    findings = [f for f in findings if f["file"] not in ignored]
    allowlisted = [f for f in findings if _is_allowlisted(f["file"])]
    high_conf = [f for f in findings if not _is_allowlisted(f["file"])]

    by_surface: dict[str, int] = {}
    for f in allowlisted:
        rel = _norm_rel(f["file"])
        root = next((p for p in ALLOWLIST_PREFIXES if rel.startswith(p)), "other")
        by_surface[root] = by_surface.get(root, 0) + 1

    env_ok = env_audit.get("status") in ("OK", "MISSING")
    verdict = "PASS" if (not high_conf and env_ok and neg_detected) else "FAIL"

    return {
        "audit_id": "SEC-006",
        "verdict": verdict,
        "scanner": scanner,
        "scanned_rev": head_rev,
        "surfaces": {
            "working_tree": "SCANNED",
            "notebooks": "SCANNED (part of working tree; under docs/ allowlist)",
            "logs": "SCANNED (part of working tree)",
            "fixtures": "SCANNED (allowlisted: planted fakes for the security suites)",
            "git_history": "NOT_SCANNED (bounded; see residuals)",
            "bundle": "NONE_PRESENT",
        },
        "totals": {
            "raw_findings": len(findings),
            "allowlisted": len(allowlisted),
            "high_confidence": len(high_conf),
        },
        "allowlisted_by_surface": by_surface,
        "findings": high_conf,  # redacted; empty on a clean tree
        "env_example": env_audit,
        "negative_fixture_detected": neg_detected,
        "residuals": [
            "git-history / reflog / packed objects are NOT scanned (--no-git); a "
            "credential that existed only in a rewritten past commit would be missed. "
            "Run `gitleaks detect` (git mode) or `gitleaks detect --no-git` on a full "
            "clone for deep-history coverage.",
            "The four allowlisted surface roots (detect-secrets baseline, docs/, "
            "tests/, scripts/eval/fixtures/) are trusted to contain only placeholder / "
            "planted-fake tokens and are not deep-verified; a real secret committed "
            "into one of them would be allowlisted. The gate has full teeth on every "
            "other path (application, runtime, configs, core, stray .env).",
        ],
    }


def _head_rev() -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30,
        )
        return out.stdout.strip() or None
    except Exception:  # pragma: no cover - defensive
        return None


def run_gate(write: bool = True, out_path: Path | None = None) -> tuple[int, dict[str, Any]]:
    config = REPO_ROOT / ".gitleaks.toml"
    findings, scanner = scan(REPO_ROOT, config if config.exists() else None)
    env_audit = audit_env_example(REPO_ROOT / ".env.example")
    neg_detected = run_negative_selftest(config if config.exists() else None)
    audit = build_audit(findings, scanner, env_audit, neg_detected, _head_rev())

    if write:
        target = out_path or (REPO_ROOT / "artifacts" / "security" / "secret_audit.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return (0 if audit["verdict"] == "PASS" else 1), audit


def _print_summary(audit: dict[str, Any]) -> None:
    t = audit["totals"]
    print(f"[SEC-006] scanner={audit['scanner']} verdict={audit['verdict']}")
    print(f"  raw={t['raw_findings']} allowlisted={t['allowlisted']} "
          f"high_confidence={t['high_confidence']}")
    print(f"  .env.example: {audit['env_example'].get('status')}, "
          f"advisories={len(audit['env_example'].get('advisories', []))}")
    print(f"  negative_fixture_detected: {audit['negative_fixture_detected']}")
    for f in audit["findings"]:
        print(f"  HIGH-CONFIDENCE SECRET: {f['file']}:{f['line']} [{f['rule']}] {f['match']}")
    if audit["env_example"].get("real_values"):
        for r in audit["env_example"]["real_values"]:
            print(f"  ENV LEAK: {r['key']} [{r['rule']}] {r['fingerprint']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SEC-006 secret & sensitive-data boundary gate")
    ap.add_argument("--target", type=Path, default=None,
                    help="Scan an arbitrary file/dir with NO allowlist; exit non-zero on "
                         "any finding. Used by the negative-fixture test to prove teeth.")
    ap.add_argument("--self-test", action="store_true",
                    help="Only run the negative-fixture self-check; exit 0 iff detected.")
    ap.add_argument("--no-write", action="store_true",
                    help="Do not write the audit artifact (used by tests).")
    ap.add_argument("--out", type=Path, default=None, help="Override audit artifact path.")
    args = ap.parse_args(argv)

    config = REPO_ROOT / ".gitleaks.toml"
    config = config if config.exists() else None

    if args.self_test:
        detected = run_negative_selftest(config)
        print(f"[SEC-006] negative fixture detected: {detected}")
        return 0 if detected else 1

    if args.target is not None:
        if not args.target.exists():
            print(f"[SEC-006] target not found: {args.target}", file=sys.stderr)
            return 2
        findings, scanner = scan(args.target, config)
        print(f"[SEC-006] scanner={scanner} target={args.target} findings={len(findings)}")
        for f in findings:
            print(f"  {f['file']}:{f['line']} [{f['rule']}] {f['match']}")
        return 1 if findings else 0

    try:
        code, audit = run_gate(write=not args.no_write, out_path=args.out)
    except FileNotFoundError as exc:
        print(f"[SEC-006] fail-closed: {exc}", file=sys.stderr)
        return 2
    _print_summary(audit)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
