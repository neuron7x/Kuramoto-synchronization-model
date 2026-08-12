#!/usr/bin/env python3
"""BBB-NVU Cognitive Noise Gate deterministic demo engine.

Research-use repo seed. Not a medical device.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Annotated, Any, Literal, cast

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    ValidationError,
    field_validator,
)

ENGINE_VERSION = "demo-0.5.0"
DOMAIN_MIN = 0.0
DOMAIN_MAX = 100.0
CONFIDENCE_MIN = 0.0
CONFIDENCE_MAX = 1.0
HIGH_REVIEW_STATES = {"ORANGE_RISK", "RED_CRITICAL", "BLACK_INVALID"}
AUTONOMOUS_PROHIBITED_STATES = {"RED_CRITICAL", "BLACK_INVALID"}
VALID_STATES = {
    "GREEN_STABLE",
    "YELLOW_WATCH",
    "ORANGE_RISK",
    "RED_CRITICAL",
    "BLACK_INVALID",
}
CRITICAL_DEGRADATIONS = {
    "SOURCE_CONFLICT",
    "RULE_VERSION_MISMATCH",
    "OUT_OF_DISTRIBUTION",
    "UNKNOWN_PROVENANCE",
    "CLOCK_SKEW_DETECTED",
    "MATH_CORRUPTION",
    "SCHEMA_INVALID",
}

DomainCode = Literal["BSI", "NRI", "VML", "GRS", "CNI"]
SourceType = Literal[
    "lab",
    "wearable",
    "cognitive_test",
    "imaging",
    "bbb_on_chip",
    "clinical_note",
    "manual_entry",
]
ObservationDomain = Literal[
    "barrier",
    "inflammation",
    "vascular_metabolic",
    "glymphatic_sleep",
    "cognitive",
    "environment",
    "qc",
]
ProvenanceActivity = Literal[
    "created",
    "measured",
    "imported",
    "normalized",
    "inferred",
    "reviewed",
    "updated",
    "deleted",
]
EvidenceGrade = Literal["A", "B", "C", "D"]
StrictDomainIndex = Annotated[
    float,
    Field(strict=True, ge=DOMAIN_MIN, le=DOMAIN_MAX, allow_inf_nan=False),
]
StrictConfidence = Annotated[
    float,
    Field(strict=True, ge=CONFIDENCE_MIN, le=CONFIDENCE_MAX, allow_inf_nan=False),
]


class StrictProvenance(BaseModel):
    """L1 provenance contract for data entering the artifact."""

    model_config = ConfigDict(extra="forbid")

    record_id: StrictStr
    created_at: datetime.datetime
    agent: StrictStr
    source_id: StrictStr
    activity: ProvenanceActivity
    version: StrictStr
    input_hash: StrictStr = ""
    output_hash: StrictStr = ""
    signature: StrictStr = ""
    license: StrictStr = ""


class StrictObservation(BaseModel):
    """L1 numeric observation contract: no polymorphic metric payloads."""

    model_config = ConfigDict(extra="forbid")

    observation_id: StrictStr
    subject_id: StrictStr
    timestamp: datetime.datetime
    source_type: SourceType
    domain: ObservationDomain
    measure_code: StrictStr
    value: Annotated[float, Field(strict=True, allow_inf_nan=False)]
    unit: StrictStr
    method: StrictStr
    provenance: StrictProvenance
    evidence_grade: EvidenceGrade | None = None
    quality_score: (
        Annotated[
            float,
            Field(strict=True, ge=0.0, le=1.0, allow_inf_nan=False),
        ]
        | None
    ) = None
    notes: StrictStr | None = None

    @field_validator("value")
    @classmethod
    def check_numeric_sanity(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Inference path block: NaN or Inf detected.")
        return value


class StrictInferenceInput(BaseModel):
    """L1 normalized inference contract used by the deterministic engine."""

    model_config = ConfigDict(extra="forbid")

    subject_id: StrictStr
    critical_data_invalid: StrictBool
    confidence: StrictConfidence
    domain_indices: dict[DomainCode, StrictDomainIndex]
    degradations: list[StrictStr]

    @field_validator("domain_indices")
    @classmethod
    def check_domain_indices(cls, values: dict[DomainCode, float]) -> dict[DomainCode, float]:
        for domain, value in values.items():
            if not math.isfinite(value):
                raise ValueError(f"Inference path block: NaN or Inf detected in {domain}.")
        return values

    def normalized_doc(self) -> dict[str, Any]:
        """Return a plain deterministic input document after L1 validation."""
        return {
            "subject_id": self.subject_id,
            "critical_data_invalid": self.critical_data_invalid,
            "confidence": float(self.confidence),
            "domain_indices": {
                str(key): float(value) for key, value in sorted(self.domain_indices.items())
            },
            "degradations": list(self.degradations),
        }


def canonical(obj: Any) -> str:
    """Return deterministic JSON text for hashing with strict JSON constants."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonicalize_jcs(obj: Any) -> str:
    """Alias for RFC-8785-style deterministic JSON subset used by this artifact."""
    return canonical(obj)


