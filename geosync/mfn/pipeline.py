# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic MFN integration pipeline."""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .contract import MFNContract

STAGE_ORDER: tuple[str, ...] = (
    "simulate",
    "extract",
    "detect",
    "forecast",
    "compare",
    "report",
)

JSON_INDENT = 2
SHA256_HEX_LENGTH = 64
MANIFEST_SCHEMA_VERSION = "mfn.bundle.v1"


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp with a ``Z`` suffix."""

    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch is not None:
        moment = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    else:
        moment = datetime.now(timezone.utc)
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from ``path``."""

    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return loaded


def write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    """Write ``payload`` as canonical-ish pretty JSON and return ``path``."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=JSON_INDENT, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest for one file."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stage_payload(stage: str, contract: MFNContract, body: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": contract.schema_version,
        "stage": stage,
        "timestamp_utc": utc_now(),
        "contract": asdict(contract),
        **dict(body),
    }


def _is_sha256_hex(value: str) -> bool:
    return len(value) == SHA256_HEX_LENGTH and all(char in "0123456789abcdef" for char in value)


def _is_safe_relative_path(value: str) -> bool:
    return bool(value) and not value.startswith("/") and ".." not in Path(value).parts


def _finite_float(value: object, *, field: str, source: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{source} {field} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{source} {field} must be finite")
    return number


def _parse_sha256_manifest(path: Path) -> tuple[dict[str, str], list[str]]:
    """Parse a SHA-256 manifest into ``relative_path -> digest`` entries."""

    entries: dict[str, str] = {}
    errors: list[str] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if "  " not in line:
            errors.append(f"SHA256SUMS line {line_number} must use two-space separator")
            continue
        digest, rel = line.split("  ", 1)
        if not _is_sha256_hex(digest):
            errors.append(f"SHA256SUMS line {line_number} has invalid digest")
            continue
        if not _is_safe_relative_path(rel):
            errors.append(f"SHA256SUMS line {line_number} has invalid path")
            continue
        if rel in entries:
            errors.append(f"SHA256SUMS duplicate entry: {rel}")
            continue
        entries[rel] = digest
    return entries, errors


def simulate(output_dir: Path, *, seed: int, points: int, contract: MFNContract) -> Path:
    """Create a deterministic synthetic observation series."""

    if points < 4:
        raise ValueError("points must be >= 4")
    rng = random.Random(seed)
    price = 100.0
    observations: list[dict[str, float | int]] = []
    for index in range(points):
        drift = 0.03 * math.sin(index / 3.0)
        shock = rng.uniform(-0.15, 0.15)
        price = max(1.0, price + drift + shock)
        observations.append(
            {
                "t": index,
                "price": round(price, 6),
                "volume": round(10.0 + abs(shock) * 100.0 + index * 0.1, 6),
            }
        )
    payload = _stage_payload(
        "simulate",
        contract,
        {
            "seed": seed,
            "points": points,
            "observations": observations,
        },
    )
    return write_json(output_dir / "simulate.json", payload)


def extract(output_dir: Path, *, contract: MFNContract) -> Path:
    """Extract simple deterministic features from the simulated observations."""

    source = read_json(output_dir / "simulate.json")
    observations = source.get("observations")
    if not isinstance(observations, list):
        raise ValueError("simulate.json must contain observations")

    prices: list[float] = []
    for index, item in enumerate(observations):
        if not isinstance(item, dict):
            continue
        if "price" not in item:
            raise ValueError(f"simulate.json observations[{index}] price is required")
        prices.append(_finite_float(item["price"], field="price", source="simulate.json"))
    if len(prices) < 2:
        raise ValueError("simulate.json must contain at least two price observations")
    returns = [round(prices[i] - prices[i - 1], 8) for i in range(1, len(prices))]
    mean_return = sum(returns) / len(returns)
    variance = sum((item - mean_return) ** 2 for item in returns) / len(returns)
    features = {
        "count": len(prices),
        "last_price": round(prices[-1], 6),
        "mean_return": round(mean_return, 8),
        "volatility": round(math.sqrt(variance), 8),
        "positive_return_ratio": round(sum(1 for item in returns if item > 0) / len(returns), 8),
    }
    payload = _stage_payload("extract", contract, {"source": "simulate.json", "features": features})
    return write_json(output_dir / "extract.json", payload)


def detect(output_dir: Path, *, contract: MFNContract) -> Path:
    """Classify the feature snapshot into an observable regime."""

    source = read_json(output_dir / "extract.json")
    features = source.get("features")
    if not isinstance(features, dict):
        raise ValueError("extract.json must contain features")
    mean_return = _finite_float(
        features.get("mean_return"), field="mean_return", source="extract.json features"
    )
    volatility = _finite_float(
        features.get("volatility"), field="volatility", source="extract.json features"
    )
    if volatility > 0.12:
        regime = "volatile"
    elif mean_return > 0:
        regime = "upward_drift"
    elif mean_return < 0:
        regime = "downward_drift"
    else:
        regime = "flat"
    payload = _stage_payload(
        "detect",
        contract,
        {
            "source": "extract.json",
            "regime": regime,
            "risk_flag": volatility > 0.12,
            "confidence": round(min(1.0, abs(mean_return) / (volatility or 1.0) + 0.25), 8),
        },
    )
    return write_json(output_dir / "detect.json", payload)


def forecast(output_dir: Path, *, contract: MFNContract) -> Path:
    """Emit a conservative one-step forecast decision."""

    features_doc = read_json(output_dir / "extract.json")
    detect_doc = read_json(output_dir / "detect.json")
    features = features_doc.get("features")
    if not isinstance(features, dict):
        raise ValueError("extract.json must contain features")
    mean_return = _finite_float(
        features.get("mean_return"), field="mean_return", source="extract.json features"
    )
    last_price = _finite_float(
        features.get("last_price"), field="last_price", source="extract.json features"
    )
    risk_flag = bool(detect_doc.get("risk_flag"))
    predicted_price = round(last_price + mean_return, 6)
    decision = "OBSERVE" if not risk_flag else "NO_TRADE"
    payload = _stage_payload(
        "forecast",
        contract,
        {
            "sources": ["extract.json", "detect.json"],
            "predicted_next_price": predicted_price,
            "decision": decision,
            "claim_tier": contract.claim_tier,
        },
    )
    return write_json(output_dir / "forecast.json", payload)


def compare(output_dir: Path, *, contract: MFNContract) -> Path:
    """Compare the forecast against a null baseline without tier promotion."""

    features_doc = read_json(output_dir / "extract.json")
    forecast_doc = read_json(output_dir / "forecast.json")
    features = features_doc.get("features")
    if not isinstance(features, dict):
        raise ValueError("extract.json must contain features")
    last_price = _finite_float(
        features.get("last_price"), field="last_price", source="extract.json features"
    )
    predicted = _finite_float(
        forecast_doc.get("predicted_next_price"),
        field="predicted_next_price",
        source="forecast.json",
    )
    model_delta = abs(predicted - last_price)
    null_delta = 0.0
    null_superiority = null_delta <= model_delta
    payload = _stage_payload(
        "compare",
        contract,
        {
            "sources": ["extract.json", "forecast.json"],
            "null_baseline": "last_price_persistence",
            "model_absolute_delta": round(model_delta, 8),
            "null_absolute_delta": null_delta,
            "falsification_status": "BLOCKED" if null_superiority else "PASS",
            "claim_tier": "INSTRUMENTED",
        },
    )
    return write_json(output_dir / "compare.json", payload)


def report(output_dir: Path, *, contract: MFNContract) -> Path:
    """Create the machine report and human-readable runbook for the MFN bundle."""

    compare_doc = read_json(output_dir / "compare.json")
    forecast_doc = read_json(output_dir / "forecast.json")
    report_payload = _stage_payload(
        "report",
        contract,
        {
            "sources": ["forecast.json", "compare.json"],
            "status": "INSTRUMENTED",
            "decision": forecast_doc.get("decision"),
            "falsification_status": compare_doc.get("falsification_status"),
            "first_file_to_open": "manifest.json",
        },
    )
    report_path = write_json(output_dir / "report.json", report_payload)
    lines = [
        "# MFN Integration Runbook",
        "",
        "Status: INSTRUMENTED.",
        f"Decision: {forecast_doc.get('decision')}",
        f"Falsification status: {compare_doc.get('falsification_status')}",
        "",
        "First file to open: manifest.json",
        "",
        "Reproduce:",
        "",
        "```bash",
        "mfn --out <bundle-dir> run",
        "mfn validate --bundle <bundle-dir>",
        "```",
        "",
    ]
    (output_dir / "runbook.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def write_manifests(output_dir: Path, files: Iterable[Path]) -> tuple[Path, Path]:
    """Write JSON and sha256 manifests for ``files``."""

    entries = []
    sha_lines = []
    for path in sorted({item for item in files if item.is_file()}):
        rel = path.relative_to(output_dir).as_posix()
        digest = sha256_file(path)
        entries.append({"path": rel, "sha256": digest, "bytes": path.stat().st_size})
        sha_lines.append(f"{digest}  {rel}")
    manifest = write_json(
        output_dir / "manifest.json", {"schema_version": MANIFEST_SCHEMA_VERSION, "files": entries}
    )
    sha_manifest = output_dir / "SHA256SUMS"
    sha_manifest.write_text("\n".join(sha_lines) + "\n", encoding="utf-8")
    return manifest, sha_manifest


def run_all(output_dir: Path, *, seed: int, points: int) -> dict[str, Path]:
    """Run the full MFN integration chain and return named artifacts."""

    contract = MFNContract(seed=seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, Path] = {}
    artifacts["simulate"] = simulate(output_dir, seed=seed, points=points, contract=contract)
    artifacts["extract"] = extract(output_dir, contract=contract)
    artifacts["detect"] = detect(output_dir, contract=contract)
    artifacts["forecast"] = forecast(output_dir, contract=contract)
    artifacts["compare"] = compare(output_dir, contract=contract)
    artifacts["report"] = report(output_dir, contract=contract)
    artifacts["runbook"] = output_dir / "runbook.md"
    manifest, sha_manifest = write_manifests(output_dir, artifacts.values())
    artifacts["manifest"] = manifest
    artifacts["sha256_manifest"] = sha_manifest
    return artifacts


def _validate_runbook(runbook_text: str, errors: list[str]) -> None:
    """Validate stable human replay guidance in ``runbook.md``."""

    if "First file to open: manifest.json" not in runbook_text:
        errors.append("runbook.md missing first-file guidance")
    if "mfn validate --bundle <bundle-dir>" not in runbook_text:
        errors.append("runbook.md missing validation command")


def _validate_stage_document(
    document: Mapping[str, Any], *, stage: str, expected_schema: str, errors: list[str]
) -> None:
    """Validate one stage artifact document against the MFN stage contract."""

    if document.get("schema_version") != expected_schema:
        errors.append(f"{stage}.json has unsupported schema_version")
    if document.get("stage") != stage:
        errors.append(f"{stage}.json has wrong stage")


def _validate_manifest_entry(
    entry: object, *, output_dir: Path, manifest_hashes: dict[str, str], errors: list[str]
) -> None:
    """Validate one manifest entry and record its digest when admissible."""

    if not isinstance(entry, dict):
        errors.append("manifest entry must be an object")
        return
    rel = entry.get("path")
    digest = entry.get("sha256")
    size = entry.get("bytes")
    if not isinstance(rel, str) or not isinstance(digest, str):
        errors.append("manifest entry path and sha256 must be strings")
        return
    if not isinstance(size, int) or size < 0:
        errors.append(f"manifest entry has invalid bytes: {rel}")
        return
    if not _is_safe_relative_path(rel):
        errors.append(f"manifest entry has invalid path: {rel}")
        return
    if not _is_sha256_hex(digest):
        errors.append(f"manifest entry has invalid digest: {rel}")
        return
    if rel in manifest_hashes:
        errors.append(f"manifest duplicate entry: {rel}")
        return
    manifest_hashes[rel] = digest
    target = output_dir / rel
    if not target.exists():
        errors.append(f"manifest target missing: {rel}")
        return
    if target.stat().st_size != size:
        errors.append(f"manifest size mismatch: {rel}")
    actual = sha256_file(target)
    if actual != digest:
        errors.append(f"manifest hash mismatch: {rel}")


def validate_bundle(output_dir: Path) -> list[str]:
    """Return validation errors for an MFN output bundle."""

    errors: list[str] = []
    manifest = output_dir / "manifest.json"
    sha_manifest = output_dir / "SHA256SUMS"
    runbook = output_dir / "runbook.md"
    required_artifacts = [
        runbook,
        *(output_dir / f"{stage}.json" for stage in STAGE_ORDER),
    ]
    for required in [manifest, sha_manifest, *required_artifacts]:
        if not required.exists():
            errors.append(f"missing required artifact: {required.name}")
    if errors:
        return errors

    _validate_runbook(runbook.read_text(encoding="utf-8"), errors)

    expected_manifest_paths = {
        path.relative_to(output_dir).as_posix() for path in required_artifacts
    }
    expected_stage_schema = MFNContract().schema_version
    for stage in STAGE_ORDER:
        path = output_dir / f"{stage}.json"
        try:
            document = read_json(path)
        except ValueError as exc:
            errors.append(f"{stage}.json is invalid: {exc}")
            continue
        _validate_stage_document(
            document, stage=stage, expected_schema=expected_stage_schema, errors=errors
        )

    try:
        manifest_doc = read_json(manifest)
    except ValueError as exc:
        errors.append(f"manifest.json is invalid: {exc}")
        return errors
    if manifest_doc.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append("manifest.json has unsupported schema_version")
    files = manifest_doc.get("files")
    if not isinstance(files, list):
        errors.append("manifest.json files must be a list")
        return errors

    manifest_hashes: dict[str, str] = {}
    for entry in files:
        _validate_manifest_entry(
            entry, output_dir=output_dir, manifest_hashes=manifest_hashes, errors=errors
        )

    for rel in sorted(expected_manifest_paths - set(manifest_hashes)):
        errors.append(f"manifest missing required entry: {rel}")
    for rel in sorted(set(manifest_hashes) - expected_manifest_paths):
        errors.append(f"manifest unexpected entry: {rel}")

    sha_hashes, sha_errors = _parse_sha256_manifest(sha_manifest)
    errors.extend(sha_errors)
    if sha_hashes != manifest_hashes:
        for rel in sorted(set(manifest_hashes) - set(sha_hashes)):
            errors.append(f"SHA256SUMS missing entry: {rel}")
        for rel in sorted(set(sha_hashes) - set(manifest_hashes)):
            errors.append(f"SHA256SUMS unexpected entry: {rel}")
        for rel in sorted(set(manifest_hashes) & set(sha_hashes)):
            if sha_hashes[rel] != manifest_hashes[rel]:
                errors.append(f"SHA256SUMS hash mismatch: {rel}")

    for rel, digest in sha_hashes.items():
        target = output_dir / rel
        if not target.exists():
            errors.append(f"SHA256SUMS target missing: {rel}")
            continue
        actual = sha256_file(target)
        if actual != digest:
            errors.append(f"SHA256SUMS target hash mismatch: {rel}")
    return errors
