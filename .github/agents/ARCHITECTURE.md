# DOC PR COPILOT v2 Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    PULL REQUEST (GitHub)                        │
│                                                                 │
│  - Code Changes (diff)                                          │
│  - PR Title & Description                                       │
│  - Modified Files                                               │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              DOC PR COPILOT v2 AGENT                            │
│                                                                 │
│  System Prompt: .github/agents/doc-pr-copilot-v2.md            │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                   PHASE 1: PLAN                           │ │
│  │                                                           │ │
│  │  1. Analyze PR diff                                       │ │
│  │  2. Identify changed modules/APIs                         │ │
│  │  3. Detect breaking changes                               │ │
│  │  4. Map to existing documentation                         │ │
│  │  5. Build MODEL_OF_CHANGE                                 │ │
│  └───────────────────────────────────────────────────────────┘ │
│                         │                                       │
│                         ▼                                       │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                   PHASE 2: ACT                            │ │
│  │                                                           │ │
│  │  1. Generate DOC_SUMMARY                                  │ │
│  │     - List changes by TYPE and FILE                       │ │
│  │                                                           │ │
│  │  2. Generate DOC_PATCHES                                  │ │
│  │     - UPDATE_SECTION: Modify existing content             │ │
│  │     - ADD_FILE_OR_SECTION: Create new content             │ │
│  │     - APPEND_ENTRY: Add to changelog/list                 │ │
│  │                                                           │ │
│  │  3. Flag REVIEW_NOTES                                     │ │
│  │     - Items needing human verification                    │ │
│  └───────────────────────────────────────────────────────────┘ │
│                         │                                       │
│                         ▼                                       │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                 PHASE 3: REFLECT                          │ │
│  │                                                           │ │
│  │  1. Verify correctness                                    │ │
│  │     - Match code behavior                                 │ │
│  │     - No hallucinations                                   │ │
│  │                                                           │ │
│  │  2. Apply 4C principles                                   │ │
│  │     - Clarity: Understandable                             │ │
│  │     - Conciseness: No redundancy                          │ │
│  │     - Correctness: Factual only                           │ │
│  │     - Consistency: Aligned with repo                      │ │
│  │                                                           │ │
│  │  3. Validate completeness                                 │ │
│  └───────────────────────────────────────────────────────────┘ │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STRUCTURED OUTPUT                            │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ DOC_SUMMARY                                             │   │
│  │ - [UPDATE] README.md Add new feature to overview        │   │
│  │ - [ADD] docs/api/new.md Document new API endpoint       │   │
│  │ - [UPDATE] CHANGELOG.md Record feature addition         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ DOC_PATCHES                                             │   │
│  │                                                         │   │
│  │ - FILE: README.md                                       │   │
│  │   ACTION: UPDATE_SECTION                                │   │
│  │   SECTION: "API Endpoints"                              │   │
│  │   BEFORE: |                                             │   │
│  │     - /api/v1/orders                                    │   │
│  │   AFTER: |                                              │   │
│  │     - /api/v1/orders                                    │   │
│  │     - /api/v1/strategies                                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ REVIEW_NOTES                                            │   │
│  │ - [FILE docs/api/new.md] [VERIFY_BEHAVIOR]             │   │
│  │   Confirm error response codes                          │   │
│  └─────────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                     APPLICATION                                 │
│                                                                 │
│  Options:                                                       │
│  1. Post as PR comment                                          │
│  2. Apply patches automatically                                 │
│  3. Create follow-up PR                                         │
│  4. Notify reviewers of REVIEW_NOTES                            │
└─────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Input Layer

**Sources:**
- Git diff (changed lines)
- PR metadata (title, description)
- Existing documentation files
- Code comments and docstrings

**Format:**
```
PR Title: Add strategy validation endpoint
PR Description: Implements POST /api/v1/validate for strategy validation
Diff: [file changes]
```

### 2. Processing Layer

#### Phase 1: PLAN
Builds internal model of changes:
```
MODEL_OF_CHANGE:
  type: feature
  modules: [api, validation]
  public_contracts: [REST endpoint]
  breaking_changes: false
```

#### Phase 2: ACT
Generates structured patches:
```
PATCH:
  file: docs/api.md
  action: ADD_SECTION
  content: [documentation text]
```

#### Phase 3: REFLECT
Validates output quality:
```
CHECKS:
  - correctness: match_code_behavior()
  - clarity: understandable_first_read()
  - conciseness: no_redundancy()
  - consistency: align_with_repo()
```

### 3. Output Layer

**Three-part structure:**

1. **DOC_SUMMARY** (high-level)
2. **DOC_PATCHES** (actionable)
3. **REVIEW_NOTES** (human-required)

## Data Flow

```
GitHub PR
    │
    ├─→ Extract: diff, title, description
    │
    ├─→ Load: agent prompt
    │
    ├─→ LLM Processing:
    │       │
    │       ├─→ PLAN: Analyze changes
    │       ├─→ ACT: Generate patches
    │       └─→ REFLECT: Validate quality
    │
    └─→ Output: Structured response
            │
            ├─→ DOC_SUMMARY
            ├─→ DOC_PATCHES
            └─→ REVIEW_NOTES
```

