# Deployment Guide

This guide outlines how to run TradePulse with Docker Compose for workstation and staging setups and how to prepare a Helm-based deployment for Kubernetes clusters. It also explains how to manage sensitive configuration and wire health checks into your automation pipelines. For a visual overview of the services involved in each environment, refer to the [architecture diagrams](docs/architecture/system_overview.md) and [feature-store topology](docs/architecture/feature_store.md) before proceeding with environment-specific steps.

## Prerequisites

Before deploying, install the following tools:

- Docker Engine 20.10+ and Docker Compose v2 for container orchestration.
- Access to a container registry where you can push the TradePulse image, if you plan to deploy to Kubernetes.
- `kubectl` configured to talk to your cluster and Helm 3.12+ for chart management.
- Python 3.11+ with `pip` so you can install dependencies using the pinned security constraints described below.

### Dependency security guardrails

⚠️ **CRITICAL**: As of 2025-11-17, the security constraint policy has been significantly enhanced to address a critical supply chain vulnerability. See [SECURITY_CONSTRAINT_POLICY.md](SECURITY_CONSTRAINT_POLICY.md) for full details.

- The repository ships with `constraints/security.txt`, which enforces exact versions of **all security-critical packages**:
  - **HTTP Stack**: `requests`, `urllib3`, `certifi`, `idna`, `charset-normalizer`
  - **Cryptography**: `cryptography`, `PyJWT` (fixes CVE-2023-50782, CVE-2024-26130, CVE-2022-29217)
  - **Templates**: `Jinja2` (XSS prevention), `PyYAML` (arbitrary code execution prevention)
  - **Data/ORM**: `SQLAlchemy`, `pydantic`, `pydantic-settings`, `pandera`

- **MANDATORY**: Always install dependencies with the constraint file to guarantee hardened versions:

  ```bash
  pip install -c constraints/security.txt -r sbom/combined-requirements.txt
  pip install -c constraints/security.txt -r requirements-dev.lock
  ```

- **Verification**: Run the security constraint verification script after installation:

  ```bash
  python scripts/verify_security_constraints.py
  # Or to auto-fix violations:
  python scripts/verify_security_constraints.py --fix
  ```

- When `pip-audit` or Dependabot reports a vulnerability in any security-critical package:
  1. Update the constraint in `constraints/security.txt` with the fixed version
  2. Re-lock dependency sets:
     ```bash
     pip install --upgrade pip-tools
     pip-compile --constraint=constraints/security.txt --no-annotate --output-file=requirements.lock --strip-extras requirements.txt
     pip-compile --constraint=constraints/security.txt --no-annotate --output-file=requirements-dev.lock --strip-extras requirements-dev.txt
     cp requirements.lock sbom/combined-requirements.txt
     ```
  3. Validate locally (lint, unit tests, smoke flows)
  4. Run security audit to verify the vulnerability is resolved:
     ```bash
     pip-audit --severity HIGH --severity CRITICAL -r sbom/combined-requirements.txt -r requirements-dev.lock
     python scripts/verify_security_constraints.py
     ```

- Commit the updated constraint and regenerated lock files. Dependabot is configured to watch `/constraints/security.txt`, so
  CVE-driven updates will surface as automated pull requests that follow the same workflow.
  See [docs/SECURITY_DEPENDENCIES.md](docs/SECURITY_DEPENDENCIES.md) for the complete dependency hardening playbook.

## Configuration Management

1. Copy the sample environment file and adjust it for your target environment:
   ```bash
   cp .env.example .env
   ```
2. Populate the `.env` file with database settings, exchange API credentials, and provider keys (`POSTGRES_*`, `BINANCE_*`, `COINBASE_*`, `KRAKEN_*`, `ALPHA_VANTAGE_API_KEY`, `IEX_CLOUD_API_KEY`, etc.).【F:.env.example†L19-L64】
3. Set observability and logging configuration so that metrics and logs are exposed on the expected ports (`METRICS_PORT`, `PROMETHEUS_PORT`, `LOG_*`).【F:.env.example†L103-L133】
4. Replace placeholder application secrets (`SECRET_KEY`, `JWT_SECRET`, OAuth tokens, SMTP/Slack/Telegram credentials) with secure values before deploying anywhere outside of local development.【F:.env.example†L135-L183】
5. Never commit populated `.env` files—store them in your secret manager or CI/CD vault and inject them during deployment.

