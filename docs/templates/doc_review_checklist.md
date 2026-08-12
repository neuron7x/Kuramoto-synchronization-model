# Documentation Review Checklist

**Document:** [Document name and path]  
**Author:** [Author name]  
**Reviewer:** [Your name]  
**Review Date:** [YYYY-MM-DD]  
**Document Type:** [ADR/Guide/Runbook/API/Other]

---

## Review Instructions

Use this checklist to ensure documentation meets GeoSync quality standards. Check applicable items, add comments where needed, and provide overall assessment at the end.

**Legend:**
- ✅ Pass - Meets standard
- ⚠️ Minor Issues - Acceptable but could improve
- ❌ Fail - Must fix before approval
- N/A - Not applicable to this document

---

## 1. Metadata and Structure

### Front Matter
- [ ] **YAML front matter present** with all required fields
- [ ] **Owner specified** and contactable
- [ ] **Review cadence defined** and appropriate
- [ ] **Last reviewed date** is accurate
- [ ] **Links section** includes related documents
- [ ] **Status/version** indicated if applicable

**Comments:**
```
[Your comments here]
```

### Document Structure
- [ ] **Title** is clear and descriptive
- [ ] **Purpose statement** explains document's goal
- [ ] **Table of contents** present (for docs >2 pages)
- [ ] **Sections logically organized** and flow well
- [ ] **Headings use proper hierarchy** (H1 > H2 > H3)

**Comments:**
```
[Your comments here]
```

---

## 2. Content Quality

### Accuracy
- [ ] **Technical facts verified** and correct
- [ ] **Code examples tested** and working
- [ ] **Commands executable** and produce expected results
- [ ] **Links valid** and point to correct targets
- [ ] **No conflicting information** with other docs

**Comments:**
```
[Your comments here]
```

### Completeness
- [ ] **Covers stated scope** fully
- [ ] **Required sections present** per template
- [ ] **Prerequisites listed** if applicable
- [ ] **Success criteria defined** for guides
- [ ] **Edge cases addressed** or acknowledged

**Comments:**
```
[Your comments here]
```

### Clarity
- [ ] **Writing is clear** and unambiguous
- [ ] **Target audience appropriate** (beginner/intermediate/expert)
- [ ] **Jargon explained** or linked to glossary
- [ ] **Examples illustrate concepts** effectively
- [ ] **Diagrams included** where helpful

**Comments:**
```
[Your comments here]
```

---

## 3. Documentation Type-Specific

### For Architecture Decision Records (ADRs)

- [ ] **Problem statement** clearly defined
- [ ] **Decision** explicitly stated
- [ ] **Rationale** thoroughly explained
- [ ] **Alternatives considered** and evaluated
- [ ] **Consequences** (positive/negative) documented
- [ ] **Implementation status** tracked
- [ ] **Supersedes/Superseded by** links if applicable

**Comments:**
```
[Your comments here]
```

### For Guides and Tutorials

- [ ] **Prerequisites** clearly stated
- [ ] **Step-by-step instructions** easy to follow
- [ ] **Screenshots/diagrams** where helpful
- [ ] **Expected outputs** shown for commands
- [ ] **Verification section** to validate success
- [ ] **Troubleshooting section** for common issues
- [ ] **Next steps** or related guides linked

**Comments:**
```
[Your comments here]
```

### For API Documentation

- [ ] **Endpoint/function signature** correct
- [ ] **Parameters** fully documented with types
- [ ] **Return values** explained with examples
- [ ] **Error cases** documented
- [ ] **Usage examples** provided and tested
- [ ] **Authentication requirements** clear
- [ ] **Rate limits** or constraints noted

**Comments:**
```
[Your comments here]
```

### For Runbooks/Playbooks

- [ ] **Trigger/when to use** clearly stated
- [ ] **Step-by-step procedures** actionable
- [ ] **Commands** copy-pasteable
- [ ] **Decision points** with guidance
- [ ] **Rollback procedures** documented
- [ ] **Success/completion criteria** defined
- [ ] **Escalation path** if procedure fails

**Comments:**
```
[Your comments here]
```

### For Requirements Specifications

- [ ] **Requirements ID** unique and trackable
- [ ] **Pre-conditions** stated
- [ ] **Post-conditions** stated
- [ ] **Acceptance criteria** measurable
- [ ] **Priority** assigned
- [ ] **Traceability** to ADR/implementation
- [ ] **Dependencies** identified

**Comments:**
```
[Your comments here]
```

---

## 4. Style and Formatting

### Writing Style
- [ ] **Active voice** used predominantly
- [ ] **Concise** without unnecessary words
- [ ] **Consistent terminology** throughout
- [ ] **Professional tone** maintained
- [ ] **Grammar and spelling** correct

**Comments:**
```
[Your comments here]
```

### Markdown Formatting
- [ ] **Code blocks** use appropriate language tags
- [ ] **Tables** properly formatted
- [ ] **Lists** use consistent style (bullets vs numbers)
- [ ] **Emphasis** (bold/italic) used appropriately
- [ ] **No raw HTML** (unless necessary)
- [ ] **Line length** reasonable (<120 chars preferred)

