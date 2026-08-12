---
owner: sre@geosync
review_cadence: quarterly
last_reviewed: 2025-12-28
links:
  - docs/incident_playbooks.md
  - docs/documentation_standardisation_playbook.md
---

# Incident Playbook: <Incident Name>

<details>
<summary>How to use this template</summary>

- Name the file `runbook_<incident>.md` and store under `docs/` or
  `docs/runbook_*.md` depending on scope.
- Maintain bilingual severity callouts if regulatory requirements demand it.
- Include verification evidence for each response step.
- Remove this block prior to publication.

</details>

## Metadata

- **Severity:** SEV-1/2/3
- **Primary Owner:**
- **Secondary Owner:**
- **Communication Channels:** #incident-warroom, PagerDuty service
- **Regulatory Obligations:**

## Detection

- **Signals / Alerts:**
- **Dashboards:**
- **Known False Positives:**

## Response Steps

| Step | Action | Owner | Evidence |
| ---- | ------ | ----- | -------- |
| 1 | | | |

## Containment

- **Immediate Mitigations:**
- **Customer Impact:**
- **Access Controls:**

## Eradication & Recovery

1. Action with verification command/output.
2. Action with rollback plan.

## Post-Incident

- **Lessons Learned:**
- **Preventive Backlog Items:**
- **Compliance Notifications:**

## Verification Checklist

- [ ] All alerts cleared
- [ ] Incident timeline archived in postmortem doc
- [ ] Follow-up tickets created

## Changelog

| Date | Author | Change |
| ---- | ------ | ------ |
| 2025-12-28 | Docs Guild | Reviewed template metadata and validated module alignment references. |
| YYYY-MM-DD | name | Initial draft |
