"""Artifact schema validation and evidence bundle writing."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .determinism import canonical_json_bytes, sha256_bytes

SCHEMA_PATH = Path("schemas/research/ricci_microstructure_artifact.schema.json")
FORBIDDEN_STATUSES = {
    "ALPHA_FOUND",
    "MARKET_SIGNAL_PROVEN",
    "PRODUCTION_READY",
    "PHYSICS_CONFIRMED",
}
ALLOWED_STATUSES = {"SUPPORTED", "HYPOTHESIS_NOT_SUPPORTED", "INVALID"}


def load_schema(path: Path = SCHEMA_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_artifact_payload(
    payload: dict[str, Any], *, schema_path: Path = SCHEMA_PATH
) -> list[str]:
    if payload.get("falsification_status") in FORBIDDEN_STATUSES:
        return [f"forbidden falsification_status: {payload['falsification_status']}"]
    schema = load_schema(schema_path)
    validator = Draft202012Validator(schema)
    return [
        error.message
        for error in sorted(validator.iter_errors(payload), key=lambda item: item.path)
    ]


def write_artifact(path: Path, payload: dict[str, Any], *, schema_path: Path = SCHEMA_PATH) -> str:
    errors = validate_artifact_payload(payload, schema_path=schema_path)
    if errors:
        raise RuntimeError("artifact schema validation failed: " + "; ".join(errors))
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = canonical_json_bytes(payload)
    path.write_bytes(encoded + b"\n")
    return sha256_bytes(encoded)


def verify_artifact(path: Path, *, schema_path: Path = SCHEMA_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("artifact root must be an object")
    errors = validate_artifact_payload(payload, schema_path=schema_path)
    if errors:
        raise RuntimeError("artifact schema validation failed: " + "; ".join(errors))
    if payload["falsification_status"] not in ALLOWED_STATUSES:
        raise RuntimeError("invalid final status")
    return payload


def write_minimal_pdf(path: Path, title: str, lines: list[str]) -> None:
    text = "\\n".join([title, *lines]).replace("(", "[").replace(")", "]")
    stream = f"BT /F1 12 Tf 72 740 Td ({text[:1600]}) Tj ET".encode("latin-1", "replace")
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        b"5 0 obj << /Length "
        + str(len(stream)).encode()
        + b" >> stream\n"
        + stream
        + b"\nendstream endobj\n",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(output))
        output.extend(obj)
    xref = len(output)
    output.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(output))


def write_evidence_bundle(
    *,
    run_id: str,
    artifact_path: Path,
    data_manifest_path: Path,
    replay_command: str,
    out_dir: Path,
) -> Path:
    evidence_dir = Path("artifacts/evidence")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    summary_pdf = out_dir / "summary.pdf"
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    write_minimal_pdf(
        summary_pdf,
        "GeoSync Ricci Microstructure v1",
        [
            f"run_id={run_id}",
            f"status={payload.get('falsification_status')}",
            f"p_value={payload.get('p_value')}",
            f"cliffs_delta={payload.get('cliffs_delta')}",
        ],
    )
    replay_path = out_dir / "replay_command.txt"
    replay_path.write_text(replay_command + "\n", encoding="utf-8")
    bundle_path = evidence_dir / f"{run_id}.zip"
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(artifact_path, "artifact.json")
        bundle.write(data_manifest_path, "data_manifest.json")
        bundle.write(replay_path, "replay_command.txt")
        bundle.write(summary_pdf, "PDF summary")
        for candidate, arcname in (
            (Path("sbom/cdx.json"), "cdx.json"),
            (Path("sbom/spdx.json"), "spdx.json"),
            (Path("provenance/provenance.json"), "provenance.json"),
        ):
            if candidate.exists():
                bundle.write(candidate, arcname)
        log_dir = out_dir / "logs"
        if log_dir.exists():
            for log in sorted(log_dir.rglob("*")):
                if log.is_file():
                    bundle.write(log, f"logs/{log.relative_to(log_dir).as_posix()}")
    return bundle_path
