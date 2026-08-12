#!/usr/bin/env python3
"""Fail-closed PromptOps artifact validator.

This module validates prompt-as-code artifacts as deterministic CI contracts.
It intentionally avoids live LLM calls; provider-backed evaluation belongs behind
an explicit shadow runner with cost, secret, and regression controls.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

yaml: Any = None
try:  # YAML support is optional locally, installed in CI.
    yaml = importlib.import_module("yaml")
except Exception:  # pragma: no cover - exercised when PyYAML is absent.
    yaml = None

CONTRACT_SCHEMA_ID = (
    "https://neuron7xlab.local/schemas/promptops/system_prompt_contract.schema.json"
)
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{2,127}$")
TEST_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
REF_RE = re.compile(r"<ref:([A-Za-z0-9_.-]+)>")
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
URL_RE = re.compile(r"https?://[^\s)\]>'\"]+")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
SECRET_PATTERNS = {
    "openai_key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "generic_token": re.compile(
        r"(api[_-]?key|token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{16,}", re.IGNORECASE
    ),
}
INJECTION_PATTERNS = {
    "ignore_previous": re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    "reveal_prompt": re.compile(r"reveal\s+(the\s+)?(system\s+)?prompt", re.IGNORECASE),
    "developer_mode": re.compile(r"you\s+are\s+now\s+(in\s+)?developer\s+mode", re.IGNORECASE),
}
ALLOWED_ROLES = {"system", "developer", "user", "assistant", "tool"}
REQUIRED_ROOT_KEYS = ("artifact_type", "id", "version", "messages", "unit_tests", "shadow_tests")


@dataclass
class ValidationIssue:
    path: str
    code: str
    message: str
    severity: str = "error"


@dataclass
class ValidationReport:
    artifact: str
    ok: bool = True
    issues: list[ValidationIssue] = field(default_factory=list)
    artifact_id: str | None = None
    version: str | None = None
    source_sha256: str | None = None

    def fail(self, code: str, message: str, path: str = "$.") -> None:
        self.ok = False
        self.issues.append(ValidationIssue(path=path, code=code, message=message))

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact,
            "artifact_id": self.artifact_id,
            "version": self.version,
            "source_sha256": self.source_sha256,
            "ok": self.ok,
            "issues": [
                issue.__dict__
                for issue in sorted(
                    self.issues, key=lambda item: (item.path, item.code, item.message)
                )
            ],
        }


def load_artifact(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    if path.suffix.lower() in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML is required to validate YAML artifacts")
        return yaml.safe_load(text)
    raise RuntimeError(f"Unsupported artifact extension: {path.suffix}")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def valid_url(raw: str) -> bool:
    parsed = urlparse(raw)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def all_text_nodes(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(all_text_nodes(item))
        return out
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(all_text_nodes(item))
        return out
    return []


def require_keys(report: ValidationReport, data: dict[str, Any], keys: tuple[str, ...]) -> None:
    for key in keys:
        if key not in data:
            report.fail("missing_required_key", f"Missing required key: {key}", f"$.{key}")


def validate_messages(report: ValidationReport, messages: Any) -> None:
    if not isinstance(messages, list) or not messages:
        report.fail("invalid_messages", "messages must be a non-empty array", "$.messages")
        return

    roles: list[str] = []
    for i, message in enumerate(messages):
        if not isinstance(message, dict):
            report.fail("invalid_message", "message must be an object", f"$.messages[{i}]")
            continue
        role = message.get("role")
        content = message.get("content")
        if role not in ALLOWED_ROLES:
            report.fail(
                "invalid_role",
                f"role must be one of {sorted(ALLOWED_ROLES)}",
                f"$.messages[{i}].role",
            )
        else:
            roles.append(role)
        if not isinstance(content, str) or not content.strip():
            report.fail(
                "empty_content",
                "message.content must be a non-empty string",
                f"$.messages[{i}].content",
            )

    if "system" not in roles and "developer" not in roles:
        report.fail(
            "missing_authoritative_instruction",
            "messages must include at least one system or developer instruction",
            "$.messages",
        )


def validate_references(report: ValidationReport, references: Any) -> set[str]:
    declared_refs: set[str] = set()
    if references is None:
        return declared_refs
    if not isinstance(references, list):
        report.fail("invalid_references", "references must be an array", "$.references")
        return declared_refs

    for i, ref in enumerate(references):
        if not isinstance(ref, dict):
            report.fail("invalid_reference", "reference must be an object", f"$.references[{i}]")
            continue
        ref_id, href = ref.get("id"), ref.get("href")
        if not isinstance(ref_id, str) or not TEST_ID_RE.fullmatch(ref_id):
            report.fail("invalid_reference_id", "reference id is invalid", f"$.references[{i}].id")
        elif ref_id in declared_refs:
            report.fail(
                "duplicate_reference_id",
                f"Duplicate reference id: {ref_id}",
                f"$.references[{i}].id",
            )
        else:
            declared_refs.add(ref_id)
        if not isinstance(href, str) or not valid_url(href):
            report.fail(
                "invalid_reference_href",
                "reference href must be http(s) URI",
                f"$.references[{i}].href",
            )
    return declared_refs


def validate_url_closure(report: ValidationReport, text_nodes: list[str]) -> None:
    urls: set[str] = set()
    for text in text_nodes:
        urls.update(URL_RE.findall(text))
        urls.update(match.group(1) for match in MARKDOWN_LINK_RE.finditer(text))
    for raw in sorted(urls):
        if raw.startswith("mailto:"):
            continue
        if not valid_url(raw):
            report.fail("invalid_url", f"Invalid URL: {raw}", "$.text")


def validate_security(report: ValidationReport, text_nodes: list[str]) -> None:
    for label, pattern in SECRET_PATTERNS.items():
        for text in text_nodes:
            if pattern.search(text):
                report.fail("secret_like_value", f"Potential secret detected: {label}", "$.text")
                break

    for label, pattern in INJECTION_PATTERNS.items():
        for text in text_nodes:
            if pattern.search(text):
                report.fail(
                    "prompt_injection_phrase",
                    f"Potential prompt-injection phrase detected: {label}",
                    "$.text",
                )
                break


def validate_test_collections(report: ValidationReport, data: dict[str, Any]) -> None:
    for collection_name in ("unit_tests", "shadow_tests"):
        collection = data.get(collection_name)
        if not isinstance(collection, list) or not collection:
            report.fail(
                "invalid_test_collection",
                f"{collection_name} must be a non-empty array",
                f"$.{collection_name}",
            )
            continue

        seen: set[str] = set()
        required = (
            ("input", "assertions")
            if collection_name == "unit_tests"
            else ("input", "baseline_expectations", "quality_gates")
        )
        for i, case in enumerate(collection):
            if not isinstance(case, dict):
                report.fail(
                    "invalid_test_case", "test case must be an object", f"$.{collection_name}[{i}]"
                )
                continue
            case_id = case.get("id")
            if not isinstance(case_id, str) or not TEST_ID_RE.fullmatch(case_id):
                report.fail("invalid_test_id", "test id is invalid", f"$.{collection_name}[{i}].id")
                continue
            if case_id in seen:
                report.fail(
                    "duplicate_test_id",
                    f"Duplicate test id: {case_id}",
                    f"$.{collection_name}[{i}].id",
                )
            seen.add(case_id)
            for key in required:
                if key not in case:
                    report.fail(
                        "missing_test_key",
                        f"Missing {key} in {collection_name} case",
                        f"$.{collection_name}[{i}].{key}",
                    )

            if collection_name == "shadow_tests":
                gates = case.get("quality_gates")
                if not isinstance(gates, list) or not gates:
                    report.fail(
                        "invalid_quality_gates",
                        "shadow_tests quality_gates must be a non-empty array",
                        f"$.{collection_name}[{i}].quality_gates",
                    )
                expectations = case.get("baseline_expectations")
                if not isinstance(expectations, (dict, list, str)):
                    report.fail(
                        "invalid_baseline_expectations",
                        "baseline_expectations must be object, array, or string",
                        f"$.{collection_name}[{i}].baseline_expectations",
                    )


def validate_artifact(path: Path) -> ValidationReport:
    report = ValidationReport(artifact=str(path))
    if path.exists():
        report.source_sha256 = sha256_file(path)

    try:
        data = load_artifact(path)
    except Exception as exc:
        report.fail("parse_error", str(exc))
        return report

    if not isinstance(data, dict):
        report.fail("invalid_root", "Artifact root must be an object")
        return report

    report.artifact_id = data.get("id") if isinstance(data.get("id"), str) else None
    report.version = data.get("version") if isinstance(data.get("version"), str) else None

    require_keys(report, data, REQUIRED_ROOT_KEYS)
    if any(issue.code == "missing_required_key" for issue in report.issues):
        return report

    if data.get("artifact_type") != "system_prompt_contract":
        report.fail(
            "invalid_artifact_type",
            "artifact_type must be system_prompt_contract",
            "$.artifact_type",
        )

    artifact_id = data.get("id")
    if not isinstance(artifact_id, str) or not ID_RE.fullmatch(artifact_id):
        report.fail("invalid_id", "id must match ^[A-Za-z][A-Za-z0-9_.-]{2,127}$", "$.id")

    version = data.get("version")
    if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
        report.fail(
            "invalid_version", "version must be strict semver: MAJOR.MINOR.PATCH", "$.version"
        )

    objective = data.get("objective")
    if objective is not None and (not isinstance(objective, str) or len(objective.strip()) < 16):
        report.fail(
            "invalid_objective",
            "objective must be at least 16 non-whitespace characters",
            "$.objective",
        )

    validate_messages(report, data.get("messages"))

    declared_refs = validate_references(report, data.get("references", []))
    text_nodes = all_text_nodes(data)

    mentioned_refs = {match.group(1) for text in text_nodes for match in REF_RE.finditer(text)}
    missing_refs = mentioned_refs - declared_refs
    if missing_refs:
        report.fail(
            "missing_reference_declaration",
            f"Referenced IDs are not declared: {sorted(missing_refs)}",
            "$.references",
        )

    validate_url_closure(report, text_nodes)
    validate_security(report, text_nodes)
    validate_test_collections(report, data)

    return report


def discover(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            out.extend(
                sorted(p for p in path.rglob("*") if p.suffix.lower() in {".json", ".yaml", ".yml"})
            )
        elif path.exists():
            out.append(path)
    return sorted(set(out), key=lambda item: item.as_posix())


def apply_global_gates(reports: list[ValidationReport]) -> None:
    ids: dict[str, list[ValidationReport]] = {}
    for report in reports:
        if report.artifact_id:
            ids.setdefault(report.artifact_id, []).append(report)

    for artifact_id, grouped in ids.items():
        if len(grouped) <= 1:
            continue
        locations = sorted(report.artifact for report in grouped)
        for report in grouped:
            report.fail(
                "duplicate_artifact_id",
                f"Artifact id {artifact_id!r} is duplicated across files: {locations}",
                "$.id",
            )


def build_payload(reports: list[ValidationReport]) -> dict[str, Any]:
    ok = all(report.ok for report in reports)
    issue_count = sum(len(report.issues) for report in reports)
    return {
        "contract_schema": CONTRACT_SCHEMA_ID,
        "ok": ok,
        "summary": {
            "artifact_count": len(reports),
            "issue_count": issue_count,
            "failed_artifacts": sum(1 for report in reports if not report.ok),
        },
        "reports": [report.as_dict() for report in reports],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate PromptOps system prompt contracts")
    parser.add_argument("paths", nargs="+", help="Artifact files or directories")
    parser.add_argument("--report", default="", help="Optional JSON report path")
    args = parser.parse_args(argv)

    artifacts = discover(args.paths)
    if not artifacts:
        print("PROMPTOPS_VALIDATION: FAIL no artifacts found", file=sys.stderr)
        return 2

    reports = [validate_artifact(path) for path in artifacts]
    apply_global_gates(reports)
    payload = build_payload(reports)

    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
