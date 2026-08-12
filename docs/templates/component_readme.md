---
owner: docs@geosync
review_cadence: quarterly
last_reviewed: 2025-12-28
links:
  - docs/documentation_standardisation_playbook.md
---

# <Component Name> README

<details>
<summary>How to use this template</summary>

- Place component READMEs beside the module/package directory (e.g.,
  `src/<package>/README.md`).
- Keep the README scoped to the component; cross-link to canonical references
  in `docs/` rather than duplicating information.
- Replace placeholders and remove this guidance section before publishing.

</details>

## Purpose

Describe the role of the component, the systems it interacts with, and
measurable objectives (SLOs, throughput targets, etc.).

## Key Responsibilities

- Primary behaviour 1
- Primary behaviour 2

## Public Interfaces

| Interface | Type | Location | Description |
| --------- | ---- | -------- | ----------- |
| `function_or_class` | Python | `path/to/file.py` | Brief usage guidance |

## Configuration

- **Environment Variables:**
- **Configuration Files:**
- **Feature Flags:**

## Dependencies

- **Internal:**
- **External Services/Libraries:**

## Operational Notes

- **SLIs / Metrics:**
- **Alarms:**
- **Runbooks:** Link to relevant documents.

## Testing Strategy

- **Unit:**
- **Integration:**
- **End-to-end:**

## Changelog

| Date | Author | Change |
| ---- | ------ | ------ |
| 2025-12-28 | Docs Guild | Reviewed template metadata and validated module alignment references. |
| YYYY-MM-DD | name | Created README |
