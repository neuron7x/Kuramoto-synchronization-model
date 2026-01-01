# GitHub Actions MLOps Orchestration

This document describes the event-driven CI/CD system that governs the TradePulse
MLOps pipeline. The workflow is implemented in
`.github/workflows/mlops-orchestration.yml` and promotes deterministic training,
automated validation, artifact governance, and staged delivery across AWS, GCP,
and Azure.

## Trigger Matrix

| Trigger | Purpose |
| --- | --- |
| `push` to `main` | Continuously validates changes that affect infrastructure, orchestration scripts, or deployment descriptors. |
| `pull_request` targeting `main` | Provides pre-merge signal for feature work touching MLOps assets. |
| `workflow_dispatch` | Allows operators to launch ad-hoc training cycles, optionally selecting the dataset to ingest. |
| `schedule` (`0 3 * * 1-5`) | Executes weekday overnight training so fresh models are ready for trading hours. |

## Workflow Topology

The pipeline materialises the following jobs. Each stage is idempotent and emits
a clear artifact trail for auditability.

1. **`validate`** – Boots a Python 3.11 environment, installs the deterministic
   dependency set, and runs the focused unit tests that gate the orchestrator.
   Test diagnostics are preserved as build artifacts so failures can be
   reproduced locally.
2. **`train-model`** – Invokes `scripts.mlops.github_actions_pipeline` to
   synthesise model weights, derive evaluation metrics, and register a run in
   the file-backed `ModelRegistry`. The job can optionally request dynamic
   credentials from HashiCorp Vault when the `MLOPS_VAULT_*` secrets are present,
   ensuring we never hardcode secrets in the repository.
3. **`build-container`** – Builds the runtime Docker image with BuildKit and
   archives the result as a tarball. The stage logs into GitHub Container
   Registry using the ephemeral workflow token so images can be promoted later
   without rebuilding.
4. **`terraform-plan`** – Pins Terraform 1.6.6, runs `init`, `fmt`, `validate`,
   and (when AWS credentials are provided) `plan` against `infra/terraform/eks`.
   This guarantees that infrastructure definitions stay consistent with the
   runtime image and training artifacts.
5. **`render-manifests`** – Uses Kustomize 5.4.3 to assemble deployment
   manifests and performs a `kubectl --dry-run=client apply` for the `aws`,
   `gcp`, and `azure` contexts. Generated YAMLs are persisted for manual review
   or downstream promotion pipelines.

The jobs share artifacts via `actions/upload-artifact` rather than bespoke
storage so the workflow stays self-contained.

## Environment & Secrets

| Variable | Default | Description |
| --- | --- | --- |
| `PYTHON_VERSION` | `3.11` | Version used by validation and training jobs. |
| `TERRAFORM_VERSION` | `1.6.6` | Matches repository `versions.tf` constraints. |
| `KUSTOMIZE_VERSION` | `5.4.3` | Keeps deployment manifests reproducible. |
| `ARTIFACT_ROOT` | `artifacts/mlops` | Location for generated models and logs. |
| `REGISTRY_ROOT` | `artifacts/model-registry` | File-backed registry consumed by `ModelRegistry`. |
| `DOCKER_IMAGE` | `ghcr.io/<repo>/mlops:<sha>` | Tag assigned to the BuildKit image. |

Optional secrets unlock privileged integrations:

- `MLOPS_VAULT_ADDRESS`, `MLOPS_VAULT_ROLE`, `MLOPS_VAULT_TOKEN` – When set,
  the workflow retrieves short-lived credentials through
  `scripts.cli secrets-issue-dynamic` and stores them alongside the training
  artifacts.
- `AWS_MLOPS_ACCESS_KEY_ID`, `AWS_MLOPS_SECRET_ACCESS_KEY` – Enable Terraform to
  run a full `plan` against AWS. Without them, the job still runs `fmt` and
  `validate` and records that the plan was skipped.

## Artifacts & Registry Outputs

The orchestrator writes a structured `summary.json` which captures the run ID,
metric paths, and registry location. The model registry mirrors runs under
`artifacts/model-registry/experiments`, ensuring every training cycle is
reproducible. Artifacts uploaded to GitHub include:

- `mlops-validation-logs` – Pytest cache and diagnostics from the `validate`
  job.
- `mlops-training-artifacts` – Model JSON, metrics, run context, any optional
  dataset copy, and the registry snapshot. Model artifacts include declared
  `data_version` and `code_version` fields to describe training data and code
  lineage.
- `mlops-docker-image` – Tarball of the built Docker image ready for promotion.
- `kustomize-<cloud>-manifest` – Dry-run manifests for AWS, GCP, and Azure.

## Extending the Pipeline

- Add new validation suites by editing the `validate` job command. The Python
  cache is shared automatically via `actions/setup-python`.
- To onboard another cloud, append an entry to the `render-manifests`
  `matrix.cloud` list and update the kubeconfig template if required.
- Deployment promotion can subscribe to the uploaded manifests and container
  artifact, ensuring separation of duties between training and release steps.

## Operational Notes

- The workflow summary (visible in the GitHub Actions UI) includes the latest
  run ID and metric snapshot so trading leads can verify progress without
  downloading artifacts.
- The workflow honours the engineering deadline from the operations order: the
  schedule keeps the training cadence ready before the November 2025 cut-off and
  supports additional manual runs as needed.

## Documentation Links

- [Model Card: Market Regime Classifier](../model_cards/market_regime_classifier.md)
- [Dataset Card: Feature Store Market Snapshot](../datasets/market_feature_snapshot.md)