### Secure Database Connectivity

- Provision client TLS material (root CA, client certificate, and private key) for each environment and store them in your
  secret manager. Mount them into the container at runtime or distribute them via Kubernetes Secrets/ConfigMaps as read-only
  files.
- Export the corresponding environment variables that the Hydra experiments expect (`PROD_DB_CA_FILE`, `PROD_DB_CERT_FILE`,
  `PROD_DB_KEY_FILE`, and their staging equivalents). These defaults map to `/etc/tradepulse/db/*.pem` paths in the sample
  configuration so mounting the directory at that location keeps the templates working out of the box.【F:conf/experiment/prod.yaml†L2-L6】【F:conf/experiment/stage.yaml†L2-L6】
- Ensure your database accepts only TLS-authenticated connections and requires the `verify-full` (or stronger) `sslmode` so
  hostname and certificate validation protect against downgrade attacks. The configuration loader now rejects weaker modes,
  causing application startup to fail fast if misconfigured.【F:core/config/postgres.py†L6-L43】

## Golden-Path Deployment, Rollback, and Monitoring

1. **Install Path**: Build/pull the container image (`Dockerfile`) → run workstation/staging via Docker Compose → promote with Helm/Kustomize overlays (`deploy/kustomize/overlays/*`) for Kubernetes.  
2. **Production Readiness**: Apply liveness/readiness probes from `deploy/kustomize/base/` and confirm mTLS/secret mounts render correctly via `kubectl rollout status`.  
3. **Rollback**: Use `kubectl rollout undo deployment/tradepulse-api -n <env>` (or `helm rollback <release> <rev>`) after capturing Prometheus snapshots; rerun `pytest tests/smoke -m smoke` as a post-rollback verification.  
4. **Monitoring & Alerting**: Prometheus scrapes `/metrics`, Alertmanager routes pages for SLO breaches, and the OpenTelemetry collector exports traces to your APM. Keep alerts for latency, error rate, queue depth, and thermodynamic free-energy spikes enabled in production.

## Docker Compose Deployment

The repository ships with a lightweight Compose stack that builds the TradePulse container and runs Prometheus for metrics scraping.【F:docker-compose.yml†L1-L12】

1. **Build images** (only required when you change the application code):
   ```bash
   docker compose build tradepulse
   ```
2. **Start the stack** using your `.env` file:
   ```bash
   docker compose --env-file .env up -d
   ```
3. **Verify runtime state**:
   ```bash
   docker compose ps
   docker compose logs -f tradepulse
   ```
4. **Stop and remove** the stack when done:
   ```bash
   docker compose down -v
   ```

### Compose Health Check

The TradePulse service exposes an HTTP health endpoint at `/health` on port 8000 by default. The docker-compose.yml includes a healthcheck that integrates with Docker's health status reporting:

```yaml
services:
  tradepulse:
    # ...existing settings...
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5.0)"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 20s
```

The default port can be customized using the `TRADEPULSE_HTTP_PORT` environment variable. For example, to use port 8001:

```bash
export TRADEPULSE_HTTP_PORT=8001
docker compose up -d
```

The smoke test script (`scripts/deploy/docker_compose_smoke.py`) automatically respects this environment variable, so health checks will target the correct port during CI validation. You can also override the health and metrics URLs explicitly using `--health-url` and `--metrics-url` command-line arguments.

Prometheus runs on port 9090 by default. Set `TRADEPULSE_PROMETHEUS_PORT` before invoking `docker compose` to bind it to an alternate host port, or let the smoke test script choose a free port automatically when 9090 is already in use. The script propagates the selected port to its Prometheus probes so that runtime diagnostics keep working even on shared CI runners.

