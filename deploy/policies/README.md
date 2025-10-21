# TradePulse Policy-as-Code

This directory contains Open Policy Agent (OPA) rules that enforce the baseline
runtime security and reliability guarantees expected for TradePulse workloads.
The policies are designed to run with [Conftest](https://www.conftest.dev/) over
the rendered Kubernetes manifests produced by the Helm chart in
`deploy/helm/tradepulse`.

## Quick start

```bash
helm template tradepulse ./deploy/helm/tradepulse \
  --values ./deploy/helm/tradepulse/values.yaml > /tmp/tradepulse.yaml
conftest test /tmp/tradepulse.yaml --policy ./deploy/policies/opa
```

The tests fail with actionable messages when a manifest omits resource limits,
security contexts, or health probes. Integrate the checks into CI/CD pipelines
to block regressions before they reach the cluster.

## Policies

- `deployment.rego` – Enforces non-root execution, read-only filesystems,
  resource requests/limits, and liveness/readiness probes for standard
  Deployments.
- `rollout.rego` – Validates progressive delivery settings on Argo Rollouts,
  ensuring that canary steps and resource safeguards are present.
- `service.rego` – Guards Service annotations and port wiring so platform load
  balancers and service meshes remain correctly configured.

Extend the ruleset with environment-specific requirements as needed. The
container build helper (`docker/build_and_verify.sh policy`) runs these checks
whenever Helm and Conftest are available on the execution host.