**Comments:**
```
[Your comments here]
```

### Visual Elements
- [ ] **Diagrams** clear and legible
- [ ] **Screenshots** current and relevant
- [ ] **Tables** formatted consistently
- [ ] **Admonitions** (notes/warnings) used appropriately
- [ ] **Code syntax highlighting** works

**Comments:**
```
[Your comments here]
```

---

## 5. Argumentation and Justification

### For Documents Requiring Rationale
- [ ] **Problem clearly articulated** with evidence
- [ ] **Solution justified** with reasoning
- [ ] **Alternatives considered** and compared
- [ ] **Trade-offs acknowledged** honestly
- [ ] **Evidence provided** for major claims
- [ ] **Assumptions stated** explicitly
- [ ] **Risks identified** and mitigated

**Comments:**
```
[Your comments here]
```

---

## 6. Maintenance and Governance

### Sustainability
- [ ] **Ownership clear** and accepted
- [ ] **Review schedule appropriate** for volatility
- [ ] **Update triggers identified** (e.g., "review after each release")
- [ ] **Deprecation plan** if temporary doc
- [ ] **Version history** tracks major changes

**Comments:**
```
[Your comments here]
```

### Cross-References
- [ ] **Links to related docs** provided
- [ ] **Referenced by** appropriate index/parent docs
- [ ] **Not orphaned** (reachable via navigation)
- [ ] **Bidirectional links** where appropriate
- [ ] **Canonical links** used (not to copies)

**Comments:**
```
[Your comments here]
```

---

## 7. Automation and Verification

### Testability
- [ ] **Executable snippets tagged** with `<!-- verify:cli -->` if applicable
- [ ] **Examples tested** and pass
- [ ] **Notebooks validated** with Papermill if applicable
- [ ] **No hardcoded secrets** or credentials
- [ ] **Reproducible** by following instructions

**Comments:**
```
[Your comments here]
```

---

## 8. Accessibility and Inclusivity

### Accessibility
- [ ] **Alt text** for images
- [ ] **Sufficient color contrast** in diagrams
- [ ] **Tables have headers** for screen readers
- [ ] **Abbreviations explained** on first use
- [ ] **No flashing content** in animations

**Comments:**
```
[Your comments here]
```

### Inclusivity
- [ ] **Gender-neutral language** used
- [ ] **No cultural assumptions** (date formats, examples)
- [ ] **Accommodates different skill levels**
- [ ] **Avoids ableist language** (e.g., "sanity check")

**Comments:**
```
[Your comments here]
```

---

## Overall Assessment

### Summary

**Strengths:**
- [List 2-3 things done well]

**Improvements Needed:**
- [List must-fix issues]

**Optional Enhancements:**
- [List nice-to-have improvements]

### Recommendation

- [ ] ✅ **Approve** - Ready to merge as-is
- [ ] ⚠️ **Approve with Minor Changes** - Fix small issues then merge
- [ ] 🔄 **Request Changes** - Requires significant revision
- [ ] ❌ **Reject** - Fundamental issues, needs complete rewrite

**Justification:**
```
[Explain your recommendation]
```

---

## Action Items

### Required (Before Approval)
1. [ ] [Action item 1]
2. [ ] [Action item 2]
3. [ ] [Action item 3]

### Recommended (Future Improvement)
1. [ ] [Enhancement 1]
2. [ ] [Enhancement 2]

---

## Reviewer Signature

**Reviewer:** [Your name]  
**Date:** [YYYY-MM-DD]  
**Contact:** [Your email]

---

## Review History

| Date | Reviewer | Outcome | Notes |
|------|----------|---------|-------|
| [Date] | [Name] | [Approve/Changes/Reject] | [Brief note] |

---

## Template Notes

<details>
<summary>How to use this checklist</summary>

### Review Process

1. **Read document fully** before starting checklist
2. **Check applicable items** systematically
3. **Add specific comments** for flagged items
4. **Provide constructive feedback** not just criticism
5. **Recommend action** with clear reasoning
6. **Follow up** to ensure changes made if needed

### Balancing Rigor and Pragmatism

- **Critical documents** (ADRs, runbooks, security): High bar, thorough review
- **Guides and examples**: Medium bar, focus on usability
- **Experimental/temporary**: Light review, ensure not misleading

### Common Review Mistakes

- ❌ Being too pedantic about minor style issues
- ❌ Approving without actually reading
- ❌ Focusing only on technical accuracy, ignoring usability
- ❌ Requiring perfection before allowing merge
- ❌ Not providing specific, actionable feedback

### Tips for Effective Reviews

- ✅ Test commands and examples yourself
- ✅ Read as target audience would
- ✅ Check cross-references actually work
- ✅ Suggest improvements, don't just criticize
- ✅ Acknowledge what's done well
- ✅ Complete review within 48 hours

</details>
