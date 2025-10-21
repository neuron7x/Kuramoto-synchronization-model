# TradePulse Helm Chart

This chart packages the TradePulse research and execution stack with production
hardening defaults and progressive delivery primitives.

## Features

- **Multi-strategy rollouts** – Toggle between standard Deployments and
  [Argo Rollouts](https://argoproj.github.io/argo-rollouts/) for blue/green or
  canary delivery without touching templates.
- **Resource governance** – Requests/limits, PodDisruptionBudgets, and HPA
  settings ship with sensible defaults that can be tuned per environment.
- **Health management** – Liveness, readiness, and startup probes ensure
  rollouts fail fast. Optional cache warm-up jobs prepare feature stores before
  traffic is switched over.
- **Observability hooks** – Metrics and log annotations are configurable for
  Prometheus scraping and log aggregation platforms.
- **Policy-as-code ready** – The chart is validated by the OPA rules under
  `deploy/policies/opa` so CI/CD pipelines can block misconfigurations early.

## Usage

Build and publish the container image first (see `docker/build_and_verify.sh`):

```bash
./docker/build_and_verify.sh build
```

Render and review the manifests:

```bash
helm template tradepulse ./deploy/helm/tradepulse \
  --values ./deploy/helm/tradepulse/values-prod.yaml
```

Deploy progressively with Rollouts:

```bash
helm upgrade --install tradepulse ./deploy/helm/tradepulse \
  --namespace tradepulse-prod \
  --create-namespace \
  --values ./deploy/helm/tradepulse/values-prod.yaml
kubectl argo rollouts get rollout tradepulse-tradepulse
```

Smoke test the release:

```bash
helm test tradepulse
```

Override values per environment via `values-dev.yaml`, `values-canary.yaml`, or
custom files checked into your infra repository.
