---
owner: docs@tradepulse
review_cadence: quarterly
last_reviewed: 2025-12-28
links:
  - DOCUMENTATION_SUMMARY.md
  - docs/documentation_governance.md
  - docs/documentation_standardisation_playbook.md
---

# Documentation Quality Metrics Handbook

This handbook formalises how TradePulse measures and reports documentation quality.
It defines the source of truth for every documentation KPI, the automation that
produces the signals, and the operational thresholds that trigger remediation.
All metrics cover the Markdown, notebook, and asset artefacts served through the
TradePulse documentation portal and referenced by release governance materials.

## Measurement Principles

1. **Single Source of Truth** – Every KPI maps to a reproducible command or
   script. Manual edits to scorecards are prohibited; results must be derived
   from tracked artefacts or CI pipelines.
2. **Automation First** – Collection happens via scheduled workflows or
   pre-commit hooks. Humans intervene only to fix drift, not to assemble data.
3. **Actionable Thresholds** – Metrics include green/yellow/red bands with
   documented playbooks so the team can respond immediately.
4. **Traceable History** – Snapshots are stored in `reports/docs/monthly/` with
   timestamped Markdown tables. Retention is 24 months for auditability.

## KPI Catalogue

| Metric | Definition | Source | Collection Cadence | Thresholds |
| ------ | ---------- | ------ | ------------------ | ---------- |
| **Metadata Coverage** | Percentage of docs under `docs/` and repository READMEs containing valid YAML front matter. | `scripts/docs/check_front_matter.py` | Nightly scheduled workflow + PR hook | ≥98% green, 95–97% yellow, <95% red |
| **Review Freshness** | Share of documents whose `last_reviewed` date is within the configured review cadence. | `scripts/docs/check_freshness.py` | Weekly scheduled workflow | ≥90% green, 80–89% yellow, <80% red |
| **Link Health** | Number of broken or redirected links detected by `make docs-check-links`. | GitHub Actions job `docs-linkcheck` | On every PR and nightly | 0 broken = green, 1–5 yellow, >5 red |
| **Executable Snippets Pass Rate** | Ratio of CLI or notebook snippets tagged with `<!-- verify:cli -->` or Papermill manifests that pass replay tests. | `make docs-verify-snippets` | On every PR touching docs, weekly scheduled | ≥99% green, 95–98% yellow, <95% red |
| **Accessibility Table Compliance** | Percentage of Markdown tables passing `docs/accessibility/table_contrast_lint.py`. | Scheduled job `docs-accessibility` | Monthly | ≥97% green, 90–96% yellow, <90% red |
| **Documentation Review Lead Time** | Median hours from PR open to merge for `documentation` label. | GitHub REST API via `scripts/docs/review_lead_time.py` | Weekly | ≤24h green, 25–48h yellow, >48h red |
| **Search Index Coverage** | Count of orphaned documents detected by MkDocs build warnings. | `make docs-build` with `--strict` | On every PR touching navigation | 0 orphaned = green, >0 red |
| **Release Artefact Completeness** | Whether release notes include Documentation Changes section with link to scorecard. | Release checklist automation | At every release candidate | Pass/Fail |

!!! note "Script registry"
    All scripts referenced above are catalogued in `docs/templates/README.md`
    under the "Verification Scripts" section. When adding a new metric, update
    both the script registry and this handbook.

## Data Collection Pipeline

1. **CI Workflows** – `docs-metrics-nightly.yml` orchestrates nightly runs of the
   metadata, freshness, link health, and snippet replay checks. Results are
   pushed as workflow artefacts and parsed by `scripts/docs/publish_metrics.py`.
2. **Scheduled Jobs** – Monthly accessibility scans and weekly review lead-time
   reports execute via GitHub Actions schedule triggers.
3. **Local Verification** – Contributors run `make docs-quality` before opening a
   PR. The target executes front matter validation, link checks in fast mode, and
   snippet verification for changed files.
4. **Scorecard Publication** – After each nightly run, the publish script updates
   `reports/docs/monthly/<YYYY-MM>.md` with an appended entry containing KPI
   values, status emojis, and relevant issue links.

## Operational Responsibilities

| Role | Responsibilities |
| ---- | ---------------- |
| Documentation Steward | Owns the metrics pipeline, triages alerts, and curates dashboards. |
| Quality Engineer | Maintains CI jobs, ensures scripts stay compatible with supported Python versions, and reviews failed runs. |
| Domain Owners | Address stale documents or broken examples within their scope within two business days. |
| Release Manager | Confirms release artefact completeness and records sign-off in the release checklist. |

When an alert crosses the red threshold, the Documentation Steward opens an
incident ticket referencing the appropriate runbook (e.g., `docs/incident_playbooks.md`).

## Dashboards and Reporting

- **Grafana** – The `Docs Quality Overview` dashboard visualises KPI trends and
  derives SLO burn-down charts. Panels are annotated automatically when related
  issues are opened.
- **Slack Alerts** – Workflow failures send alerts to `#docs-ops` with direct
  links to remediation checklists. Yellow threshold crossings post a heads-up; red
  thresholds trigger an incident emoji and PagerDuty escalation.
- **Monthly Digest** – The Documentation Steward publishes a summary in
  `reports/docs/monthly/README.md` referencing trend highlights, outstanding
  risks, and planned remediations.

## Extending the Metrics Suite

1. Draft a proposal describing the new KPI, data source, and automation cost.
2. Implement or update scripts under `scripts/docs/` with unit tests in
   `tests/scripts/docs/`.
3. Update this handbook's KPI table and the template registry.
4. Add CI coverage by modifying `docs-metrics-nightly.yml` or creating a new
   workflow.
5. Record the addition in `DOCUMENTATION_SUMMARY.md` and announce during the
   weekly documentation stand-up.

## Verification Checklist

- [ ] `make docs-quality` passes locally.
- [ ] New or updated scripts include automated tests.
- [ ] Scorecard snapshot updated with the new data point.
- [ ] MkDocs navigation includes links to any new handbook sections.
- [ ] Release checklist references are current.

## Changelog

| Date | Change | Author |
| ---- | ------ | ------ |
| 2025-12-28 | Reviewed KPI definitions and refreshed metadata alignment with core/execution/runtime/observability modules. | Docs Guild |
| 2025-03-21 | Initial publication of the Documentation Quality Metrics Handbook. | Docs Guild |
