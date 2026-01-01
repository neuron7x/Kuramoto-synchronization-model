---
owner: integrations@tradepulse
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# TradePulse API Governance Overview

* Service: **TradePulse Public API**
* Release: **2025.1**
* Documentation: https://docs.tradepulse.example/api
* Default signature algorithm: `ed25519`
* Default idempotency header: `X-Idempotency-Key`
* Compatibility tier: `stable` (support window 180 days)

## Environments

| Name | Base URL |
| --- | --- |
| production | https://api.tradepulse.example |
| staging | https://staging.api.tradepulse.example |

## Routes

| Name | Method | Path | Scope | Cache | Rate limits | Throttle | Idempotency | Signature | Webhooks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| get-market-signal | GET | /v1/signals/{symbol} | signals:read | public; max-age=15; swr=30 | 180/min, 5000/hour, 40000/day | burst=12 / 60s | optional | required (ed25519 via X-TradePulse-Signature v1) | signal.published |
| create-prediction | POST | /v1/predictions | predictions:write | no-store; max-age=0; swr=0 | 30/min, 500/hour, 3000/day | burst=5 / 60s | required (X-Idempotency-Key ttl=86400s) | required (ed25519 via X-TradePulse-Signature v1) | prediction.completed |

## Contract catalog

For contract-by-contract inputs/outputs, DTOs, and examples (including interface-layer contracts), see
[`docs/api/contracts.md`](contracts.md).

## Operational guides

- [Authentication](authentication.md)
- [Error model](error_model.md)
- [Rate limits](rate_limits.md)
- [Pagination](pagination.md)

## Smoke tests

| Name | Description | Expected status | Route |
| --- | --- | --- | --- |
| signal-btc-ok | Fetch BTC-USD signal and validate structure. | 200 | get-market-signal |
| prediction-accepted | Submit canonical inference payload. | 202 | create-prediction |

## Compatibility

| Route | Minimum client version | Status | Comments |
| --- | --- | --- | --- |
| create-prediction | 2.5.0 | stable | Requires webhook consumption with exponential backoff. |

## Maintainers

- **Platform Engineering** — platform@tradepulse.example
- **Developer Experience** — devex@tradepulse.example