## Kubernetes Infrastructure with Terraform and Kustomize

TradePulse now ships with first-class infrastructure code for Amazon EKS alongside Kustomize overlays for staging and production workloads. Use Terraform to provision the cluster(s) and managed node groups, then deploy the application manifests with the provided overlays.

### Provisioning EKS

1. Review the Terraform module under `infra/terraform/eks/`. It provisions a multi-AZ VPC, EKS control plane, managed node groups, and an optional Cluster Autoscaler with IRSA.【F:infra/terraform/eks/main.tf†L1-L203】
2. Initialise Terraform with the desired backend (configure S3/DynamoDB or Terraform Cloud before the first apply):

   ```bash
   terraform -chdir=infra/terraform/eks init
   ```

3. Select the workspace for the target environment and apply the corresponding variables file:

   ```bash
   terraform -chdir=infra/terraform/eks workspace select staging || terraform -chdir=infra/terraform/eks workspace new staging
   terraform -chdir=infra/terraform/eks apply -var-file=environments/staging.tfvars
   ```

   The `production.tfvars` file contains higher-capacity defaults and an additional SPOT node group tailored for mission-critical workloads.【F:infra/terraform/eks/environments/production.tfvars†L1-L27】 Stage-specific sizing lives in `staging.tfvars` for parity testing without the full production footprint.【F:infra/terraform/eks/environments/staging.tfvars†L1-L20】

4. Export AWS credentials securely (e.g., via IAM roles, AWS SSO, or Vault) before applying Terraform. Never embed static keys inside the codebase.

5. The Kubernetes and Helm providers rely on the cluster outputs created in the same plan, so Terraform waits for the control plane to stabilise before installing add-ons like the Cluster Autoscaler.【F:infra/terraform/eks/main.tf†L132-L203】

### Staging and Production Manifests

- Base manifests reside in `deploy/kustomize/base/` and encapsulate shared deployment traits, probes, and service wiring.【F:deploy/kustomize/base/deployment.yaml†L1-L74】【F:deploy/kustomize/base/service.yaml†L1-L17】【F:deploy/kustomize/base/pdb.yaml†L1-L11】
- Environment overlays extend the base with namespace scoping, image tags, scheduling policies, and topology constraints:
  - `deploy/kustomize/overlays/staging` targets the `tradepulse-staging` namespace, preserves mTLS requirements, and spreads pods across zones while staying right-sized for testing.【F:deploy/kustomize/overlays/staging/kustomization.yaml†L1-L14】【F:deploy/kustomize/overlays/staging/patches/deployment-resources.yaml†L1-L36】
  - `deploy/kustomize/overlays/production` introduces a high-priority class, strict topology distribution, and rate limiting tuned for live trading traffic in the `tradepulse-production` namespace.【F:deploy/kustomize/overlays/production/kustomization.yaml†L1-L14】【F:deploy/kustomize/overlays/production/patches/deployment-high-availability.yaml†L1-L43】
- Namespaces are declaratively managed in `deploy/kustomize/namespaces/` and should be applied before or together with the workload overlays.【F:deploy/kustomize/namespaces/staging/namespace.yaml†L1-L8】【F:deploy/kustomize/namespaces/production/namespace.yaml†L1-L8】
- Production overlays install a dedicated `PriorityClass` so the API keeps scheduling headroom even during large-scale cluster events.【F:deploy/kustomize/overlays/production/priorityclass.yaml†L1-L7】

Apply manifests directly with `kubectl` once your kubeconfig contexts are configured:

```bash
kubectl apply -k deploy/kustomize/overlays/staging
kubectl rollout status deployment/tradepulse-api -n tradepulse-staging

kubectl apply -k deploy/kustomize/overlays/production
kubectl rollout status deployment/tradepulse-api -n tradepulse-production
```

Secrets referenced by the deployments (`tradepulse-secrets`, `tradepulse-mtls-client`) must be provisioned outside of source control via your secret management workflow.

### Continuous Delivery Pipeline

