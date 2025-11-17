"""Comprehensive data annotation workflow utilities.

This module provides the building blocks necessary to run high quality
annotation programs in a single place.  The design favours composable classes
that can be reused inside notebooks, pipelines, or thin orchestration layers.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
import uuid
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import StatisticsError
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    MutableMapping,
    Optional,
    Sequence,
    Tuple,
)


@dataclass(slots=True)
class AnnotationRecord:
    """A single annotation entry produced by an annotator."""

    item_id: str
    annotator_id: str
    label: str
    score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class InstructionTemplate:
    """Reusable instructions for annotators."""

    template_id: str
    name: str
    body: str
    version: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DatasetVersion:
    """Represents a dataset snapshot."""

    version_id: str
    created_at: datetime
    data_path: Path
    description: str
    checksum: str


class AnnotationProject:
    """Manages annotation records, instructions, and metadata."""

    def __init__(
        self, project_id: str, name: str, instruction: InstructionTemplate
    ) -> None:
        self.project_id = project_id
        self.name = name
        self.instruction = instruction
        self.records: List[AnnotationRecord] = []
        self.item_assignments: Dict[str, List[str]] = defaultdict(list)
        self.audit_log = AuditLog(project_id=project_id)

    def assign_item(self, item_id: str, annotator_id: str) -> None:
        self.item_assignments[item_id].append(annotator_id)
        self.audit_log.log(
            "assignment", {"item_id": item_id, "annotator_id": annotator_id}
        )

    def add_record(self, record: AnnotationRecord) -> None:
        self.records.append(record)
        self.audit_log.log(
            "annotation",
            {
                "item_id": record.item_id,
                "annotator_id": record.annotator_id,
                "label": record.label,
            },
        )

    def get_records_for_item(self, item_id: str) -> List[AnnotationRecord]:
        return [record for record in self.records if record.item_id == item_id]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "instruction_id": self.instruction.template_id,
            "records": [asdict(record) for record in self.records],
        }


class AnnotationInterface:
    """Minimal interface that can serve annotation tasks to annotators."""

    def __init__(self, project: AnnotationProject) -> None:
        self.project = project

    def next_assignment(
        self, annotator_id: str, backlog: Iterable[str]
    ) -> Optional[str]:
        assigned = self.project.item_assignments
        for item_id in backlog:
            if annotator_id not in assigned[item_id]:
                self.project.assign_item(item_id, annotator_id)
                return item_id
        return None

    def submit(
        self,
        item_id: str,
        annotator_id: str,
        label: str,
        score: Optional[float] = None,
        **metadata: Any,
    ) -> None:
        record = AnnotationRecord(
            item_id=item_id,
            annotator_id=annotator_id,
            label=label,
            score=score,
            metadata=metadata,
        )
        self.project.add_record(record)


class QualityChecker:
    """Evaluates annotation quality metrics."""

    def __init__(
        self,
        reference_labels: MutableMapping[str, str],
        *,
        positive_label: str = "positive",
    ) -> None:
        self.reference_labels = reference_labels
        self.positive_label = positive_label

    def evaluate(self, records: Sequence[AnnotationRecord]) -> Dict[str, float]:
        tp = fp = fn = tn = 0
        for record in records:
            reference = self.reference_labels.get(record.item_id)
            if reference is None:
                continue
            if record.label == reference:
                if reference == self.positive_label:
                    tp += 1
                else:
                    tn += 1
            else:
                if record.label == self.positive_label:
                    fp += 1
                else:
                    fn += 1
        total = tp + tn + fp + fn
        accuracy = (tp + tn) / total if total else 0.0
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (
            (2 * precision * recall) / (precision + recall)
            if (precision + recall)
            else 0.0
        )
        return {
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }


class InterraterAgreementCalculator:
    """Computes agreement metrics between annotators."""

    def __init__(self, records: Sequence[AnnotationRecord]) -> None:
        self.records = records

    def cohen_kappa(self) -> Dict[Tuple[str, str], float]:
        items_by_annotator: Dict[str, Dict[str, str]] = defaultdict(dict)
        for record in self.records:
            items_by_annotator[record.annotator_id][record.item_id] = record.label
        annotators = list(items_by_annotator)
        kappas: Dict[Tuple[str, str], float] = {}
        for i, left in enumerate(annotators):
            for right in annotators[i + 1 :]:
                kappas[(left, right)] = self._pairwise_kappa(
                    items_by_annotator[left], items_by_annotator[right]
                )
        return kappas

    @staticmethod
    def _pairwise_kappa(left: Dict[str, str], right: Dict[str, str]) -> float:
        items = set(left) & set(right)
        if not items:
            return float("nan")
        observed = sum(1 for item in items if left[item] == right[item]) / len(items)
        label_counts_left = Counter(left[item] for item in items)
        label_counts_right = Counter(right[item] for item in items)
        labels = set(label_counts_left) | set(label_counts_right)
        pe = 0.0
        for label in labels:
            pe += (label_counts_left[label] / len(items)) * (
                label_counts_right[label] / len(items)
            )
        if math.isclose(1 - pe, 0.0):
            return float("nan")
        return (observed - pe) / (1 - pe)

    def fleiss_kappa(self) -> float:
        per_item: Dict[str, Counter[str]] = defaultdict(Counter)
        annotators_per_item: Dict[str, int] = defaultdict(int)
        for record in self.records:
            per_item[record.item_id][record.label] += 1
            annotators_per_item[record.item_id] += 1
        if not per_item:
            return float("nan")
        label_set = sorted({label for counts in per_item.values() for label in counts})
        n = len(per_item)
        annotator_counts = list(annotators_per_item.values())
        if not annotator_counts:
            return float("nan")
        try:
            m = statistics.mode(annotator_counts)
        except StatisticsError:
            m = int(statistics.mean(annotator_counts))
        if m == 0:
            return float("nan")
        p: Dict[str, float] = {label: 0.0 for label in label_set}
        for counts in per_item.values():
            for label in label_set:
                p[label] += counts[label]
        for label in p:
            p[label] /= n * m
        p_bar = 0.0
        for counts in per_item.values():
            sum_sq = sum((counts[label] / m) ** 2 for label in label_set)
            p_bar += sum_sq
        p_bar /= n
        pe = sum(value**2 for value in p.values())
        if math.isclose(1 - pe, 0.0):
            return float("nan")
        return (p_bar - pe) / (1 - pe)


class ActiveLearningSampler:
    """Selects items for labeling based on model scores."""

    def __init__(self, strategy: str = "uncertainty") -> None:
        self.strategy = strategy

    def select(
        self, scored_items: Sequence[Tuple[str, Sequence[float]]], batch_size: int
    ) -> List[str]:
        if self.strategy == "uncertainty":
            scored = sorted(
                scored_items, key=lambda item: self._entropy(item[1]), reverse=True
            )
        elif self.strategy == "margin":
            scored = sorted(scored_items, key=lambda item: self._margin(item[1]))
        else:
            raise ValueError(f"Unsupported strategy: {self.strategy}")
        return [item_id for item_id, _ in scored[:batch_size]]

    @staticmethod
    def _entropy(probabilities: Sequence[float]) -> float:
        return -sum(p * math.log(p + 1e-12, 2) for p in probabilities)

    @staticmethod
    def _margin(probabilities: Sequence[float]) -> float:
        if len(probabilities) < 2:
            return 0.0
        sorted_probs = sorted(probabilities, reverse=True)
        return sorted_probs[0] - sorted_probs[1]


class InstructionTemplateManager:
    """Stores and retrieves instruction templates."""

    def __init__(self) -> None:
        self.templates: Dict[str, InstructionTemplate] = {}

    def register(
        self,
        name: str,
        body: str,
        version: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InstructionTemplate:
        template_id = str(uuid.uuid4())
        template = InstructionTemplate(
            template_id=template_id,
            name=name,
            body=body,
            version=version,
            metadata=metadata or {},
        )
        self.templates[template_id] = template
        return template

    def latest(self, name: str) -> Optional[InstructionTemplate]:
        candidates = [
            template for template in self.templates.values() if template.name == name
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda template: template.version)

    def get(self, template_id: str) -> InstructionTemplate:
        return self.templates[template_id]


class DatasetManager:
    """Handles dataset lifecycle, anonymisation, and versioning."""

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.versions: Dict[str, DatasetVersion] = {}
        self.audit_log = AuditLog(project_id="dataset_manager")

    def create_version(
        self, name: str, records: Sequence[MutableMapping[str, Any]], description: str
    ) -> DatasetVersion:
        version_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        path = self.storage_dir / f"{name}_{version_id}.json"
        path.write_text(json.dumps(list(records), indent=2))
        checksum = str(uuid.uuid5(uuid.NAMESPACE_URL, path.read_text()))
        dataset_version = DatasetVersion(
            version_id=version_id,
            created_at=datetime.now(timezone.utc),
            data_path=path,
            description=description,
            checksum=checksum,
        )
        self.versions[version_id] = dataset_version
        self.audit_log.log("create_version", dataset_version.__dict__)
        return dataset_version

    def update_version(
        self,
        version_id: str,
        updated_records: Sequence[MutableMapping[str, Any]],
        description: str,
    ) -> DatasetVersion:
        if version_id not in self.versions:
            raise KeyError(f"Unknown dataset version: {version_id}")
        path = self.versions[version_id].data_path
        path.write_text(json.dumps(list(updated_records), indent=2))
        checksum = str(uuid.uuid5(uuid.NAMESPACE_URL, path.read_text()))
        dataset_version = DatasetVersion(
            version_id=version_id,
            created_at=datetime.now(timezone.utc),
            data_path=path,
            description=description,
            checksum=checksum,
        )
        self.versions[version_id] = dataset_version
        self.audit_log.log("update_version", dataset_version.__dict__)
        return dataset_version

    def list_versions(self) -> List[DatasetVersion]:
        return sorted(
            self.versions.values(), key=lambda version: version.created_at, reverse=True
        )


class AuditLog:
    """Captures auditable events."""

    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self.events: List[Dict[str, Any]] = []

    def log(self, action: str, details: Dict[str, Any]) -> None:
        self.events.append(
            {
                "project_id": self.project_id,
                "action": action,
                "details": details,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def export(self) -> List[Dict[str, Any]]:
        return list(self.events)


class VersionSynchronizer:
    """Keeps different assets on the same version."""

    def __init__(self) -> None:
        self.registry: Dict[str, str] = {}

    def register(self, asset_name: str, version: str) -> None:
        self.registry[asset_name] = version

    def is_synced(self) -> bool:
        return len(set(self.registry.values())) <= 1

    def status(self) -> Dict[str, Any]:
        return {"synced": self.is_synced(), "versions": dict(self.registry)}


class DataExporter:
    """Exports annotations or datasets in various formats."""

    def export_json(self, data: Iterable[MutableMapping[str, Any]], path: Path) -> Path:
        path.write_text(json.dumps(list(data), indent=2))
        return path

    def export_csv(self, data: Iterable[MutableMapping[str, Any]], path: Path) -> Path:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = None
            for row in data:
                if writer is None:
                    writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
                    writer.writeheader()
                writer.writerow(row)
        return path


class DataImporter:
    """Imports data from multiple formats."""

    def import_json(self, path: Path) -> List[Dict[str, Any]]:
        return json.loads(path.read_text())

    def import_csv(self, path: Path) -> List[Dict[str, Any]]:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))


class DataAnonymizer:
    """Redacts personally identifiable information using heuristics."""

    def __init__(self, replacement: str = "<REDACTED>") -> None:
        self.replacement = replacement

    def anonymize(self, record: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        redacted = dict(record)
        for key, value in list(redacted.items()):
            if not isinstance(value, str):
                continue
            if self._looks_like_email(value) or self._looks_like_phone(value):
                redacted[key] = self.replacement
        return redacted

    @staticmethod
    def _looks_like_email(value: str) -> bool:
        return "@" in value and "." in value.split("@")[-1]

    @staticmethod
    def _looks_like_phone(value: str) -> bool:
        digits = [character for character in value if character.isdigit()]
        return len(digits) >= 9


class PrivacyController:
    """Validates data against privacy budgets."""

    def __init__(self, anonymizer: DataAnonymizer, policies: Dict[str, Any]) -> None:
        self.anonymizer = anonymizer
        self.policies = policies

    def enforce(self, record: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        processed = self.anonymizer.anonymize(record)
        if self.policies.get("drop_free_text") and isinstance(
            processed.get("text"), str
        ):
            processed["text"] = processed["text"][
                : self.policies.get("max_text_length", 200)
            ]
        return processed


class AccessController:
    """Role-based access control for annotation artifacts."""

    def __init__(self) -> None:
        self.roles: Dict[str, set[str]] = defaultdict(set)
        self.permissions: Dict[str, set[str]] = defaultdict(set)

    def assign_role(self, user_id: str, role: str) -> None:
        self.roles[user_id].add(role)

    def set_role_permissions(self, role: str, permissions: Iterable[str]) -> None:
        self.permissions[role] = set(permissions)

    def can(self, user_id: str, permission: str) -> bool:
        return any(
            permission in self.permissions.get(role, set())
            for role in self.roles.get(user_id, set())
        )


class MetricReporter:
    """Produces metric reports for dashboards."""

    def __init__(
        self,
        quality_checker: QualityChecker,
        agreement_calculator: InterraterAgreementCalculator,
    ) -> None:
        self.quality_checker = quality_checker
        self.agreement_calculator = agreement_calculator

    def build_report(self, records: Sequence[AnnotationRecord]) -> Dict[str, Any]:
        quality = self.quality_checker.evaluate(records)
        pairwise = self.agreement_calculator.cohen_kappa()
        pairwise_serializable = {
            f"{left}::{right}": value for (left, right), value in pairwise.items()
        }
        fleiss = self.agreement_calculator.fleiss_kappa()
        return {
            "quality": quality,
            "pairwise_kappa": pairwise_serializable,
            "fleiss_kappa": fleiss,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


class AlertService:
    """Issues alerts when metrics breach thresholds."""

    def __init__(self, alert_callback: Callable[[str, Dict[str, Any]], None]) -> None:
        self.alert_callback = alert_callback

    def evaluate(self, report: Dict[str, Any], thresholds: Dict[str, float]) -> None:
        quality = report.get("quality", {})
        for metric, threshold in thresholds.items():
            value = quality.get(metric)
            if value is None:
                continue
            if value < threshold:
                self.alert_callback(
                    "quality_threshold_breach",
                    {
                        "metric": metric,
                        "value": value,
                        "threshold": threshold,
                        "generated_at": report["generated_at"],
                    },
                )


def demo_alert_callback(event_type: str, payload: Dict[str, Any]) -> None:
    """Default alert callback used in examples."""

    print(f"ALERT: {event_type} -> {payload}")


__all__ = [name for name in globals() if not name.startswith("_")]
