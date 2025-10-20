# TradePulse Dashboard Localization Strategy

## Target Locales and Market Notes

| Locale | Priority | Market Focus | Cultural Considerations |
| --- | --- | --- | --- |
| en-US | Tier-0 launch market | North American multi-asset operations | Emphasize regulatory confidence (SEC/CFTC familiarity) and operational clarity. |
| uk-UA | Tier-1 expansion | Ukrainian and regional brokers scaling electronic execution | Respect linguistic purity, leverage established Ukrainian financial terminology, and acknowledge heightened sensitivity to data sovereignty. |
| de-DE | Tier-1 expansion | DACH enterprise buy-side and treasury desks | Highlight auditability, rigorous compliance, and prefer precise, low-hype tone. |
| ja-JP | Tier-1 expansion | Japanese institutional desks balancing domestic and global flows | Maintain formal politeness, stress reliability and quantitative evidence. |

## Voice, Tone, and Messaging Guardrails

- **Approved voice**: Analytical, trustworthy, and calm across all locales. Avoid speculative language; every promise must be defensible.
- **Tone adjustments**:
  - en-US: confident and action-led while remaining concise.
  - uk-UA: supportive and transparent with careful terminology choices.
  - de-DE: authoritative, factual, and free of marketing superlatives.
  - ja-JP: formal, respectful, and grounded in quantitative proof points.
- **Tone-critical messaging** must carry reviewer annotations in resource files. Localization leads should confirm adherence before release.

## Privacy and Regulatory Obligations

- **GDPR** applies to en-US (for EU data residency), uk-UA, and de-DE. Map consent logs to locale-level storage requirements.
- **CCPA** overlaps with en-US deployments; ensure opt-out flows remain visible after localization.
- **APPI** governs ja-JP with stricter breach notification and record-keeping cadence.
- **BDSG** (Germany) and Ukrainian national data laws mandate explicit cross-border transfer disclosures.
- Maintain an evergreen register of locale-specific legal copy; sync with Legal weekly.

## Native-Speaker Review Cadence

- en-US: Quarterly linguistic QA with New York trading-ops linguists.
- uk-UA: Monthly review with Kyiv localization squad.
- de-DE: Quarterly compliance-driven review in Frankfurt.
- ja-JP: Bi-monthly review alongside Tokyo regulatory advisors.

## Translation Quality KPIs

- **Terminology adherence** ≥ 98% (cross-checked via termbase automation).
- **Functional accuracy** (no broken placeholders or HTML) ≥ 99.5%.
- **Review turnaround** ≤ 3 business days from vendor delivery.
- **User feedback**: track locale-specific NPS sentiment deltas within ±2 points of en-US baseline.

## Escalation Path for Regulatory Changes

1. Localization lead logs regulation change in Jira (`LOC-*`).
2. Legal counsel triages impact within 24 hours.
3. Product compliance reviews UI copy and telemetry requirements.
4. Engineering schedules translation update via `make i18n-validate` run and vendor sync.
5. Release management blocks shipment until updated locale bundle passes QA checklist.