The `Deploy TradePulse Environments` GitHub Actions workflow automates validation and rollouts for both environments.【F:.github/workflows/deploy-environments.yml†L1-L139】 Key characteristics:

- On every push to `main`, Terraform formatting/validation and Kustomize builds are executed before any cluster writes.
- Staging deploys automatically after validation. Production deploys once staging succeeds and the protected `production` environment gate is approved inside GitHub.
- Workflow dispatch supports ad-hoc rollouts via GitHub OIDC → AWS IAM federation. Configure short-lived access by supplying the `AWS_REGION`, `AWS_STAGING_ROLE_ARN`, `AWS_STAGING_CLUSTER_NAME`, `AWS_PRODUCTION_ROLE_ARN`, and `AWS_PRODUCTION_CLUSTER_NAME` secrets so the workflow can assume scoped roles and call `aws eks update-kubeconfig` on demand.
- `kubectl diff` runs before each apply to surface configuration drift without failing the run for expected changes.

Before enabling the workflow, create an IAM OIDC identity provider in your cloud account for `token.actions.githubusercontent.com` (or the equivalent endpoint on your platform). Bind environment-specific roles to that provider with trust policies that limit access to this repository, branch, and workflow so that every job receives ephemeral credentials with least privilege.

Document required environment reviewers inside your repository settings so production deployments remain a two-person control.

## Managing Secrets

- **Docker Compose** – export sensitive values via a `.env` file stored outside of version control. In production automation, load them from your CI/CD vault (`docker compose --env-file /path/to/rendered.env up`).
- **Kubernetes** – create Secrets straight from the same environment file:
  ```bash
  kubectl create secret generic tradepulse-secrets \
    --from-env-file=.env \
    --namespace tradepulse
  ```
  Reference the secret with `envFrom` in your Deployment so that the application receives identical configuration in every environment.
- Rotate API keys and credentials regularly. Update the Secret object and restart the workloads (`kubectl rollout restart deployment tradepulse`).
- **CI/CD cluster access** – rely on GitHub's OpenID Connect integration with your cloud provider instead of storing kubeconfigs in secrets. Create dedicated IAM roles with the minimum permissions needed to call `eks:DescribeCluster` (and supporting `sts:AssumeRole`), scope their trust policy to your repository, and allow automatic rotation by issuing fresh tokens per workflow run.

### Vault/KMS-backed exchange credentials

Define a `secret_backend` block inside each venue credential stanza to source API keys from Vault or a managed KMS instead of long-lived environment variables. The adapter selects the backend implementation while `path` or `path_env` points to the credential bundle. Optional `field_mapping` entries let you translate the payload into the uppercase keys expected by the connectors:

```toml
[[venues]]
name = "binance"
class = "execution.adapters.BinanceRESTConnector"

  [venues.credentials]
  env_prefix = "BINANCE"
  required = ["API_KEY", "API_SECRET"]

    [venues.credentials.secret_backend]
    adapter = "vault"
    path_env = "BINANCE_VAULT_PATH"

      [venues.credentials.secret_backend.field_mapping]
      API_KEY = "api_key"
      API_SECRET = "api_secret"

[[venues]]
name = "kraken"
class = "execution.adapters.KrakenRESTConnector"

  [venues.credentials]
  env_prefix = "KRAKEN"
  required = ["API_KEY", "API_SECRET"]
  optional = ["OTP"]

    [venues.credentials.secret_backend]
    adapter = "vault"
    path_env = "KRAKEN_VAULT_PATH"

      [venues.credentials.secret_backend.field_mapping]
      API_KEY = "api_key"
      API_SECRET = "api_secret"
      OTP = "otp"
```

At runtime register backend resolvers on the `LiveTradingRunner`. For example, when HashiCorp Vault agents render JSON secrets locally you can expose a resolver that reads and parses the file, while a cloud KMS adapter might call the vendor SDK and return a decoded dictionary:

