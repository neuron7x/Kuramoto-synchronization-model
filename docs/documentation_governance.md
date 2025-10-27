---
owner: docs@tradepulse
review_cadence: quarterly
last_reviewed: 2025-02-14
links:
  - docs/index.md
  - DOCUMENTATION_SUMMARY.md
  - docs/documentation_quality_metrics.md
---

# Documentation Governance and Quality Framework

This playbook formalises how TradePulse plans, writes, reviews, and maintains documentation across the repository. It defines
mandatory artefacts, review cadences, and automation hooks so that documentation quality keeps pace with code changes. The
framework applies to all Markdown, Jupyter, configuration samples, and diagrams served through the documentation portal or
referenced by release materials.

## Roles and Accountability

| Role | Scope | Responsibilities | Sign-off Required |
| ---- | ----- | ---------------- | ----------------- |
| **Documentation Steward** | Cross-repo documentation strategy and tooling. | Curate the taxonomy, own MkDocs configuration, enforce style guides, and drive quarterly audits. | Changes to navigation, style guide, or documentation automation. |
| **Domain Owner** | Specific product area (e.g., indicators, execution, governance). | Ensure area-specific docs reflect current behaviour, review PRs touching their domain, and maintain runbooks/playbooks. | Feature/behaviour updates affecting their domain. |
| **Release Manager** | Pre-release validation and change management. | Verify release notes, migration guides, and DoR/DoD artefacts are linked and complete before cutover. | Release sign-off checkpoints. |
| **Quality Engineer** | Automation and documentation testing. | Operate link checkers, docstring coverage checks, and screenshot diffing as part of CI/CD quality gates. | Failing documentation quality gates. |
| **Contributors** | Authors of individual documentation updates. | Follow templates, include verification evidence, and register updates in change logs. | None; rely on reviewer approvals. |

All documentation changes must have at least one domain owner reviewer; structural changes also require approval from the
Documentation Steward.

## Documentation Taxonomy

Documentation is grouped into three tiers to keep navigation predictable and reviews targeted.

1. **Canonical References** – Authoritative specifications such as API contracts, governance controls, and architecture
   blueprints. Files live under `docs/` with stable filenames and include version tables plus backward-compatibility notes.
2. **Guides & Playbooks** – Task-oriented walkthroughs (quick starts, troubleshooting, operational handbooks) with executable
   examples or commands. Guides must end with a "Verification" section describing how to validate success.
3. **Knowledge Base Addenda** – Scenario templates, FAQs, and runbooks tied to specific incidents or experiments. These
   documents may evolve rapidly but must link to the canonical reference they extend.

Each document begins with a YAML metadata block capturing owner(s), review cadence, and last substantive update. Example:

```yaml
---
owner: indicators@tradepulse
review_cadence: quarterly
last_reviewed: 2025-02-14
links:
  - docs/indicators.md
---
```

Existing docs without front matter must be updated opportunistically; new docs require the metadata block at creation time.

## Lifecycle and Change Control

1. **Proposal** – Authors open an issue or RFC describing the documentation gap. For canonical references, attach impact
   assessment and affected components.
2. **Drafting** – Follow the relevant template from `docs/templates/` (create one if missing) and populate metadata. Screenshots
   captured via the browser tooling must be stored in `docs/assets/` and referenced with Markdown captions.
3. **Review** – Request review from the Domain Owner and Documentation Steward. Use the PR checklist to confirm link integrity,
   command validation, and example outputs.
4. **Approval** – Merge after all comments are resolved, metadata updated, and automation (see below) passes. Structural changes
   also require navigation updates (`mkdocs.yml` and `docs/index.md`).
5. **Release** – Tag documentation milestones in `DOCUMENTATION_SUMMARY.md` and, for major releases, add a "Documentation
   Changes" section to release notes.

## Style and Consistency Requirements

- **Language** – Prefer concise, active voice. Provide bilingual call-outs only when localisation is available; otherwise include
  English with optional glossary links.
- **Structure** – Use level-two headings for major sections, tables for matrices, and admonitions (`!!! note`, `!!! warning`) for
  caveats. Include verification steps or acceptance criteria at the end of guides.
