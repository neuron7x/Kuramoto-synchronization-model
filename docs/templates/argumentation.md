---
owner: [your-email@tradepulse]
review_cadence: [quarterly|monthly|as-needed]
last_reviewed: [YYYY-MM-DD]
status: [draft|review|active|deprecated]
version: [X.Y.Z]
links:
  - [related-document.md]
---

# [Document Title]

**Purpose:** [One-sentence description of this document's purpose]

**Context:** [Brief context explaining why this document exists and what problem it addresses]

---

## Executive Summary

[2-3 paragraph summary of the key argument, decision, or recommendation]

**Key Takeaway:** [One sentence capturing the essence]

---

## Problem Statement

### Current Situation
[Describe the current state without judgment]

**Symptoms:**
- [Observable problem 1]
- [Observable problem 2]
- [Observable problem 3]

**Impact:**
- [Quantified impact on users/business/engineering]
- [Example: "Costs $X per month" or "Delays releases by Y days"]

### Root Causes
[Explain why this problem exists]

1. **[Root Cause 1]**
   - Evidence: [Data, incidents, feedback supporting this]
   - Contribution: [How much does this cause contribute?]

2. **[Root Cause 2]**
   - Evidence: [Data, incidents, feedback supporting this]
   - Contribution: [How much does this cause contribute?]

---

## Proposed Solution

### Overview
[High-level description of the proposed approach]

### Core Arguments

#### Argument 1: [Main Benefit/Reason]

**Claim:** [Specific claim being made]

**Reasoning:** [Logical explanation of why this claim is true]

**Evidence:**
- [Data point, study, or example 1]
- [Data point, study, or example 2]
- [Data point, study, or example 3]

**Counterarguments Addressed:**
- **Objection:** [Potential objection to this argument]
  - **Response:** [How this objection is mitigated or refuted]

**Confidence:** [High/Medium/Low] based on [reasoning]

#### Argument 2: [Secondary Benefit/Reason]

**Claim:** [Specific claim being made]

**Reasoning:** [Logical explanation of why this claim is true]

**Evidence:**
- [Data point, study, or example 1]
- [Data point, study, or example 2]
- [Data point, study, or example 3]

**Counterarguments Addressed:**
- **Objection:** [Potential objection to this argument]
  - **Response:** [How this objection is mitigated or refuted]

**Confidence:** [High/Medium/Low] based on [reasoning]

#### Argument 3: [Additional Benefit/Reason]
[Repeat structure as needed]

---

## Alternatives Considered

### Alternative 1: [Name]

**Description:** [What is this alternative?]

**Pros:**
- [Advantage 1]
- [Advantage 2]

**Cons:**
- [Disadvantage 1]
- [Disadvantage 2]

**Why Not Chosen:** [Specific reasoning for rejection]

### Alternative 2: [Name]

**Description:** [What is this alternative?]

**Pros:**
- [Advantage 1]
- [Advantage 2]

**Cons:**
- [Disadvantage 1]
- [Disadvantage 2]

**Why Not Chosen:** [Specific reasoning for rejection]

### Alternative 3: Do Nothing

**Description:** Maintain current state without changes

**Pros:**
- [Advantage 1: No implementation cost]
- [Advantage 2: No risk of unintended consequences]

**Cons:**
- [Disadvantage 1: Problem persists]
- [Disadvantage 2: Opportunity cost]

**Why Not Chosen:** [Specific reasoning - usually cost of inaction]

---

## Decision Criteria

### Must Have (Non-Negotiable)
- [ ] [Criterion 1: e.g., "Must reduce latency below 50ms"]
- [ ] [Criterion 2: e.g., "Must not break existing APIs"]
- [ ] [Criterion 3: e.g., "Must be deployable in Q1 2026"]

### Should Have (Highly Desirable)
- [ ] [Criterion 4: e.g., "Should reduce costs by 20%"]
- [ ] [Criterion 5: e.g., "Should improve developer experience"]
- [ ] [Criterion 6: e.g., "Should integrate with existing monitoring"]

### Nice to Have (Optional)
- [ ] [Criterion 7: e.g., "Could support multi-region deployment"]
- [ ] [Criterion 8: e.g., "Could enable new use cases"]

---

## Cost-Benefit Analysis

### Investment Required

**Upfront Costs:**
- Development: [X hours/dollars]
- Testing: [Y hours/dollars]
- Migration: [Z hours/dollars]
- **Total Upfront:** [Total]

**Ongoing Costs:**
- Maintenance: [X hours/month]
- Infrastructure: [Y dollars/month]
- Training: [Z hours one-time]
- **Total Annual:** [Estimate]

### Expected Returns

**Quantifiable Benefits:**
- [Benefit 1]: [Value per time period]
- [Benefit 2]: [Value per time period]
- [Benefit 3]: [Value per time period]
- **Total Annual:** [Estimate]

**Qualitative Benefits:**
- [Benefit 1]: [Description of non-quantifiable benefit]
- [Benefit 2]: [Description of non-quantifiable benefit]
- [Benefit 3]: [Description of non-quantifiable benefit]

### Return on Investment (ROI)

**Break-Even:** [Time until costs recovered]

**ROI Calculation:**
```
Annual Return = $[benefit] - $[ongoing cost]
ROI = (Annual Return / Upfront Cost) × 100%
    = ($[return] / $[cost]) × 100%
    = [X]%
```

**Payback Period:** [Months/years]

---

## Risk Assessment

### Risk Matrix

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| [Risk 1] | [High/Medium/Low] | [High/Medium/Low] | [Strategy] |
| [Risk 2] | [High/Medium/Low] | [High/Medium/Low] | [Strategy] |
| [Risk 3] | [High/Medium/Low] | [High/Medium/Low] | [Strategy] |

### Detailed Risk Analysis

#### Risk 1: [Description]

**Probability:** [High/Medium/Low] - [Reasoning]

**Impact:** [High/Medium/Low] - [Consequences if occurs]

**Mitigation:**
- [Preventive action 1]
- [Preventive action 2]

**Contingency:** [What to do if risk materializes]

#### Risk 2: [Description]
[Repeat structure]

---

## Implementation Strategy

### Phased Approach

#### Phase 1: [Name] (Target: [Date])
**Objectives:**
- [Objective 1]
- [Objective 2]

**Deliverables:**
- [Deliverable 1]
- [Deliverable 2]

**Success Criteria:**
- [Criterion 1]
- [Criterion 2]

#### Phase 2: [Name] (Target: [Date])
[Repeat structure]

#### Phase 3: [Name] (Target: [Date])
[Repeat structure]

### Rollout Strategy

**Approach:** [Big bang / Phased / Canary / Blue-green / etc.]

**Rationale:** [Why this approach chosen]

**Rollback Plan:** [How to revert if issues arise]

---

## Success Metrics

### Key Performance Indicators (KPIs)

| Metric | Baseline | Target | Timeline | Measurement Method |
|--------|----------|--------|----------|-------------------|
| [KPI 1] | [Current] | [Goal] | [When] | [How to measure] |
| [KPI 2] | [Current] | [Goal] | [When] | [How to measure] |
| [KPI 3] | [Current] | [Goal] | [When] | [How to measure] |

### Leading Indicators

[Metrics that predict success before KPIs change]
- [Leading indicator 1]
- [Leading indicator 2]

### Validation Plan

**Pilot:** [Description of pilot/experiment to validate approach]

**Evaluation:** [How will we know if pilot succeeded?]

**Go/No-Go Criteria:** [Decision criteria for full implementation]

---

## Stakeholder Analysis

### Impacted Parties

| Stakeholder | Impact | Sentiment | Engagement Strategy |
|-------------|--------|-----------|---------------------|
| [Group 1] | [High/Medium/Low] | [Supportive/Neutral/Concerned] | [Approach] |
| [Group 2] | [High/Medium/Low] | [Supportive/Neutral/Concerned] | [Approach] |
| [Group 3] | [High/Medium/Low] | [Supportive/Neutral/Concerned] | [Approach] |

### Communication Plan

**Key Messages:**
- [Message for stakeholder group 1]
- [Message for stakeholder group 2]

**Channels:**
- [Announcement method 1]
- [Announcement method 2]

**Timeline:**
- [Date 1]: [Communication event]
- [Date 2]: [Communication event]

---

## Assumptions and Dependencies

### Assumptions

1. **[Assumption 1]**
   - Confidence: [High/Medium/Low]
   - If Wrong: [Impact of invalidation]
   - Validation: [How to verify]

2. **[Assumption 2]**
   - Confidence: [High/Medium/Low]
   - If Wrong: [Impact of invalidation]
   - Validation: [How to verify]

### Dependencies

1. **[Dependency 1]**
   - Type: [Technical/Organizational/External]
   - Status: [On Track/At Risk/Blocked]
   - Owner: [Who is responsible]
   - Contingency: [What if dependency fails]

2. **[Dependency 2]**
   [Repeat structure]

---

## Review and Approval

### Review Process

**Reviewers:**
- [ ] [Role/Name] - [Aspect being reviewed]
- [ ] [Role/Name] - [Aspect being reviewed]
- [ ] [Role/Name] - [Aspect being reviewed]

**Approval Authority:** [Who has final say]

**Review Criteria:**
- [ ] Problem statement validated
- [ ] Arguments sound and evidence-based
- [ ] Alternatives fairly evaluated
- [ ] Risks identified and mitigated
- [ ] Implementation plan realistic
- [ ] Success metrics defined

### Feedback Log

| Date | Reviewer | Feedback | Response |
|------|----------|----------|----------|
| [Date] | [Name] | [Comment] | [How addressed] |

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | [Date] | [Name] | Initial draft |
| 0.2.0 | [Date] | [Name] | Incorporated feedback from [reviewer] |
| 1.0.0 | [Date] | [Name] | Approved for implementation |

---

## Appendix

### Supporting Evidence

**Reference 1:** [Citation or link to supporting material]

**Reference 2:** [Citation or link to supporting material]

### Glossary

- **[Term 1]:** Definition
- **[Term 2]:** Definition

### Related Documents

- [Link to related ADR]
- [Link to requirements doc]
- [Link to implementation plan]

---

**Status:** [Draft/Review/Active/Deprecated]  
**Last Updated:** [YYYY-MM-DD]  
**Next Review:** [YYYY-MM-DD]

---

## Template Usage Instructions

<details>
<summary>Click to expand usage guide</summary>

### When to Use This Template

Use this template when you need to:
- Make a significant decision requiring justification
- Propose a change that requires stakeholder buy-in
- Document the rationale behind an architectural choice
- Create a business case for a technical initiative
- Argue for a particular approach over alternatives

### How to Use This Template

1. **Copy the template** to your target location
2. **Fill in YAML front matter** with accurate metadata
3. **Complete each section** in order (top to bottom)
4. **Delete inapplicable sections** if they don't add value
5. **Add sections** if you need additional structure
6. **Provide evidence** for all major claims
7. **Address counterarguments** honestly
8. **Quantify when possible** (use numbers over adjectives)
9. **Request review** from appropriate stakeholders
10. **Iterate based on feedback**

### Tips for Strong Arguments

- **Be specific:** "Reduces latency by 50%" not "Makes things faster"
- **Show your work:** Link to data, studies, examples
- **Steel-man objections:** Address strongest counterarguments
- **Admit uncertainty:** State confidence levels and assumptions
- **Separate facts from opinions:** Clear about which is which
- **Quantify trade-offs:** Help readers make informed decisions

### Common Mistakes to Avoid

- ❌ Starting with the solution (bias)
- ❌ Ignoring strong counterarguments
- ❌ Overstating confidence or benefits
- ❌ Using buzzwords instead of specifics
- ❌ Failing to consider alternatives
- ❌ Missing stakeholder concerns
- ❌ Weak or missing evidence

</details>