```python
import json
from pathlib import Path

from interfaces.live_runner import LiveTradingRunner

def resolve_vault(path: str) -> dict[str, str]:
    return json.loads(Path(path).read_text())

runner = LiveTradingRunner(
    config_path=Path("configs/live/default.toml"),
    secret_backends={"vault": resolve_vault},
)
```

When running in production you can skip manual registration entirely. The
`LiveTradingRunner` inspects environment variables and configures centralised
secret backends automatically:

- **HashiCorp Vault** – set `TRADEPULSE_VAULT_ADDR` with either
  `TRADEPULSE_VAULT_TOKEN` or `TRADEPULSE_VAULT_TOKEN_FILE`. Optional knobs like
  `TRADEPULSE_VAULT_NAMESPACE`, `TRADEPULSE_VAULT_MOUNT`, and
  `TRADEPULSE_VAULT_KV_VERSION` control namespaces and KV engine behaviour.
  Audit metadata can be overridden via
  `TRADEPULSE_VAULT_AUDIT_ACTOR` / `TRADEPULSE_VAULT_AUDIT_IP`.
- **AWS Secrets Manager** – enable the integration with
  `TRADEPULSE_AWS_SECRETS_MANAGER_ENABLED=true` and provide a region through
  `TRADEPULSE_AWS_SECRETS_REGION`. TLS and endpoint overrides are respected via
  `TRADEPULSE_AWS_SECRETS_VERIFY` and `TRADEPULSE_AWS_SECRETS_ENDPOINT`.

With these variables in place secrets are fetched directly from Vault or AWS
Secrets Manager and rotated transparently without embedding static API keys in
configuration files.【F:interfaces/live_runner.py†L104-L171】【F:interfaces/secrets/backends.py†L1-L270】

Connectors inheriting from `AuthenticatedRESTExecutionConnector` automatically reuse the resolver for credential rotations so a Vault/KMS rotation triggers a fresh fetch before the next REST call.【F:configs/live/default.toml†L8-L36】【F:interfaces/live_runner.py†L73-L140】【F:interfaces/execution/common.py†L52-L147】

## Health Checks and Observability

- **HTTP probes** – reuse the metrics endpoint for readiness and liveness, or expose a lightweight `/healthz` endpoint that validates downstream dependencies before returning `200`.
- **Prometheus** – keep the scrape configuration aligned with your target service names (`tradepulse:8001` in Docker Compose, `<service-name>:8001` in Kubernetes).【F:deploy/prometheus.yml†L2-L7】
- **Dashboards** – point Grafana or your preferred UI to the Prometheus instance and alert on failed health probes, high error rates, or scrape gaps.

Following these practices keeps deployments reproducible across environments while giving operations teams the hooks they need for automation, alerting, and incident response.

## Release Automation

TradePulse releases are automated through GitHub Actions:

1. **Drafting** – The `Release Drafter` workflow updates a draft release on every push to `main`, grouping merged PRs by labels via `.github/release-drafter.yml`.
2. **Changelog fragments** – Every change must include a Towncrier fragment under `newsfragments/` (see `newsfragments/README.md`). When the release workflow runs it stitches the fragments into `CHANGELOG.md` and generates the GitHub release notes.
3. **SemVer tags only** – Publishing requires annotated tags that follow `vMAJOR.MINOR.PATCH`. The workflow verifies that the tag matches the version recorded in the `VERSION` file before continuing.
4. **Green CI gate** – Releases are blocked unless all checks on the tagged commit have completed successfully. The workflow inspects the commit status and fails fast if required jobs (tests, lint, build) are pending or red.
5. **Signature enforcement** – Tags must carry a cryptographic signature, and build artifacts (wheels and sdists) are signed with Sigstore before they are uploaded to the release and PyPI.

To perform a release:

```bash
# ensure CI is green and fragments exist
# create a signed SemVer tag and push it
 git tag -s vX.Y.Z -m "TradePulse vX.Y.Z"
 git push origin vX.Y.Z
```

GitHub Actions will take over from there, generate the changelog, attach the signed artifacts, and publish to PyPI once the release is approved.