- **Commands** – Shell commands must be copy-paste ready, prefixed with the minimum necessary environment variables. Annotate
  expected output when deviations are meaningful.
- **Code Snippets** – Label code fences with language identifiers and keep to ≤60 lines; longer samples should link to runnable
  scripts in `examples/` or `notebooks/`.
- **Change History** – Append a "Changelog" section to canonical references summarising dated updates with links to pull
  requests or ADRs.

## Automation and Quality Gates

Documentation-specific automation augments the repository quality gates documented in `docs/quality_gates.md`.

- **Link Integrity** – `make docs-check-links` runs nightly and on PRs touching `docs/` to prevent broken internal/external links.
- **Style Linting** – `markdownlint` executes through pre-commit; violations block merges until corrected or waived by the
  Documentation Steward.
- **Example Validation** – Notebooks in `docs/notebooks/` run via Papermill smoke tests. CLI snippets tagged with
  `<!-- verify:cli -->` are replayed during CI to confirm output drift stays within tolerance.
- **Screenshot Drift** – Visual diffs for UI docs run when assets under `docs/assets/ui/` change. Failing diffs require sign-off
  from the Product Experience owner.
- **Search Index Completeness** – MkDocs build reports highlight orphaned documents; merge requests must resolve orphaned nodes by
  updating navigation or linking from `docs/index.md`.

## Audit Cadence and Metrics

| Cadence | Activity | Output |
| ------- | -------- | ------ |
| Weekly | Triage documentation issues and review backlog. | `#docs-standup` update with owner assignments and blockers. |
| Monthly | Run link check, metadata freshness script, and accessibility lint on Markdown tables. | Metrics snapshot stored in `reports/docs/monthly/<YYYY-MM>.md`. |
| Quarterly | Deep-dive review per domain, ensuring canonical references align with shipped behaviour and ADRs. | Updated `DOCUMENTATION_SUMMARY.md` entry and issue list for remediation. |
| Post-Release | Audit release notes, upgrade guides, and quickstarts for the released version. | Completed checklist attached to release tag. |

Key quality indicators tracked in the metrics snapshot:

- Metadata coverage (% of docs with valid YAML front matter)
- Link health (broken/redirected link count)
- Example verification pass rate
- Time-to-review (median days from PR open to merge for documentation-only changes)
- Open documentation debt items (`documentation` label) ageing >30 days

## Templates and Supporting Assets

- **Templates Directory** – Store Markdown templates in `docs/templates/`. Each template includes instructions commented inside a
  `<details>` block explaining required sections.
- **Snippet Library** – Shared CLI and code snippets live under `docs/snippets/`. Authors include snippets via
  `--8<-- "snippets/<name>.md"` to centralise updates.
- **Diagram Sources** – Mermaid or PlantUML sources reside alongside exported images in `docs/assets/`. Every diagram must list
  its source file path for reproducibility.

## Integration with Tooling

- **MkDocs Navigation** – All new documents require navigation entries in `mkdocs.yml` and cross-links from `docs/index.md` to
  avoid orphaned content.
- **Search Keywords** – Include keyword lists in metadata when documents introduce new terms; MkDocs Material uses them to boost
  search relevance.
- **Versioned Releases** – When cutting a new release via `mike`, ensure the documentation site is updated and aliases point to
  the latest stable branch.
- **Local Preview** – Authors validate changes with `make docs-serve`; the command builds docs in watch mode and reports build
  warnings that must be resolved before merging.

## Continuous Improvement

- Encourage contributors to raise "Docs Debt" issues when they encounter stale content, missing verifications, or incomplete
  metadata.
- Run quarterly retrospectives comparing documentation metrics against engineering KPIs (bug reopen rate, onboarding time) to
  quantify documentation impact.
- Align documentation objectives with the roadmap by adding documentation milestones to each epic, ensuring feature delivery
  includes knowledge transfer artefacts.

Maintaining rigorous documentation governance ensures TradePulse contributors can move quickly without sacrificing accuracy,
operational resilience, or auditability.
