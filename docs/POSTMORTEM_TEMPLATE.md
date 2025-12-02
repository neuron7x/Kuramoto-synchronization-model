# Postmortem Template

> **Policy:** Будь-який SEV1/SEV2 інцидент → обов'язковий postmortem протягом 72 годин.

---

## Incident Summary

| Field | Value |
|-------|-------|
| **Incident ID** | INC-YYYY-NNNN |
| **Severity** | SEV1 / SEV2 / SEV3 |
| **Date** | YYYY-MM-DD |
| **Duration** | X hours Y minutes |
| **Impact** | [Brief description of user/business impact] |
| **Author** | [Name] |
| **Reviewers** | [Names] |

---

## Executive Summary

_2-3 речення що сталось, чому, і що ми робимо щоб це не повторилось._

**Example:**
> On 2025-01-15, the trading system experienced a 45-minute outage due to a kill-switch trigger caused by a misconfigured position limit. This resulted in approximately $X in missed trading opportunities. We are implementing automated limit validation and improving alerting thresholds.

---

## Timeline (UTC)

| Time | Event |
|------|-------|
| HH:MM | First anomaly detected (describe what) |
| HH:MM | Alert fired: `AlertName` |
| HH:MM | On-call engineer paged |
| HH:MM | Investigation started |
| HH:MM | Root cause identified |
| HH:MM | Fix deployed / action taken |
| HH:MM | Service restored |
| HH:MM | Monitoring confirmed stable |
| HH:MM | Incident declared resolved |

---

## Root Cause Analysis

### What Happened?

_Детальний опис технічної проблеми. Що саме зламалось?_

### Why Did It Happen?

_Глибинна причина. Використовуй "5 Whys" методологію:_

1. **Why?** [First level cause]
2. **Why?** [Second level cause]
3. **Why?** [Third level cause]
4. **Why?** [Fourth level cause]
5. **Why?** [Root cause]

### Contributing Factors

- [ ] Code defect
- [ ] Configuration error
- [ ] Infrastructure failure
- [ ] External dependency failure
- [ ] Process/procedure gap
- [ ] Monitoring gap
- [ ] Documentation gap
- [ ] Human error
- [ ] Other: ___________

---

## Impact Assessment

### Quantitative Impact

| Metric | Value |
|--------|-------|
| Downtime | X hours Y minutes |
| Failed orders | N |
| Missed trading opportunities | $X |
| Affected strategies | List |
| Customer impact | None / Limited / Significant |

### Qualitative Impact

- _Impact on customer trust_
- _Regulatory implications_
- _Operational burden_

---

## Detection & Response

### How Was It Detected?

- [ ] Automated alert
- [ ] Manual observation
- [ ] Customer report
- [ ] Scheduled check
- [ ] Other: ___________

**Time to Detection (TTD):** X minutes from incident start

### Response Effectiveness

| Metric | Value | Target | Met? |
|--------|-------|--------|------|
| Time to Acknowledge | X min | 5 min | ✅/❌ |
| Time to Mitigate | X min | 30 min | ✅/❌ |
| Time to Resolve | X min | 2 hours | ✅/❌ |

### What Went Well?

1. _Example: Alert fired promptly_
2. _Example: Team responded quickly_
3. _Example: Runbook was helpful_

### What Could Be Improved?

1. _Example: Took too long to identify root cause_
2. _Example: Missing documentation for recovery procedure_
3. _Example: Alert was too noisy initially_

---

## Action Items

### Immediate (< 1 week)

| Action | Owner | Due Date | Ticket |
|--------|-------|----------|--------|
| Fix the specific bug/config | @name | YYYY-MM-DD | JIRA-XXX |
| Add missing alert | @name | YYYY-MM-DD | JIRA-XXX |
| Update runbook | @name | YYYY-MM-DD | JIRA-XXX |

### Short-term (< 1 month)

| Action | Owner | Due Date | Ticket |
|--------|-------|----------|--------|
| Improve test coverage | @name | YYYY-MM-DD | JIRA-XXX |
| Add validation checks | @name | YYYY-MM-DD | JIRA-XXX |
| Review similar components | @name | YYYY-MM-DD | JIRA-XXX |

### Long-term (< 1 quarter)

| Action | Owner | Due Date | Ticket |
|--------|-------|----------|--------|
| Architectural improvement | @name | YYYY-MM-DD | JIRA-XXX |
| Process change | @name | YYYY-MM-DD | JIRA-XXX |
| Training/documentation | @name | YYYY-MM-DD | JIRA-XXX |

---

## Lessons Learned

### Technical Lessons

1. _What did we learn about the system?_
2. _What assumptions were wrong?_
3. _What monitoring gaps existed?_

### Process Lessons

1. _What worked well in our response?_
2. _What communication could be improved?_
3. _What tools/automation would help?_

---

## Appendix

### Relevant Logs

```
[Sanitized log excerpts that illustrate the problem]
```

### Relevant Metrics/Graphs

_[Attach or link to Grafana dashboards showing the incident]_

### Related Incidents

- INC-YYYY-NNNN: [Brief description]
- INC-YYYY-NNNN: [Brief description]

### References

- [Link to incident channel/thread]
- [Link to related documentation]
- [Link to code changes/PRs]

---

## Sign-off

| Role | Name | Date |
|------|------|------|
| Author | | |
| Tech Lead | | |
| Engineering Manager | | |

---

## Postmortem Review Checklist

Before publishing:

- [ ] Timeline is accurate and complete
- [ ] Root cause is clearly identified
- [ ] Impact is quantified where possible
- [ ] Action items have owners and due dates
- [ ] Lessons learned are actionable
- [ ] Sensitive information is redacted
- [ ] Review meeting scheduled/completed
- [ ] Action items tracked in ticketing system

---

*Template version: 1.0*
*Last updated: 2025-12-02*
