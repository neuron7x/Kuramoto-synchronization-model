# Postmortem Template

> Мета постмортему — глибоко проаналізувати інцидент, ідентифікувати системні причини, зафіксувати рішення та попередити повторення. Зберігайте завершені документи в `reports/incidents/<year>/<incident-id>/` і посилайтеся на них у базі знань.

## Executive Summary
- **Incident ID:**
- **Date Range:**
- **Severity:**
- **Customer Impact:**
- **Resolution Timestamp:**
- **Prepared By / Reviewers:**

## Narrative
> Опис інциденту мовою, зрозумілою для бізнесу.

- Що саме сталося?
- Хто виявив проблему і як?
- Який був вплив на клієнтів і внутрішні команди?

## Detailed Timeline
> Використовуйте дані з інцидент-репорту, доповнивши їх ключовими деталями.

| Time (UTC) | Event | Notes / Links |
| ---------- | ----- | ------------- |
|  |  |  |

## Root Cause Analysis
- **Primary Root Cause:**
- **Contributing Factors:** (process gaps, tooling, people, external dependencies)
- **Why Tree / 5 Whys Summary:**
- **Safeguards That Worked:**
- **Safeguards That Failed:**

## Detection & Response Evaluation
- **Detection Quality:** Did alerts fire? Were they actionable?
- **Response Quality:** Role clarity, coordination, decision making.
- **Tooling Gaps:** dashboards, runbooks, automation missing?
- **What Slowed Us Down:** access, knowledge, approvals, tooling.

## Impact & Metrics
- **Duration:** start, detection, mitigation, resolution timestamps.
- **Users / Orders / Revenue Impacted:**
- **SLO/SLA Breaches:** include before/after metrics.
- **Data Integrity Outcome:** validated? data loss? remediation steps.

## Corrective & Preventive Actions (CAPA)
> Кожна дія має бути відслідкована до виконання. Додавайте посилання на Jira/Linear/YouTrack задачі.

| ID | Action Item | Type (Corrective/Preventive) | Owner | Due Date | Status | Evidence of Completion |
| -- | ----------- | --------------------------- | ----- | -------- | ------ | ---------------------- |
| PM-001 |  |  |  |  | ☐ / ☐ / ☑ |  |
|  |  |  |  |  |  |  |

### Validation Plan
- **Regression / Automated Tests Added:**
- **Monitoring / Alerting Updates:**
- **Runbook Updates:**
- **Training / Exercises Scheduled:**

## Knowledge Base & Follow-up
- **KB Articles / Runbooks Updated:** list links.
- **GameDay / Simulation Backlog:** future drills to confirm fix effectiveness.
- **Lessons Learned:** bullet list of actionable insights.
- **Signals to Watch Going Forward:**

## Approvals & Sign-off
- **Incident Commander:** _signature/date_
- **Service Owner:** _signature/date_
- **Risk / Compliance:** _signature/date_

---
**Retrospective Checklist**
- [ ] CAPA items registered у `reports/incidents/action_item_register.md`
- [ ] Alerts/runbooks оновлені
- [ ] Документ додано до каталогу знань і поширено серед on-call команд
