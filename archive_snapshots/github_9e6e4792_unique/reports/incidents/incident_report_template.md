# Incident Report Template

> Використовуйте цей шаблон під час активного інциденту, щоб фіксувати ключові дані для подальшого постмортему та аудиту. Заповнюйте розділи по мірі появи інформації.

## Incident Metadata
- **Incident ID:** `INC-YYYYMMDD-XX`
- **Severity:** SEV-1 | SEV-2 | SEV-3 | NEAR MISS
- **Status:** Open | Monitoring | Resolved
- **Commander:**
- **Primary Channel / Bridge:**
- **Declaring Team:**
- **Start Time (UTC):**
- **Detection Source:** (alert, customer report, automated check, etc.)
- **Service(s) / Component(s) Affected:**

## Summary
> Коротко опишіть, що сталося, кого зачепило та який наразі стан.

- **Current Impact:** (customer segments, transactions, data, latency, etc.)
- **Customer Communications Sent:** Yes/No — add links.
- **Mitigation in Place:**

## Timeline
> Фіксуйте ключові події у хронологічному порядку. Час — у UTC.

| Time (UTC) | Actor | Event Details |
| ---------- | ----- | -------------- |
| `2025-03-18 07:32` | On-call SRE | PagerDuty alert fired for latency breach |
|  |  |  |

## Technical Details
- **Detected Signals / Alerts:**
- **Logs / Dashboards Referenced:**
- **Hypotheses Being Investigated:**
- **Immediate Workarounds Applied:**

## Impact Assessment
- **Business Impact:** revenue at risk, client obligations, regulatory exposure.
- **Data Integrity:** corruption, loss, delay (include scope and validation steps).
- **Operational Impact:** manual interventions, degraded automations.

## Root Cause Snapshot (Interim)
> Зафіксуйте початкове розуміння причини. Остаточний аналіз проводиться в постмортемі.

- **Suspected Trigger:**
- **Contributing Factors:**
- **Safeguards That Failed or Were Missing:**

## Corrective Actions
> Сформуйте перелік дій для стабілізації та відновлення.

| Action | Owner | Status | Due Date | Notes |
| ------ | ----- | ------ | -------- | ----- |
| Restore service on standby cluster |  | ☐ Not Started / ☐ In Progress / ☐ Done |  |  |
|  |  |  |  |  |

## Communications Log
- **Stakeholders Notified:** product, compliance, leadership, partners.
- **External Updates:** status page, customer emails, regulators.
- **Next Update Due:** (time, channel, responsible person)

## Verification
- **Recovery Validation Checklist:** dashboards green, alerts quiet, customer confirmation, data reconciled.
- **Incident Closure Criteria:** document when each condition is satisfied.

## Attachments & References
- Links to dashboards, log exports, runbooks used, ticket numbers.

---
**Post-Incident Reminder:** Заплануйте постмортем не пізніше 48 годин після закриття інциденту та створіть записи у базі знань.
