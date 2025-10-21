# Data Annotation Toolkit

This toolkit bundles together utilities required to operate a production-grade
data annotation workflow.  It lives under `scripts/data_annotation` and exposes
composable classes as well as a thin CLI for common tasks.

## Features

* Annotation interfaces and project helpers.
* Quality scoring and agreement metrics.
* Active learning sampling strategies.
* Instruction template and dataset version lifecycle management.
* Change auditing, export/import tooling, and privacy controls.
* Alerting hooks for immediate notification when quality drifts.

## CLI Usage

```bash
python scripts/data_annotation_cli.py metrics records.json reference.json
python scripts/data_annotation_cli.py export records.json output.csv
python scripts/data_annotation_cli.py anonymize dataset.json
python scripts/data_annotation_cli.py active-learning scored.json 25 --strategy margin
```

The CLI commands output JSON payloads that can be wired into automation or
further reporting systems.
