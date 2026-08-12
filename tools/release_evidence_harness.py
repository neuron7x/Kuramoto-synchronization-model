#!/usr/bin/env python3
"""Generate semantic release-gate evidence with raw logs and exit codes.

A release gate is not a decorative command transcript.  Each required gate maps
to one command, one raw log, one exit code, and optional semantic checks over
stdout.  The harness bounds log growth, validates deterministic timestamps, and
marks dirty-tree output as RED even when git itself exits 0.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import selectors
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SEMANTIC_NON_EMPTY_OUTPUT = "non-empty output is a release-blocking semantic failure"
SEMANTIC_LOG_TRUNCATED = "command output exceeded max log bytes"
GATE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization:\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)((?:token|password|secret|api[_-]?key)=)[^\s]+"),
]
HIGH_ENTROPY_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9+/=_-])([A-Za-z0-9+/=_-]{20,})(?![A-Za-z0-9+/=_-])"
)
SECRET_ENTROPY_THRESHOLD = 3.7
SECRET_MIN_TOKEN_LENGTH = 20
SECRET_WHITELIST_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
UTC_Z_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
MIN_TIMESTAMP_UTC = datetime(2026, 1, 1)
MAX_TIMESTAMP_UTC = datetime(2030, 1, 1)
CYCLONEDX_BOM_FORMAT = "CycloneDX"
CYCLONEDX_SPEC_VERSION = "1.5"
BUNDLE_TOP_LEVEL_ARTIFACTS = {
    "manifest.json",
    "manifest.json.asc",
    "sbom.cdx.json",
    "audit_report.pdf",
    "ci_status.json",
}
GPG_BINARY_ALLOWLIST = {"/usr/bin/gpg", "/bin/gpg", "/usr/local/bin/gpg", "/opt/homebrew/bin/gpg"}


@dataclass(frozen=True)
class Gate:
    name: str
    command: list[str]
    required: bool = True
    fail_on_output: bool = False


@dataclass(frozen=True)
class GateResult:
    name: str
    status: str
    command: list[str]
    exit_code: int
    evidence: Path
    required: bool
    started_utc: str
    finished_utc: str
    semantic_failure: str | None = None
    evidence_sha256: str | None = None
    evidence_bytes: int = 0
    output_truncated: bool = False
    environment_sha256: str | None = None
    environment_status: str = "RECORDED"
    environment_failure: str | None = None


def _validate_utc_timestamp(timestamp_utc: str) -> str:
    try:
        parsed = datetime.strptime(timestamp_utc, UTC_Z_FORMAT)
    except ValueError as exc:
        msg = f"timestamp must be UTC in YYYY-MM-DDTHH:MM:SSZ form: {timestamp_utc!r}"
        raise ValueError(msg) from exc
    if not (MIN_TIMESTAMP_UTC <= parsed <= MAX_TIMESTAMP_UTC):
        msg = (
            "timestamp must be within the supported release evidence range "
            f"{MIN_TIMESTAMP_UTC.strftime(UTC_Z_FORMAT)}..{MAX_TIMESTAMP_UTC.strftime(UTC_Z_FORMAT)}: {timestamp_utc!r}"
        )
        raise ValueError(msg)
    return parsed.strftime(UTC_Z_FORMAT)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).strftime(UTC_Z_FORMAT)


def _fixed_clock(timestamp_utc: str) -> Callable[[], str]:
    validated = _validate_utc_timestamp(timestamp_utc)

    def _now() -> str:
        return validated

    return _now


def _shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    return -sum(
        (count / len(value)) * math.log2(count / len(value))
        for count in (value.count(char) for char in set(value))
    )


def _looks_like_secret_token(token: str) -> bool:
    if len(token) < SECRET_MIN_TOKEN_LENGTH:
        return False
    if SECRET_WHITELIST_PATTERN.fullmatch(token) and _shannon_entropy(token) < 4.2:
        return False
    return _shannon_entropy(token) >= SECRET_ENTROPY_THRESHOLD


def _redact_high_entropy_tokens(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        token = match.group(1)
        return "[REDACTED]" if _looks_like_secret_token(token) else token

    return HIGH_ENTROPY_TOKEN_PATTERN.sub(_replace, text)


def _redact_text(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(r"\1[REDACTED]", redacted)
    return _redact_high_entropy_tokens(redacted)


def _quote_command(command: list[str]) -> str:
    return _redact_text(" ".join(shlex.quote(part) for part in command))


def _validate_gate_name(name: str) -> str:
    if GATE_NAME_PATTERN.fullmatch(name) is None:
        msg = f"invalid gate name: {name!r}"
        raise ValueError(msg)
    return name


def _file_sha256(path: Path) -> tuple[str, int]:
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


@contextmanager
def _file_lock(lock_path: Path) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        import fcntl

        with lock_path.open("w", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return

    deadline = time.monotonic() + 30
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for file lock: {lock_path}")
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _atomic_write_text(path: Path, text: str) -> None:
    with _file_lock(path.with_name(f".{path.name}.lock")):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)


def _run_process_to_log(
    command: list[str],
    handle,
    timeout_sec: int,
    max_log_bytes: int,
) -> tuple[int, bool, bool]:
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert proc.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    deadline = datetime.now(UTC).timestamp() + timeout_sec
    written = 0
    saw_output = False
    truncated = False

    while True:
        remaining_time = deadline - datetime.now(UTC).timestamp()
        if remaining_time <= 0:
            proc.kill()
            proc.wait()
            handle.write(f"\nTIMEOUT after {timeout_sec}s\n")
            selector.close()
            return 124, saw_output, truncated

        events = selector.select(timeout=min(0.1, remaining_time))
        for key, _ in events:
            chunk = key.fileobj.read1(8192)
            if not chunk:
                continue
            saw_output = True
            remaining_bytes = max_log_bytes - written
            if remaining_bytes > 0:
                decoded = _redact_text(chunk[:remaining_bytes].decode("utf-8", errors="replace"))
                handle.write(decoded)
                written += len(chunk[:remaining_bytes])
            if len(chunk) > max(remaining_bytes, 0):
                truncated = True

        exit_code = proc.poll()
        if exit_code is not None:
            for chunk in iter(lambda: proc.stdout.read1(8192), b""):
                saw_output = True
                remaining_bytes = max_log_bytes - written
                if remaining_bytes > 0:
                    decoded = _redact_text(
                        chunk[:remaining_bytes].decode("utf-8", errors="replace")
                    )
                    handle.write(decoded)
                    written += len(chunk[:remaining_bytes])
                if len(chunk) > max(remaining_bytes, 0):
                    truncated = True
            selector.close()
            if truncated:
                handle.write(f"\nLOG_TRUNCATED after {max_log_bytes} bytes\n")
            return exit_code, saw_output, truncated


def _hash_existing_file(path: Path) -> dict[str, object] | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        digest, size = _file_sha256(path)
        return {"path": path.as_posix(), "sha256": digest, "bytes": size}
    except OSError:
        return None


def _environment_fingerprint(command: list[str]) -> dict[str, object]:
    candidates = [Path(sys.executable).resolve()]
    if command:
        resolved = shutil.which(command[0])
        if resolved:
            candidates.append(Path(resolved).resolve())
    for optional in (
        Path("pyproject.toml"),
        Path("schemas/research/research_inference_artifact.schema.json"),
    ):
        if optional.exists():
            candidates.append(optional.resolve())
    files = []
    seen: set[str] = set()
    for candidate in sorted(candidates, key=lambda item: item.as_posix()):
        record = _hash_existing_file(candidate)
        if record is None or str(record["path"]) in seen:
            continue
        seen.add(str(record["path"]))
        files.append(record)
    files = sorted(files, key=lambda item: str(item["path"]))
    payload = {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "executable": sys.executable,
        "files": files,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"sha256": hashlib.sha256(canonical).hexdigest(), "payload": payload}


def _load_environment_baseline(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("environment baseline must be a JSON object")
    fingerprints = data.get("gate_environment_sha256", data)
    if not isinstance(fingerprints, dict):
        raise ValueError("environment baseline gate_environment_sha256 must be an object")
    return {str(key): str(value) for key, value in fingerprints.items()}


def _write_environment_baseline(path: Path, results: list[GateResult]) -> None:
    _write_json(
        path,
        {
            "schema_version": 1,
            "generated_utc": _utc_now(),
            "gate_environment_sha256": {
                result.name: result.environment_sha256 for result in results
            },
        },
    )


def _run_gate(
    gate: Gate,
    log_dir: Path,
    timeout_sec: int,
    clock: Callable[[], str] = _utc_now,
    max_log_bytes: int = 1_000_000,
    environment_baseline: dict[str, str] | None = None,
) -> GateResult:
    gate_name = _validate_gate_name(gate.name)
    log_dir.mkdir(parents=True, exist_ok=True)
    evidence = log_dir / f"{gate_name}.log"
    started = clock()
    semantic_failure: str | None = None
    env = _environment_fingerprint(gate.command)
    environment_sha256 = str(env["sha256"])
    expected_environment_sha256 = (environment_baseline or {}).get(gate.name)
    environment_status = "RECORDED"
    environment_failure: str | None = None
    with _file_lock(evidence.with_name(f".{evidence.name}.lock")):
        with evidence.open("w", encoding="utf-8") as handle:
            handle.write(f"started_utc={started}\n")
            handle.write(f"command={_quote_command(gate.command)}\n")
            handle.write(f"environment_sha256={environment_sha256}\n\n")
            if (
                expected_environment_sha256 is not None
                and expected_environment_sha256 != environment_sha256
            ):
                environment_status = "DRIFT"
                environment_failure = "environment fingerprint drift before gate execution"
                semantic_failure = environment_failure
                exit_code = 1
                output_truncated = False
                handle.write(
                    f"ENVIRONMENT_DRIFT expected={expected_environment_sha256} actual={environment_sha256}\n"
                )
            else:
                exit_code, saw_output, output_truncated = _run_process_to_log(
                    gate.command,
                    handle,
                    timeout_sec,
                    max_log_bytes,
                )
                if output_truncated:
                    semantic_failure = SEMANTIC_LOG_TRUNCATED
                    exit_code = 1
                    handle.write(f"\nSEMANTIC_FAILURE: {semantic_failure}\n")
                elif exit_code == 0 and gate.fail_on_output and saw_output:
                    semantic_failure = SEMANTIC_NON_EMPTY_OUTPUT
                    exit_code = 1
                    handle.write(f"\nSEMANTIC_FAILURE: {semantic_failure}\n")
        finished = clock()
        with evidence.open("a", encoding="utf-8") as handle:
            handle.write(f"\nfinished_utc={finished}\n")
            handle.write(f"exit_code={exit_code}\n")
    status = "GREEN" if exit_code == 0 else "RED"
    evidence_sha256, evidence_bytes = _file_sha256(evidence)
    return GateResult(
        gate.name,
        status,
        gate.command,
        exit_code,
        evidence,
        gate.required,
        started,
        finished,
        semantic_failure,
        evidence_sha256,
        evidence_bytes,
        output_truncated,
        environment_sha256,
        environment_status,
        environment_failure,
    )


def _validate_unique_gate_names(gates: list[Gate]) -> None:
    names = [_validate_gate_name(gate.name) for gate in gates]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"duplicate gate names are not safe for parallel execution: {duplicates}")


async def _run_gates_async(
    gates: list[Gate],
    log_dir: Path,
    timeout_sec: int,
    clock: Callable[[], str],
    max_log_bytes: int,
    environment_baseline: dict[str, str] | None = None,
) -> list[GateResult]:
    _validate_unique_gate_names(gates)
    tasks = [
        asyncio.to_thread(
            _run_gate,
            gate,
            log_dir,
            timeout_sec,
            clock,
            max_log_bytes,
            environment_baseline,
        )
        for gate in gates
    ]
    return list(await asyncio.gather(*tasks))


def _run_gates(
    gates: list[Gate],
    log_dir: Path,
    timeout_sec: int,
    clock: Callable[[], str],
    max_log_bytes: int,
    environment_baseline: dict[str, str] | None = None,
) -> list[GateResult]:
    return asyncio.run(
        _run_gates_async(gates, log_dir, timeout_sec, clock, max_log_bytes, environment_baseline)
    )


def _write_json(path: Path, payload: object) -> None:
    _atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=False) + "\n")


def _yaml_scalar(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value))


def _write_release_gate_yaml(
    path: Path,
    results: list[GateResult],
    clock: Callable[[], str] = _utc_now,
) -> None:
    lines = [
        "schema_version: 1",
        f"generated_utc: {_yaml_scalar(clock())}",
        "gates:",
    ]
    for result in results:
        lines.extend(
            [
                f"  - name: {_yaml_scalar(result.name)}",
                f"    status: {_yaml_scalar(result.status)}",
                f"    required: {_yaml_scalar(result.required)}",
                f"    exit_code: {result.exit_code}",
                f"    command: {_yaml_scalar(_quote_command(result.command))}",
                f"    evidence: {_yaml_scalar(result.evidence.as_posix())}",
                f"    started_utc: {_yaml_scalar(result.started_utc)}",
                f"    finished_utc: {_yaml_scalar(result.finished_utc)}",
                f"    semantic_failure: {_yaml_scalar(result.semantic_failure)}",
                f"    evidence_sha256: {_yaml_scalar(result.evidence_sha256)}",
                f"    evidence_bytes: {result.evidence_bytes}",
                f"    output_truncated: {_yaml_scalar(result.output_truncated)}",
                f"    environment_sha256: {_yaml_scalar(result.environment_sha256)}",
                f"    environment_status: {_yaml_scalar(result.environment_status)}",
                f"    environment_failure: {_yaml_scalar(result.environment_failure)}",
            ]
        )
    _atomic_write_text(path, "\n".join(lines) + "\n")


def _installed_components() -> list[dict[str, object]]:
    components: list[dict[str, object]] = []
    for distribution in sorted(
        importlib.metadata.distributions(), key=lambda item: item.metadata.get("Name", "").lower()
    ):
        name = distribution.metadata.get("Name")
        version = distribution.version
        if not name:
            continue
        components.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "purl": f"pkg:pypi/{name}@{version}",
            }
        )
    return components


def _write_sbom(path: Path, *, clock: Callable[[], str]) -> tuple[str, int]:
    payload = {
        "bomFormat": CYCLONEDX_BOM_FORMAT,
        "specVersion": CYCLONEDX_SPEC_VERSION,
        "version": 1,
        "metadata": {"timestamp": clock(), "component": {"type": "application", "name": "GeoSync"}},
        "components": _installed_components(),
    }
    _write_json(path, payload)
    return _file_sha256(path)


def _minimal_pdf_bytes(title: str, lines: list[str]) -> bytes:
    def esc(value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    text_lines = [title, *lines]
    stream_parts = ["BT", "/F1 10 Tf", "50 780 Td"]
    for index, line in enumerate(text_lines[:55]):
        if index:
            stream_parts.append("0 -14 Td")
        stream_parts.append(f"({esc(line[:110])}) Tj")
    stream_parts.append("ET")
    stream = "\n".join(stream_parts).encode("utf-8")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(stream)).encode("ascii")
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(pdf)


def _write_audit_pdf(
    path: Path, manifest: dict[str, object], results: list[GateResult]
) -> tuple[str, int]:
    lines = [
        f"generated_utc: {manifest.get('generated_utc')}",
        f"valid_gates: {', '.join(str(item) for item in manifest.get('valid_gates', []))}",
        f"failed_required: {', '.join(str(item) for item in manifest.get('failed_required', []))}",
        f"sbom: {manifest.get('sbom', {}).get('path') if isinstance(manifest.get('sbom'), dict) else None}",
    ]
    for result in results:
        lines.append(
            f"{result.name}: {result.status} exit={result.exit_code} evidence={result.evidence.name}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_minimal_pdf_bytes("GeoSync Release Evidence Audit Report", lines))
    return _file_sha256(path)


def _write_telemetry(
    evidence_dir: Path, results: list[GateResult], *, clock: Callable[[], str]
) -> dict[str, object]:
    telemetry_dir = evidence_dir / "telemetry"
    telemetry_dir.mkdir(parents=True, exist_ok=True)
    prometheus = telemetry_dir / "release_gates.prom"
    datadog = telemetry_dir / "datadog_events.json"
    prom_lines = ["# TYPE geosync_release_gate_status gauge"]
    events = []
    for result in results:
        value = 1 if result.status == "GREEN" else 0
        prom_lines.append(
            f'geosync_release_gate_status{{gate="{result.name}",required="{str(result.required).lower()}"}} {value}'
        )
        events.append(
            {
                "title": f"GeoSync gate {result.name} {result.status}",
                "status": result.status,
                "gate": result.name,
                "exit_code": result.exit_code,
                "timestamp_utc": clock(),
            }
        )
    _atomic_write_text(prometheus, "\n".join(prom_lines) + "\n")
    _write_json(datadog, {"series": events})
    prom_sha, prom_bytes = _file_sha256(prometheus)
    dd_sha, dd_bytes = _file_sha256(datadog)
    return {
        "prometheus": {"path": prometheus.as_posix(), "sha256": prom_sha, "bytes": prom_bytes},
        "datadog": {"path": datadog.as_posix(), "sha256": dd_sha, "bytes": dd_bytes},
    }


def _write_ci_status(path: Path, manifest: dict[str, object]) -> tuple[str, int]:
    payload = {
        "schema_version": 1,
        "release_status": "PASS" if not manifest.get("failed_required") else "FAIL",
        "manifest": (path.parent / "manifest.json").as_posix(),
        "failed_required": manifest.get("failed_required", []),
    }
    _write_json(path, payload)
    return _file_sha256(path)


def _allowed_gpg_paths() -> set[Path]:
    paths = {Path(value).resolve() for value in GPG_BINARY_ALLOWLIST}
    resolved = shutil.which("gpg")
    if resolved:
        candidate = Path(resolved).resolve()
        if candidate.as_posix() in GPG_BINARY_ALLOWLIST:
            paths.add(candidate)
    return paths


def _resolve_gpg_binary(gpg_binary: str) -> Path:
    resolved = shutil.which(gpg_binary)
    if resolved is None:
        raise ValueError(f"gpg binary not found: {gpg_binary}")
    candidate = Path(resolved).resolve()
    if candidate not in _allowed_gpg_paths():
        raise ValueError(f"gpg binary is not in allowlist: {candidate}")
    return candidate


def _sign_manifest(
    manifest_path: Path, signature_path: Path, *, gpg_binary: str, gpg_key: str
) -> tuple[bool, str | None, str | None]:
    try:
        resolved_gpg = _resolve_gpg_binary(gpg_binary)
    except ValueError as exc:
        return False, None, str(exc)
    command = [
        resolved_gpg.as_posix(),
        "--batch",
        "--yes",
        "--armor",
        "--detach-sign",
        "--local-user",
        gpg_key,
        "--output",
        str(signature_path),
        str(manifest_path),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        return False, None, _redact_text((completed.stderr or completed.stdout).strip())
    signature_sha, _ = _file_sha256(signature_path)
    return True, signature_sha, None


def _verify_gpg_signature(
    manifest_path: Path, signature_path: Path, *, gpg_binary: str
) -> str | None:
    if not signature_path.is_file():
        return f"missing GPG signature: {signature_path}"
    try:
        resolved_gpg = _resolve_gpg_binary(gpg_binary)
    except ValueError as exc:
        return str(exc)
    completed = subprocess.run(
        [resolved_gpg.as_posix(), "--batch", "--verify", str(signature_path), str(manifest_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return (
            _redact_text((completed.stderr or completed.stdout).strip())
            or "GPG signature verification failed"
        )
    return None


def _default_python() -> str:
    for candidate in (sys.executable, "python3.12", "python3.11"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return sys.executable


def _clean_install_command(clean_python: str) -> list[str]:
    quoted_python = shlex.quote(clean_python)
    return [
        "bash",
        "-lc",
        "set -euo pipefail; tmp=${TMPDIR:-/tmp}/geosync-release-venv; "
        'rm -rf "$tmp"; '
        f'{quoted_python} -m venv "$tmp"; '
        '"$tmp/bin/python" -m pip install -e .; '
        '"$tmp/bin/geosync-research" --help',
    ]


def _default_gates(python: str, clean_python: str, skip_clean_install: bool) -> list[Gate]:
    gates = [
        Gate(
            "diff_summary_clean",
            [
                "git",
                "diff",
                "--stat",
                "--",
                ".",
                ":!release_gate.yaml",
                ":!artifacts/evidence_bundle",
            ],
            fail_on_output=True,
        ),
        Gate(
            "working_tree_clean",
            [
                "git",
                "status",
                "--short",
                "--",
                ".",
                ":!release_gate.yaml",
                ":!artifacts/evidence_bundle",
            ],
            fail_on_output=True,
        ),
        Gate(
            "import_smoke",
            [
                python,
                "-c",
                "import core.neuro.epistemic_audit, runtime.audit_logger, tools.architecture_audit, tools.research.research_cli",
            ],
        ),
        Gate("research_entrypoint_help", [python, "-m", "tools.research.research_cli", "--help"]),
        Gate(
            "ricci_schema_semantic",
            [
                python,
                "tools/research/validate_ricci_artifact_schema.py",
                "--semantic",
                "--schema",
                "schemas/research/research_inference_artifact.schema.json",
                "--artifact",
                "artifacts/runs/ricci_microstructure_v1/example_artifact.json",
            ],
        ),
        Gate(
            "research_artifact_truth",
            [python, "scripts/ci/check_research_artifact_truth.py"],
        ),
        Gate(
            "pytest_release_smoke",
            [
                python,
                "-m",
                "pytest",
                "tests/unit/test_audit_logger.py",
                "tests/research_lines/test_ricci_artifact_schema.py",
                "tests/tools/test_release_evidence_harness.py",
                "tests/tools/test_research_cli.py",
                "-q",
            ],
        ),
    ]
    if not skip_clean_install:
        gates.insert(0, Gate("clean_install", _clean_install_command(clean_python)))
    return gates


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _resolve_evidence_path(manifest_path: Path, evidence_value: object) -> Path:
    if not isinstance(evidence_value, str) or not evidence_value:
        raise ValueError(f"invalid evidence path: {evidence_value!r}")
    path = Path(evidence_value)
    bundle_root = manifest_path.parent.resolve()
    raw_logs_root = (bundle_root / "raw_logs").resolve()
    telemetry_root = (bundle_root / "telemetry").resolve()
    if path.is_absolute():
        candidate = path
    elif path.parts[:2] == ("artifacts", "evidence_bundle"):
        candidate = bundle_root.joinpath(*path.parts[2:])
    else:
        candidate = bundle_root / path
    if not _is_relative_to(candidate, bundle_root):
        raise ValueError(f"evidence path escapes bundle: {evidence_value!r}")
    if (
        candidate.name not in BUNDLE_TOP_LEVEL_ARTIFACTS
        and not _is_relative_to(candidate, raw_logs_root)
        and not _is_relative_to(candidate, telemetry_root)
    ):
        raise ValueError(f"evidence path must be under raw_logs or telemetry: {evidence_value!r}")
    return candidate


def _prepare_logs_dir(logs_dir: Path) -> None:
    if logs_dir.is_symlink():
        raise ValueError(f"refusing to remove symlinked raw_logs directory: {logs_dir}")
    if logs_dir.exists():
        shutil.rmtree(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)


def _verify_artifact_record(
    manifest_path: Path,
    record: object,
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(record, dict):
        errors.append(f"{label} must be an object")
        return
    try:
        path = _resolve_evidence_path(manifest_path, record.get("path"))
    except ValueError as exc:
        errors.append(f"{label}: {exc}")
        return
    if path.is_symlink():
        errors.append(f"{label}: refusing symlinked artifact: {path}")
        return
    if not path.is_file():
        errors.append(f"{label}: missing artifact: {path}")
        return
    actual_sha, actual_bytes = _file_sha256(path)
    if record.get("sha256") != actual_sha:
        errors.append(f"{label}: sha256 mismatch")
    if record.get("bytes") != actual_bytes:
        errors.append(f"{label}: bytes mismatch")


def verify_evidence_manifest(
    manifest_path: Path, *, require_gpg_signature: bool = False, gpg_binary: str = "gpg"
) -> list[str]:
    """Return integrity errors for a release evidence manifest and its raw logs."""
    raw_logs_dir = manifest_path.parent / "raw_logs"
    if raw_logs_dir.is_symlink():
        return [f"refusing symlinked raw_logs directory: {raw_logs_dir}"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"missing manifest: {manifest_path}"]
    except json.JSONDecodeError as exc:
        return [f"invalid manifest JSON: {exc}"]

    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    generated_utc = manifest.get("generated_utc")
    if not isinstance(generated_utc, str):
        errors.append("generated_utc must be a UTC string")
    else:
        try:
            _validate_utc_timestamp(generated_utc)
        except ValueError as exc:
            errors.append(str(exc))

    results = manifest.get("results")
    if not isinstance(results, list):
        return [*errors, "results must be a list"]

    valid_gates: list[str] = []
    failed_required: list[str] = []
    for index, result in enumerate(results):
        if not isinstance(result, dict):
            errors.append(f"results[{index}] must be an object")
            continue
        name = result.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"results[{index}].name must be a non-empty string")
            name = f"<invalid-{index}>"
        exit_code = result.get("exit_code")
        status = result.get("status")
        required = result.get("required")
        if not isinstance(exit_code, int):
            errors.append(f"{name}: exit_code must be an integer")
            continue
        expected_status = "GREEN" if exit_code == 0 else "RED"
        if status != expected_status:
            errors.append(f"{name}: status {status!r} does not match exit_code {exit_code}")
        if exit_code == 0:
            valid_gates.append(name)
        if required is True and exit_code != 0:
            failed_required.append(name)

        for field in ("started_utc", "finished_utc"):
            value = result.get(field)
            if not isinstance(value, str):
                errors.append(f"{name}: {field} must be a UTC string")
            else:
                try:
                    _validate_utc_timestamp(value)
                except ValueError as exc:
                    errors.append(f"{name}: {exc}")

        try:
            evidence_path = _resolve_evidence_path(manifest_path, result.get("evidence"))
        except ValueError as exc:
            errors.append(f"{name}: {exc}")
            continue
        if evidence_path.is_symlink():
            errors.append(f"{name}: refusing symlinked evidence file: {evidence_path}")
            continue
        if not evidence_path.is_file():
            errors.append(f"{name}: missing evidence file: {evidence_path}")
            continue
        actual_sha, actual_bytes = _file_sha256(evidence_path)
        if result.get("evidence_sha256") != actual_sha:
            errors.append(f"{name}: evidence_sha256 mismatch")
        if result.get("evidence_bytes") != actual_bytes:
            errors.append(f"{name}: evidence_bytes mismatch")

    if manifest.get("valid_gates") != valid_gates:
        errors.append("valid_gates does not match result exit codes")
    if manifest.get("failed_required") != failed_required:
        errors.append("failed_required does not match required result exit codes")

    _verify_artifact_record(manifest_path, manifest.get("sbom"), "sbom", errors)
    _verify_artifact_record(manifest_path, manifest.get("audit_report"), "audit_report", errors)
    _verify_artifact_record(manifest_path, manifest.get("ci_status"), "ci_status", errors)
    telemetry = manifest.get("telemetry")
    if isinstance(telemetry, dict):
        _verify_artifact_record(
            manifest_path, telemetry.get("prometheus"), "telemetry.prometheus", errors
        )
        _verify_artifact_record(
            manifest_path, telemetry.get("datadog"), "telemetry.datadog", errors
        )
    else:
        errors.append("telemetry must be an object")

    signature = manifest.get("gpg_signature")
    if require_gpg_signature:
        if not isinstance(signature, dict) or not signature.get("path"):
            errors.append("missing required gpg_signature metadata")
        else:
            try:
                signature_path = _resolve_evidence_path(manifest_path, signature.get("path"))
            except ValueError as exc:
                errors.append(f"gpg_signature: {exc}")
            else:
                error = _verify_gpg_signature(manifest_path, signature_path, gpg_binary=gpg_binary)
                if error is not None:
                    errors.append(f"gpg_signature: {error}")
    return errors


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-manifest",
        type=Path,
        help="Verify an existing evidence manifest and raw logs without running gates.",
    )
    parser.add_argument(
        "--require-gpg-signature",
        action="store_true",
        help="Require and verify manifest.json.asc when verifying a manifest.",
    )
    parser.add_argument("--gpg-binary", default="gpg")
    parser.add_argument("--gpg-key", help="GPG key ID/email used to detach-sign manifest.json.")
    parser.add_argument("--evidence-dir", type=Path, default=Path("artifacts/evidence_bundle"))
    parser.add_argument("--release-gate", type=Path, default=Path("release_gate.yaml"))
    parser.add_argument("--python", default=_default_python())
    parser.add_argument("--clean-python", default="python3.12")
    parser.add_argument("--timeout-sec", type=int, default=180)
    parser.add_argument("--max-log-bytes", type=int, default=1_000_000)
    parser.add_argument(
        "--fixed-timestamp-utc",
        help="Use one UTC timestamp for generated metadata and gate log timestamps.",
    )
    parser.add_argument("--skip-clean-install", action="store_true")
    parser.add_argument(
        "--allow-tainted-env",
        action="store_true",
        help="Development-only opt-out required with --skip-clean-install outside CI.",
    )
    parser.add_argument("--allow-failures", action="store_true")
    parser.add_argument(
        "--ci", action="store_true", help="Emit CI status JSON and keep stdout machine-readable."
    )
    parser.add_argument(
        "--environment-baseline",
        type=Path,
        help="JSON baseline of expected gate environment fingerprints.",
    )
    parser.add_argument(
        "--write-environment-baseline",
        type=Path,
        help="Write observed gate environment fingerprints for future drift checks.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.verify_manifest is not None:
        errors = verify_evidence_manifest(
            args.verify_manifest,
            require_gpg_signature=args.require_gpg_signature,
            gpg_binary=args.gpg_binary,
        )
        if errors:
            for error in errors:
                print(f"release-evidence: {error}", file=sys.stderr)
            return 1
        print(
            json.dumps(
                {"manifest": args.verify_manifest.as_posix(), "verified": True}, sort_keys=True
            )
        )
        return 0
    try:
        clock = _fixed_clock(args.fixed_timestamp_utc) if args.fixed_timestamp_utc else _utc_now
    except ValueError as exc:
        print(f"release-evidence: {exc}", file=sys.stderr)
        return 2
    ci_mode = bool(args.ci or os.environ.get("CI"))
    if args.skip_clean_install and ci_mode:
        print(
            "release-evidence: --skip-clean-install is forbidden in CI/production mode",
            file=sys.stderr,
        )
        return 2
    if args.skip_clean_install and not args.allow_tainted_env:
        print(
            "release-evidence: --skip-clean-install requires --allow-tainted-env for development runs",
            file=sys.stderr,
        )
        return 2

    evidence_dir: Path = args.evidence_dir
    logs_dir = evidence_dir / "raw_logs"
    try:
        _prepare_logs_dir(logs_dir)
    except ValueError as exc:
        print(f"release-evidence: {exc}", file=sys.stderr)
        return 2

    try:
        environment_baseline = _load_environment_baseline(args.environment_baseline)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"release-evidence: invalid environment baseline: {exc}", file=sys.stderr)
        return 2

    gates = _default_gates(args.python, args.clean_python, args.skip_clean_install)
    results = _run_gates(
        gates,
        logs_dir,
        args.timeout_sec,
        clock,
        args.max_log_bytes,
        environment_baseline,
    )
    if args.write_environment_baseline is not None:
        _write_environment_baseline(args.write_environment_baseline, results)

    sbom_path = evidence_dir / "sbom.cdx.json"
    sbom_sha, sbom_bytes = _write_sbom(sbom_path, clock=clock)
    telemetry = _write_telemetry(evidence_dir, results, clock=clock)
    manifest = {
        "schema_version": 1,
        "generated_utc": clock(),
        "python": args.python,
        "clean_python": args.clean_python,
        "release_gate": args.release_gate.as_posix(),
        "deterministic_timestamp_utc": args.fixed_timestamp_utc,
        "max_log_bytes": args.max_log_bytes,
        "execution_mode": "asyncio",
        "ci": ci_mode,
        "sbom": {
            "format": CYCLONEDX_BOM_FORMAT,
            "spec_version": CYCLONEDX_SPEC_VERSION,
            "path": sbom_path.as_posix(),
            "sha256": sbom_sha,
            "bytes": sbom_bytes,
        },
        "telemetry": telemetry,
        "gpg_signature": (
            {"path": (evidence_dir / "manifest.json.asc").as_posix(), "status": "PENDING"}
            if args.gpg_key
            else None
        ),
        "results": [
            {
                "name": result.name,
                "status": result.status,
                "required": result.required,
                "exit_code": result.exit_code,
                "command": result.command,
                "evidence": result.evidence.as_posix(),
                "started_utc": result.started_utc,
                "finished_utc": result.finished_utc,
                "semantic_failure": result.semantic_failure,
                "evidence_sha256": result.evidence_sha256,
                "evidence_bytes": result.evidence_bytes,
                "output_truncated": result.output_truncated,
                "environment_sha256": result.environment_sha256,
                "environment_status": result.environment_status,
                "environment_failure": result.environment_failure,
            }
            for result in results
        ],
    }
    failed_required = [result for result in results if result.required and result.exit_code != 0]
    manifest["valid_gates"] = [result.name for result in results if result.exit_code == 0]
    manifest["failed_required"] = [result.name for result in failed_required]
    ci_status_path = evidence_dir / "ci_status.json"
    ci_sha, ci_bytes = _write_ci_status(ci_status_path, manifest)
    manifest["ci_status"] = {"path": ci_status_path.as_posix(), "sha256": ci_sha, "bytes": ci_bytes}
    audit_pdf_path = evidence_dir / "audit_report.pdf"
    audit_sha, audit_bytes = _write_audit_pdf(audit_pdf_path, manifest, results)
    manifest["audit_report"] = {
        "format": "PDF-1.4",
        "path": audit_pdf_path.as_posix(),
        "sha256": audit_sha,
        "bytes": audit_bytes,
    }
    manifest_path = evidence_dir / "manifest.json"
    if args.gpg_key:
        signature_path = evidence_dir / "manifest.json.asc"
        manifest["gpg_signature"] = {"path": signature_path.as_posix(), "status": "SIGNED"}
        _write_json(manifest_path, manifest)
        signed, _signature_sha, signature_error = _sign_manifest(
            manifest_path, signature_path, gpg_binary=args.gpg_binary, gpg_key=args.gpg_key
        )
        if not signed:
            manifest["gpg_signature"] = {
                "path": signature_path.as_posix(),
                "status": "RED",
                "error": signature_error,
            }
            failed_required.append(
                GateResult(
                    "gpg_signature",
                    "RED",
                    [args.gpg_binary],
                    1,
                    signature_path,
                    True,
                    clock(),
                    clock(),
                    signature_error,
                )
            )
            manifest["failed_required"] = [result.name for result in failed_required]
            _write_json(manifest_path, manifest)
    else:
        _write_json(manifest_path, manifest)
    _write_release_gate_yaml(args.release_gate, results, clock=clock)

    print(
        json.dumps(
            {
                "failed_required": [item.name for item in failed_required],
                "manifest": manifest_path.as_posix(),
                "sbom": sbom_path.as_posix(),
                "audit_report": audit_pdf_path.as_posix(),
                "telemetry": telemetry,
            },
            sort_keys=True,
        )
    )
    if failed_required and not args.allow_failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
