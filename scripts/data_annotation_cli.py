"""Command line helpers for the data annotation toolkit."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable

from scripts.data_annotation import (
    ActiveLearningSampler,
    AlertService,
    AnnotationProject,
    AnnotationRecord,
    DataAnonymizer,
    DataExporter,
    DataImporter,
    InstructionTemplateManager,
    InterraterAgreementCalculator,
    MetricReporter,
    PrivacyController,
    QualityChecker,
    demo_alert_callback,
)


def _load_records(path: Path) -> Iterable[AnnotationRecord]:
    raw = json.loads(path.read_text())
    for entry in raw:
        if "created_at" in entry and isinstance(entry["created_at"], str):
            entry["created_at"] = datetime.fromisoformat(entry["created_at"])
        yield AnnotationRecord(**entry)


def _record_to_dict(record: AnnotationRecord) -> Dict[str, Any]:
    payload = asdict(record)
    payload["created_at"] = record.created_at.isoformat()
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Data annotation workflow utilities")
    sub = parser.add_subparsers(dest="command", required=True)

    metrics = sub.add_parser(
        "metrics", help="Build a metrics report from annotation records"
    )
    metrics.add_argument(
        "records", type=Path, help="Path to JSON records exported from the interface"
    )
    metrics.add_argument(
        "reference", type=Path, help="Reference labels JSON mapping item_id -> label"
    )
    metrics.add_argument(
        "--positive-label",
        default="positive",
        help="Label treated as positive for precision/recall metrics",
    )

    export = sub.add_parser("export", help="Export records to JSON or CSV")
    export.add_argument("records", type=Path, help="Path to JSON records")
    export.add_argument("output", type=Path, help="Output file path (.json or .csv)")

    anonymize = sub.add_parser("anonymize", help="Anonymize a JSON file in place")
    anonymize.add_argument("input", type=Path, help="Input JSON file")

    active = sub.add_parser("active-learning", help="Select items for active learning")
    active.add_argument(
        "scores", type=Path, help="JSON file with items and class probabilities"
    )
    active.add_argument("batch_size", type=int, help="Number of items to sample")
    active.add_argument(
        "--strategy",
        choices=["uncertainty", "margin"],
        default="uncertainty",
        help="Sampling strategy",
    )

    return parser


def handle_metrics(args: argparse.Namespace) -> None:
    records = list(_load_records(args.records))
    reference = json.loads(args.reference.read_text())
    project = AnnotationProject(
        project_id="cli",
        name="CLI Project",
        instruction=InstructionTemplateManager().register("default", "", "1.0"),
    )
    for record in records:
        project.add_record(record)
    quality_checker = QualityChecker(reference, positive_label=args.positive_label)
    agreement_calculator = InterraterAgreementCalculator(records)
    reporter = MetricReporter(quality_checker, agreement_calculator)
    report = reporter.build_report(records)

    alert_service = AlertService(demo_alert_callback)
    alert_service.evaluate(report, {"accuracy": 0.8, "f1": 0.7})

    print(json.dumps(report, indent=2))


def handle_export(args: argparse.Namespace) -> None:
    records = [_record_to_dict(record) for record in _load_records(args.records)]
    exporter = DataExporter()
    if args.output.suffix == ".json":
        exporter.export_json(records, args.output)
    elif args.output.suffix == ".csv":
        exporter.export_csv(records, args.output)
    else:
        raise SystemExit("Unsupported output format; use .json or .csv")


def handle_anonymize(args: argparse.Namespace) -> None:
    importer = DataImporter()
    data: Dict[str, Any] | Any = importer.import_json(args.input)
    anonymizer = DataAnonymizer()
    privacy = PrivacyController(
        anonymizer, {"drop_free_text": True, "max_text_length": 128}
    )
    if isinstance(data, list):
        processed = [privacy.enforce(entry) for entry in data]
    elif isinstance(data, dict):
        processed = {
            key: privacy.enforce(value) if isinstance(value, dict) else value
            for key, value in data.items()
        }
    else:
        raise SystemExit("Unsupported JSON structure for anonymization")
    args.input.write_text(json.dumps(processed, indent=2))


def handle_active_learning(args: argparse.Namespace) -> None:
    raw = json.loads(args.scores.read_text())
    scored = [(entry["item_id"], entry["probabilities"]) for entry in raw]
    sampler = ActiveLearningSampler(strategy=args.strategy)
    selected = sampler.select(scored, args.batch_size)
    print(json.dumps({"selected": selected}, indent=2))


def main(argv: list[str] | None = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    command = args.command
    if command == "metrics":
        handle_metrics(args)
    elif command == "export":
        handle_export(args)
    elif command == "anonymize":
        handle_anonymize(args)
    elif command == "active-learning":
        handle_active_learning(args)
    else:
        parser.error(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
