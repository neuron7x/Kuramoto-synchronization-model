---
title: Application Layer Orchestration Guide
---

# Application Layer Orchestration

The `application/` package bridges domain primitives to external experiences (APIs, microservices, runtime services) while enforcing secure bootstrap, configuration hygiene, and secret handling. This guide captures how orchestration, startup, security, and secret management are structured across the application layer.

## Scope and responsibilities

- **Orchestration between domain and upper layers.** `GeoSyncSystem` and `GeoSyncOrchestrator` compose ingestion, analytics, and execution flows in [`application/system.py`](../../application/system.py) and [`application/system_orchestrator.py`](../../application/system_orchestrator.py).
- **System bootstrap and runtime hardening.** Uvicorn startup, TLS enforcement, and runtime settings live under [`application/runtime/`](../../application/runtime/).
- **Configuration, secrets, and rotation.** Secure configuration surfaces are provided by [`application/configuration/secure_store.py`](../../application/configuration/secure_store.py) and secret backends in [`application/secrets/`](../../application/secrets/).
- **Security controls.** RBAC, TLS context construction, and multi-factor helpers sit in [`application/security/`](../../application/security/).

## Directory map

| Path | Purpose | Key controls |
| --- | --- | --- |
| `application/api/` | FastAPI surface, middleware, rate limiting, idempotency, and OAuth/OIDC enforcement. | Request guards (`rate_limit.py`, `idempotency.py`), security adapters (`security.py`, `system_access.py`), GraphQL and realtime endpoints. |
| `application/microservices/` | Service registry and orchestrated services (market data, backtesting, execution). | [`ServiceRegistry`](../../application/microservices/registry.py) ensures lifecycle management; DTOs and contracts live alongside the services. |
| `application/runtime/` | Runtime bootstrap for the API server. | [`runtime/server.py`](../../application/runtime/server.py) enforces TLS (fails fast when `allow_plaintext` is false) and applies runtime log levels. |
| `application/security/` | Role-based access control, TLS context builders, and two-factor helpers. | [`rbac.py`](../../application/security/rbac.py) centralizes authorization with audit logging; [`tls.py`](../../application/security/tls.py) builds hardened SSL contexts. |
| `application/secrets/` | Secret backends, rotation policies, and secure channels. | Vault and HashiCorp clients (`vault.py`, `hashicorp.py`), rotation engine (`rotation.py`), and encrypted transport (`secure_channel.py`). |
| `application/configuration/` | Secure configuration facade over secret stores. | [`secure_store.py`](../../application/configuration/secure_store.py) wraps `SecretVault`, enforces namespace-level ACLs, and emits audit events. |

## Bootstrap and safety checklist

1. **Build a system instance** using `build_geosync_system` or `GeoSyncSystemConfig` to hydrate ingestion, feature pipeline, risk, and live loop defaults.
2. **Wire services** through `ServiceRegistry.from_system(system)` and use `GeoSyncOrchestrator` to expose ingestion/backtest/execution flows to APIs or workers.
3. **Enforce TLS**: `application/runtime/server.py` requires TLS unless explicitly permitted; `application/security/tls.py` defines cipher suites and client certificate policies.
4. **Apply RBAC**: `application/security/rbac.py` validates subjects/roles and emits audit logs via `AuditLogger` before accessing execution credentials or admin APIs.
5. **Load secrets via vaults**: `application/configuration/secure_store.py` registers namespaces and routes reads through `SecretVault`. Secret rotation is handled by `SecretRotator`, and credentials should never be embedded in settings files.

## Operational notes

- API processes should be launched through `python -m application.runtime.server` (or equivalent process supervisor) so TLS and runtime settings are applied consistently.
- CI and local environments can register isolated namespaces in the `CentralConfigurationStore` to prevent cross-tenant leakage while exercising secret rotation logic.
- When extending the layer, align new modules with the table above and reuse existing guards (rate limiting, idempotency, RBAC, TLS builders) instead of re-implementing security-sensitive code.