## Integration Patterns

### Pattern 1: GitHub Actions (Automated)

```yaml
on: pull_request
jobs:
  doc-review:
    steps:
      - Load agent prompt
      - Get PR diff
      - Call LLM API
      - Post comment with output
```

### Pattern 2: Bot Integration (Event-driven)

```python
@app.on('pull_request')
def handle_pr(event):
    prompt = load_agent_prompt()
    diff = get_pr_diff(event.pr)
    response = llm.chat(prompt, diff)
    post_comment(response)
```

### Pattern 3: CLI Tool (Manual)

```bash
#!/bin/bash
PROMPT=$(cat .github/agents/doc-pr-copilot-v2.md)
DIFF=$(git diff main...feature)
curl -X POST $LLM_API \
  -d "{'system': '$PROMPT', 'user': '$DIFF'}"
```

## Quality Assurance

### Input Validation
- PR must have changes
- Diff must be parseable
- Files must be in scope

### Output Validation
- DOC_SUMMARY has valid TYPE
- DOC_PATCHES have valid ACTION
- REVIEW_NOTES have valid SHORT_ID

### Correctness Checks
- No hallucinations (code-based only)
- All examples are executable
- Breaking changes are flagged

## Scalability

### Horizontal Scaling
- Process multiple PRs in parallel
- Queue system for rate limiting
- Caching for common patterns

### Performance Optimization
- Cache agent prompt
- Batch similar PRs
- Incremental diff analysis

## Error Handling

```
┌─────────────────┐
│  Input Error    │ → Return error message with guidance
├─────────────────┤
│  LLM Timeout    │ → Retry with exponential backoff
├─────────────────┤
│  Invalid Output │ → Log, alert, request manual review
├─────────────────┤
│  API Error      │ → Graceful degradation, queue for retry
└─────────────────┘
```

## Monitoring

### Key Metrics
- PRs processed per day
- Average processing time
- Patch acceptance rate
- REVIEW_NOTES frequency
- False positive rate

### Logging
```
INFO:  PR #123 processed successfully
WARN:  PR #124 has 5 REVIEW_NOTES items
ERROR: PR #125 LLM timeout, queued for retry
```

## Security Considerations

### Input Sanitization
- Validate PR source
- Sanitize user input
- Limit diff size

### Output Safety
- No code execution in patches
- Validate file paths
- Prevent path traversal

### API Security
- Secure credential storage
- Rate limiting
- Audit logging

## Extension Points

### Custom Rules
```markdown
## 2. СТАНДАРТ МОВИ (4C + CNL)

### Project-Specific Rules:
- Use "trading strategy" not "strategy"
- Include risk warnings for financial operations
- Link to compliance documentation
```

### Custom Validators
```python
def validate_financial_warnings(patch):
    if 'trading' in patch and 'risk' not in patch:
        return ValidationError("Missing risk warning")
```

### Custom Output Formats
```python
def format_as_github_issue(doc_patches):
    return f"## Documentation Updates\n{doc_patches}"
```

## Future Enhancements

### Planned Features
- [ ] Automatic patch application with PR commits
- [ ] Multi-language documentation support
- [ ] Custom validation rules per file type
- [ ] Integration with more LLM providers
- [ ] Real-time documentation preview
- [ ] Metrics dashboard

### Research Areas
- Multi-modal documentation (images, diagrams)
- Context-aware terminology extraction
- Automated example generation
- Documentation quality scoring

## Dependencies

### Required
- LLM API (OpenAI, Anthropic, etc.)
- Git for diff extraction
- GitHub API for PR interaction

### Optional
- CI/CD platform (GitHub Actions)
- Monitoring system (Prometheus, Grafana)
- Cache system (Redis)
- Queue system (RabbitMQ, AWS SQS)

## Configuration

### Agent Prompt Location
```
.github/agents/doc-pr-copilot-v2.md
```

### Customization Points
- Scope (file types)
- Principles (4C rules)
- Output format
- Validation rules

### Environment Variables
```bash
LLM_API_KEY=xxx
LLM_MODEL=gpt-4
LLM_TEMPERATURE=0.1
DOC_AGENT_ENABLED=true
```

## Deployment

### Prerequisites
1. LLM API access
2. GitHub app or action configured
3. Agent prompt deployed
4. Validation script tested

### Steps
1. Add agent configuration to repo
2. Configure CI/CD workflow
3. Test with sample PRs
4. Monitor initial runs
5. Adjust based on feedback

## Support

### Documentation
- [User Guide](../docs/DOC_PR_COPILOT_GUIDE.md)
- [Integration Guide](INTEGRATION.md)
- [4C Principles](4C-PRINCIPLES.md)

### Troubleshooting
- Check agent prompt loading
- Verify LLM API connectivity
- Review validation script output
- Examine workflow logs

---

**Architecture Version:** 2.0.0  
**Last Updated:** 2025-11-18  
**Status:** Production Ready