def sha256_text(text: str) -> str:
    """Return a SHA-256 hex digest for UTF-8 text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_code_hash(path: str | Path = __file__) -> str:
    """Return the deterministic source hash used in run_hash construction."""
    return sha256_text(Path(path).read_text(encoding="utf-8"))


def hashable_json_value(value: Any) -> Any:
    """Convert non-JSON numeric sentinels into deterministic strings for audit hashing."""
    if isinstance(value, dict):
        return {str(key): hashable_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [hashable_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [hashable_json_value(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return f"__NON_FINITE_FLOAT__:{value!r}"
    return value


def audit_hash(obj: Any) -> str:
    """Return a deterministic hash even for direct Python fuzz inputs containing NaN/Inf."""
    return sha256_text(canonical(hashable_json_value(obj)))


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load pinned YAML rules from disk."""
    text = Path(path).read_text(encoding="utf-8")
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ValueError("risk rules must load as a mapping")
    return cast(dict[str, Any], loaded)


def utc_now_iso() -> str:
    """Return a UTC timestamp with second precision."""
    return (
        datetime.datetime.now(datetime.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def clamp_confidence(value: float) -> float:
    """Clamp confidence into the schema range after penalties."""
    return min(CONFIDENCE_MAX, max(CONFIDENCE_MIN, value))


def classify_domain(domain: str, value: float, cfg: dict[str, Any]) -> str | None:
    """Classify one domain as critical, risk, warning, or None."""
    if cfg.get("direction") == "lower_is_worse":
        if value <= float(cfg["critical_low"]):
            return "critical"
        if value <= float(cfg["risk_low"]):
            return "risk"
        if value <= float(cfg["warning_low"]):
            return "warning"
        return None

    if value >= float(cfg["critical"]):
        return "critical"
    if value >= float(cfg["risk"]):
        return "risk"
    if value >= float(cfg["warning"]):
        return "warning"
    return None


def validation_error_reasons(error: ValidationError) -> list[str]:
    """Convert Pydantic L1 failures into deterministic fail-closed reason strings."""
    reasons: list[str] = []
    for item in error.errors():
        location = ".".join(str(part) for part in item.get("loc", ())) or "root"
        error_type = str(item.get("type", "validation_error"))
        reasons.append(f"l1_schema_invalid:{location}:{error_type}")
    return sorted(reasons)


def validate_observation(input_doc: dict[str, Any]) -> StrictObservation:
    """Validate an atomic numeric Observation at L1 before feature construction."""
    return StrictObservation.model_validate(input_doc)


def validate_inference_input(input_doc: dict[str, Any]) -> StrictInferenceInput:
    """Validate normalized inference input at L1 before deterministic risk inference."""
    return StrictInferenceInput.model_validate(input_doc)


class DeterministicInferenceEngine:
    """Deterministic, fail-closed evaluator for normalized CNS risk vectors."""

    def __init__(
        self,
        rules_path: str | Path | None = None,
        *,
        rules: dict[str, Any] | None = None,
        engine_hash: str | None = None,
    ):
        if rules is None:
            if rules_path is None:
                raise ValueError("rules_path or rules must be supplied")
            self.rules_path = str(rules_path)
            self.rules = load_yaml(rules_path)
        else:
            self.rules_path = str(rules_path or "<in-memory>")
            self.rules = rules
        self.engine_hash = engine_hash or source_code_hash()

    @classmethod
    def from_rules(
        cls,
        rules: dict[str, Any],
        engine_hash: str | None = None,
    ) -> "DeterministicInferenceEngine":
        """Build an engine from already-loaded rules; no file-system rule loading."""
        return cls(rules=rules, engine_hash=engine_hash)

    def evaluate_run(
        self,
        input_doc: dict[str, Any],
        created_at: str | None = None,
        source_id: str = "memory.json",
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Return risk and actions without raising on malformed inference payloads."""
        output = self.build_output(input_doc, source_id=source_id, created_at=created_at)
        return output["risk"], output["actions"]

    def build_output(
        self,
        input_doc: dict[str, Any],
        source_id: str,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        """Build a complete inference transaction with provenance and stable run hash."""
        risk, actions = self.evaluate(input_doc)
        input_hash = audit_hash(input_doc)
        rules_hash = sha256_text(canonical(self.rules))
        run_hash = sha256_text(input_hash + rules_hash + self.engine_hash)
        now = created_at or utc_now_iso()

        return {
            "run_id": "run-" + run_hash[:12],
            "created_at": now,
            "engine_version": ENGINE_VERSION,
            "rules_version": self.rules.get("rules_version", "unknown"),
            "input_hash": input_hash,
            "rules_hash": rules_hash,
            "engine_hash": self.engine_hash,
            "run_hash": run_hash,
            "risk": risk,
            "actions": actions,
            "provenance": {
                "record_id": "prov-" + run_hash[:12],
                "created_at": now,
                "agent": "deterministic_engine.py",
                "source_id": source_id,
                "activity": "inferred",
                "version": ENGINE_VERSION,
                "input_hash": input_hash,
                "output_hash": sha256_text(canonical({"risk": risk, "actions": actions})),
                "signature": "",
                "license": "research-use-only",
            },
        }

    def evaluate(self, input_doc: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Evaluate a normalized inference input after strict L1 contract validation."""
        invalid_reasons: list[str] = []

        try:
            strict_input = validate_inference_input(input_doc)
            normalized_doc = strict_input.normalized_doc()
        except ValidationError as error:
            invalid_reasons.extend(validation_error_reasons(error))
            normalized_doc = {
                "subject_id": (
                    str(input_doc.get("subject_id", "INVALID_SUBJECT"))
                    if isinstance(input_doc, dict)
                    else "INVALID_SUBJECT"
                ),
                "critical_data_invalid": True,
                "confidence": 0.0,
                "domain_indices": {},
                "degradations": ["SCHEMA_INVALID"],
            }

        indices = normalized_doc["domain_indices"]
        degradations = list(normalized_doc["degradations"])
        confidence = float(normalized_doc["confidence"])

        if normalized_doc["critical_data_invalid"]:
            invalid_reasons.append("critical_data_invalid")

        sanitized_indices: dict[str, float] = dict(indices)

        if not invalid_reasons:
            for domain in self.rules["domains"]:
                if domain not in sanitized_indices:
                    degradations.append(f"missing_domain:{domain}")

        confidence = apply_degradation_penalties(confidence, degradations, self.rules)

        if invalid_reasons:
            state = "BLACK_INVALID"
            confidence = 0.0
            math_error = any(
                "finite" in reason
                or "float" in reason
                or "less_than" in reason
                or "greater_than" in reason
                for reason in invalid_reasons
            )
            if math_error:
                degradations.append("MATH_CORRUPTION")
            explanations = [
                "l1_data_quality_gate=blocked",
                "fail_closed=true",
                f"invalid_reasons={sorted(set(invalid_reasons))}",
                "confidence=0.00",
            ]
        else:
            state, explanations, degradations = infer_state(
                sanitized_indices,
                confidence,
                degradations,
                self.rules,
            )
            explanations.insert(0, "l1_data_quality_gate=passed")

        risk_out = {
            "risk_state": state,
            "confidence": confidence,
            "domain_indices": {key: sanitized_indices[key] for key in sorted(sanitized_indices)},
            "explanations": explanations,
            "degradations": sorted(set(degradations)),
        }
        return risk_out, build_actions(state, self.rules)


def apply_degradation_penalties(
    confidence: float,
    degradations: list[Any],
    rules: dict[str, Any],
) -> float:
    """Apply explicit confidence penalties for degradation control signals."""
    penalties = rules.get("confidence", {})
    adjusted = confidence
    normalized = {str(degradation) for degradation in degradations}

    if any("missing_domain:" in item or item == "DATA_MISSING" for item in normalized):
        adjusted -= float(penalties.get("missing_noncritical_penalty", 0.0))
    if any(item in {"UNKNOWN_PROVENANCE", "unknown_provenance"} for item in normalized):
        adjusted -= float(penalties.get("unknown_provenance_penalty", 0.0))
    if any(item in {"DATA_NOISY", "LOW_QUALITY", "low_quality"} for item in normalized):
        adjusted -= float(penalties.get("low_quality_penalty", 0.0))
    if any(item in {"SOURCE_CONFLICT", "source_conflict"} for item in normalized):
        adjusted -= float(penalties.get("conflict_penalty", 0.0))

    return clamp_confidence(adjusted)


def infer_state(
    indices: dict[str, float],
    confidence: float,
    degradations: list[Any],
    rules: dict[str, Any],
) -> tuple[str, list[str], list[Any]]:
    """Infer non-invalid composite state from sanitized domain indices."""
    critical: list[str] = []
    risk: list[str] = []
    warning: list[str] = []

    for domain, cfg in rules["domains"].items():
        if domain not in indices:
            continue

        classification = classify_domain(domain, indices[domain], cfg)
        if classification == "critical":
            critical.append(domain)
        elif classification == "risk":
            risk.append(domain)
        elif classification == "warning":
            warning.append(domain)

    visible_degradations = bool(degradations)
    critical_degradation = any(str(item) in CRITICAL_DEGRADATIONS for item in degradations)

    if critical or len(risk) >= 3 or critical_degradation:
        state = "RED_CRITICAL"
    elif len(risk) >= 2:
        state = "ORANGE_RISK"
    elif warning or confidence < 0.70 or visible_degradations:
        state = "YELLOW_WATCH"
    else:
        state = "GREEN_STABLE"

    explanations = [
        f"critical_domains={critical}",
        f"risk_domains={risk}",
        f"warning_domains={warning}",
        f"confidence={confidence:.2f}",
        f"visible_degradations={visible_degradations}",
    ]
    return state, explanations, degradations


def evaluate(
    input_doc: dict[str, Any],
    rules: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Compatibility wrapper around the deterministic engine."""
    engine = DeterministicInferenceEngine.from_rules(rules)
    return engine.evaluate(input_doc)


def build_actions(state: str, rules: dict[str, Any]) -> list[dict[str, Any]]:
    """Build state-triggered control actions."""
    actions: list[dict[str, Any]] = []
    for idx, action in enumerate(rules["actions"].get(state, []), start=1):
        action_class = "DATA_CONTROL" if state == "BLACK_INVALID" else "OPERATIONAL_CONTROL"
        if "clinical" in action:
            action_class = "CLINICAL_ESCALATION"

        actions.append(
            {
                "action_id": f"{state}-{idx}",
                "action_class": action_class,
                "description": action,
                "trigger_rule": f"state:{state}",
                "risk_state": state,
                "requires_human_review": state in HIGH_REVIEW_STATES,
                "prohibited_autonomous_execution": state in AUTONOMOUS_PROHIBITED_STATES,
            }
        )
    return actions


def build_output(
    input_doc: dict[str, Any],
    input_path: str,
    rules: dict[str, Any],
) -> dict[str, Any]:
    """Compatibility wrapper for building an inference transaction."""
    engine = DeterministicInferenceEngine.from_rules(rules)
    return engine.build_output(input_doc, source_id=input_path)


def main() -> int:
    """CLI entrypoint."""
    if len(sys.argv) != 3:
        print("Usage: deterministic_engine.py <input.json> <risk_rules.yaml>", file=sys.stderr)
        return 2

    input_path = sys.argv[1]
    input_doc = json.loads(Path(input_path).read_text(encoding="utf-8"))
    engine = DeterministicInferenceEngine(sys.argv[2])
    print(
        json.dumps(
            engine.build_output(input_doc, source_id=input_path),
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
