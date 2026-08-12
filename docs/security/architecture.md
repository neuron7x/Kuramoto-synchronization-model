---
title: Production Security Architecture
description: Segmentation, trust boundaries, and zero trust controls for the GeoSync production estate.
---

# Production Security Architecture

GeoSync production environments are segmented into defence-in-depth tiers so that ingress filtering, identity enforcement, and
data protection controls can be layered without compromising operational agility. This document summarises the network tiers,
data flow contracts, and zero trust guardrails that apply to the FastAPI control plane and its supporting services.

## Network Tiering

The production perimeter is split across an **Edge**, **DMZ**, and **Core Services** tier. Each tier carries specific inspection and
connectivity responsibilities to minimise the blast radius of a compromise.

<figure markdown>
```mermaid
--8<-- "security/assets/network_tiers.mmd"
```
<figcaption>Segmentation across the edge, DMZ, and core tiers with the cloud WAF and ingress services mediating access to the FastAPI pods.</figcaption>
</figure>

### Edge tier

- Terminate TLS at the global or regional load balancer and managed WAF, enforcing geo-fencing, bot controls, and coarse IP allow/deny lists.
- Normalise canonical headers (`Host`, `X-Forwarded-For`, `X-Request-ID`) before handing requests to the DMZ ingress tier.
- Stream raw request metadata to long-term storage for forensic correlation while redacting sensitive payload fragments.

### DMZ tier

- Kubernetes or service-mesh ingress gateways validate host headers using the `trusted_hosts` configuration surfaced by `ApiSecuritySettings`.
- Dedicated Envoy/NGINX rate-limit services apply coarse-grained quotas ahead of the FastAPI middleware to suppress volumetric attacks.
- Identity federation proxies exchange upstream identity tokens for signed JWTs that match the OAuth issuer/audience settings required by the application layer.

### Core services tier

- The FastAPI deployment and stateful dependencies (Kafka, PostgreSQL, Redis) run on isolated subnets with east-west firewalls only permitting service-mesh mTLS channels.
- Service mesh policies ensure only authorised namespaces can originate requests toward the trading control plane or downstream messaging fabric.
- Audited break-glass bastions are the only interactive access path into the core tier.

## Data Flow Constraints and Trust Boundaries

<figure markdown>
```mermaid
--8<-- "security/assets/data_trust_boundaries.mmd"
```
<figcaption>Trust boundaries governing header propagation, identity hand-offs, and telemetry fan-out.</figcaption>
</figure>

### Data flow contracts

1. **Header normalisation** – The edge WAF strips hop-by-hop headers and rewrites forwarding metadata, allowing the FastAPI WAF to trust `X-Forwarded-For` and `X-Request-ID` for rate-limiting and audit correlation.
2. **Payload sanitisation** – Upstream cloud WAF engines perform signature and anomaly inspection on full bodies, after which the FastAPI layer enforces schema-aware guards (JSON key/substring checks and payload size limits) to catch context-specific threats.
3. **Identity propagation** – OAuth/OIDC assertions are terminated in the DMZ proxy and re-signed for the internal audience defined by `GEOSYNC_OAUTH2_AUDIENCE`. mTLS client certificates are re-established inside the mesh with per-namespace trust bundles.
4. **Observability fan-out** – Every boundary emits request, security, and decision logs to the SIEM pipeline. DMZ components forward raw request metadata, while the FastAPI app emits context-rich audit events tagged with upstream correlation IDs.

### Trust boundary responsibilities

- **Boundary 0 → 1 (Public → Edge):** reject unsanctioned network ranges, apply volumetric mitigations, and enrich logs with geo/IP data.
- **Boundary 1 → 2 (Edge → DMZ):** admit only sanitised, canonicalised requests and enforce host header allow-lists and TLS policy.
- **Boundary 2 → 3 (DMZ → Core):** enforce application-layer identity, ensure mTLS handshakes use platform-trusted certificates, and attach provenance headers for downstream auditing.

## Zero Trust Enforcement

GeoSync’s zero trust controls span identity, transport, and workload policy layers and map back to the deployment manifests and runtime configuration shipped with the repository.

| Control plane element | Enforcement mechanism | Repository mapping |
| --- | --- | --- |
| Service mesh sidecars | Mutual TLS between pods, fine-grained east-west policies limiting access to Kafka/PostgreSQL | `geosync-api` deployment manifest at [`deploy/geosync-deployment.yaml`](../../deploy/geosync-deployment.yaml) mounts mesh-provisioned CA bundles via `GEOSYNC_MTLS_TRUSTED_CA_PATH` and `GEOSYNC_MTLS_REVOCATION_LIST_PATH` to integrate with the mesh. |
| Identity provider integration | OAuth2/OIDC validation for API requests; tokens re-signed by the DMZ proxy must match issuer/audience | The same deployment manifest sources `GEOSYNC_OAUTH2_ISSUER`, `GEOSYNC_OAUTH2_AUDIENCE`, and `GEOSYNC_OAUTH2_JWKS_URI` from secret stores, ensuring the FastAPI app only accepts identities minted by the central IdP. |
| Workload identities | Mesh-issued workload certificates authorise downstream access to execution venues and messaging backends | Live runner configuration in [`configs/live/default.toml`](../../configs/live/default.toml) references connectors that inherit pod identities; egress is restricted by mesh policies that couple subject-dNs with venue endpoints. |
| Observability and policy feedback | Request, security, and mesh audit logs forwarded to SIEM for anomaly detection and compliance evidence | Application-level controls exposed through `AdminApiSettings` (audit webhook, SIEM endpoint) mirror DMZ logging, providing a consolidated security telemetry pipeline. |

### Operational guardrails

- Label production namespaces (`geosync-core`, `geosync-dmz`) for automatic sidecar injection and apply namespace-wide policies that deny plaintext traffic.
- Rotate CA bundles and JWT signing keys in lockstep with the identity provider; the deployment manifest mounts these secrets so the rolling update process refreshes credentials without downtime.
- Continuously validate service-to-service authorisation via mesh policy audits and penetration tests that attempt lateral movement across namespaces.
- Mirror FastAPI audit logs and upstream WAF event identifiers in the SIEM to reconcile decisions across tiers during investigations.

## Related documentation

- [System Architecture Overview](../architecture/system_overview.md)
- [Deployment Guide](../deployment.md)
- [Rate Limits and Host Protection](../rate-limits-and-host-protection.md)
