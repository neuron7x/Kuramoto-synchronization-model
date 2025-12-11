# DOC PR COPILOT v2 User Guide

> **Internal LLM Prompt**: This document contains configuration and usage instructions for an LLM-based documentation agent used during TradePulse development. It is not part of the runtime system.

This guide explains how to use the DOC PR COPILOT v2 agent system for automated documentation maintenance.

## Overview

DOC PR COPILOT v2 is an LLM-based agent that:
- Analyzes Pull Request changes automatically
- Identifies documentation impact
- Generates ready-to-apply documentation patches
- Ensures documentation follows industry standards (4C principles)

## Quick Start

### For PR Authors

When you open a PR, the agent will automatically:
1. Analyze your code changes
2. Identify which documentation needs updating
3. Generate patches in the PR comments
4. Flag items that need manual review

**Example output in PR comment:**

```markdown
## 📝 Documentation Review by DOC PR COPILOT v2

### Summary
- [UPDATE] README.md - Add new API endpoint to overview
- [ADD] docs/api/webhooks.md - Document webhook API
- [UPDATE] CHANGELOG.md - Add feature to unreleased section

### Patches Ready to Apply
See detailed patches below...
```

### For Repository Maintainers

#### Setup Instructions

1. **Add agent to your workflow:**

```yaml
# .github/workflows/doc-review.yml
name: Documentation Review

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  doc-copilot:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run DOC PR COPILOT v2
        uses: your-org/llm-agent-action@v1
        with:
          agent_config: .github/agents/doc-pr-copilot-v2.md
```

2. **Configure access:**
   - Set up LLM API credentials (e.g., OpenAI API key)
   - Grant PR write permissions to the workflow
   - Configure automatic comments or commits

3. **Customize behavior:**
   - Edit `.github/agents/doc-pr-copilot-v2.md` to adjust agent behavior
   - Add project-specific terminology to the agent prompt
   - Configure which file types to monitor

## How It Works

### 1. Analysis Phase (PLAN)

The agent analyzes:
- **Code diff**: What changed in the codebase
- **PR metadata**: Title and description
- **Existing docs**: Current documentation state

It builds an internal model:
- Change type: feature/bugfix/refactor/breaking
- Affected modules and APIs
- Public contracts impacted

### 2. Generation Phase (ACT)

The agent generates:
- **DOC_SUMMARY**: High-level list of changes needed
- **DOC_PATCHES**: Ready-to-apply text patches
- **REVIEW_NOTES**: Items requiring human verification

### 3. Validation Phase (REFLECT)

The agent validates:
- **Correctness**: Does documentation match code?
- **4C Compliance**: Clarity, Conciseness, Correctness, Consistency
- **Completeness**: Are all changes covered?

## Understanding Agent Output

### DOC_SUMMARY Format

```
DOC_SUMMARY:
- [TYPE] [FILE] [description]
```

**Types:**
- `ADD` - New documentation needed
- `UPDATE` - Existing documentation needs changes
- `REMOVE` - Documentation no longer needed
- `NO_CHANGE` - No documentation impact
- `REVIEW_NEEDED` - Manual review required

**Example:**
```
DOC_SUMMARY:
- [UPDATE] README.md Add new CLI command to usage section
- [ADD] docs/api/v2.md Document new API version
- [UPDATE] CHANGELOG.md Record breaking change
```

### DOC_PATCHES Format

```
DOC_PATCHES:

- FILE: path/to/file.md
  ACTION: UPDATE_SECTION
  SECTION: "Section Title"
  BEFORE: |
    Old text (exact match required)
  AFTER: |
    New text (ready to apply)
```

**Actions:**
- `UPDATE_SECTION` - Replace existing text
- `ADD_FILE_OR_SECTION` - Create new content
- `APPEND_ENTRY` - Add to end of section (e.g., changelog)

**Example:**
```
DOC_PATCHES:

- FILE: README.md
  ACTION: UPDATE_SECTION
  SECTION: "CLI Commands"
  BEFORE: |
    tradepulse run      # Start trading
    tradepulse backtest # Run backtest
  AFTER: |
    tradepulse run      # Start trading
    tradepulse backtest # Run backtest
    tradepulse validate # Validate configuration
```

### REVIEW_NOTES Format

```
REVIEW_NOTES:
- [FILE path] [CATEGORY] Description of what to verify
```

**Categories:**
- `VERIFY_BEHAVIOR` - Confirm functionality description
- `CHECK_TERMS` - Verify terminology consistency
- `MISSING_CONTEXT` - Additional context needed
- `BREAKING_CHANGE` - Confirm breaking change impact

**Example:**
```
REVIEW_NOTES:
- [FILE docs/api/v2.md] [VERIFY_BEHAVIOR] Confirm error response codes
- [FILE README.md] [CHECK_TERMS] Verify "strategy" vs "trading strategy" usage
```

## Best Practices

### For PR Authors

1. **Write clear PR descriptions**
   - Explain what changed and why
   - Mention if it's a breaking change
   - Link to related issues

2. **Review agent suggestions**
   - Read the DOC_SUMMARY carefully
   - Apply patches that make sense
   - Address REVIEW_NOTES items

3. **Update docs proactively**
   - Update obvious documentation before review
   - The agent will validate your changes
   - Less work overall

### For Reviewers

1. **Check REVIEW_NOTES first**
   - These items need human verification
   - Confirm technical accuracy
   - Validate terminology choices

2. **Verify patches match code**
   - Agent should be accurate but validate
   - Check examples are executable
   - Ensure no outdated information

3. **Enforce 4C principles**
   - Use agent feedback to improve quality
   - Request clarity improvements
   - Maintain consistency across docs

## Configuration

### Adjusting Agent Behavior

Edit `.github/agents/doc-pr-copilot-v2.md` to customize:

**Add project-specific terms:**
```markdown
## 2. СТАНДАРТ МОВИ (4C + CNL)

### Project Terminology:
- Use "trading strategy" (not "strategy" or "trade strategy")
- Use "market feed" (not "data feed" or "market data")
- Use "order execution" (not "trade execution")
```

**Adjust scope:**
```markdown
## 1. СКОП

Ти працюєш тільки з документацією та пов'язаним текстом:
- README*, docs/**, *.md, *.rst, wiki-сторінки;
- API docs (endpoints, schemas, CLI, events);
- inline docs: docstrings, коментарі над нетривіальним кодом;
- changelog / release notes, якщо є;
- YOUR_CUSTOM_DOC_TYPE
```

**Add custom validation:**
```markdown
### REFLECT (перевірка результату):
4. Custom project checks:
   - Verify version numbers match release
   - Check all examples include error handling
   - Ensure security warnings for sensitive operations
```

## Troubleshooting

### Agent produces no output

**Possible causes:**
- PR has no code changes (docs-only)
- Changes are in non-covered file types
- Internal refactoring with no API changes

**Solution:**
- Check DOC_SUMMARY for `NO_CHANGE` message
- Verify file types are in agent scope
- Review agent logs for errors

### Patches don't apply cleanly

**Possible causes:**
- Documentation changed since PR opened
- BEFORE content doesn't match exactly
- Multiple conflicting changes

**Solution:**
- Rebase PR on latest main branch
- Manually verify BEFORE content
- Apply patches individually

### Agent suggests incorrect changes

**Possible causes:**
- Insufficient context in PR description
- Code comment ambiguity
- Edge case not covered

**Solution:**
- Improve PR description with context
- Add clarifying code comments
- Review and correct manually
- Report issue to improve agent

### REVIEW_NOTES too many items

**Possible causes:**
- Complex or large PR
- Ambiguous code changes
- Insufficient existing documentation

**Solution:**
- Break PR into smaller chunks
- Add more code comments
- Improve PR description
- Update documentation before agent runs

## Examples

### Example 1: New Feature

**PR Changes:**
```python
# Added new function
def validate_strategy(strategy: Strategy) -> ValidationResult:
    """Validate trading strategy configuration."""
    # implementation
```

**Agent Output:**
```
DOC_SUMMARY:
- [UPDATE] README.md Add validate_strategy to API reference
- [ADD] docs/api/validation.md Document validation API
- [UPDATE] CHANGELOG.md Add validation feature

DOC_PATCHES:

- FILE: README.md
  ACTION: UPDATE_SECTION
  SECTION: "API Functions"
  AFTER: |
    ### validate_strategy(strategy: Strategy) -> ValidationResult
    
    Validate trading strategy configuration before execution.
    
    **Parameters:**
    - `strategy`: Strategy instance to validate
    
    **Returns:** ValidationResult with status and errors
```

### Example 2: Breaking Change

**PR Changes:**
```python
# Changed function signature (breaking)
- def run_backtest(strategy, data):
+ def run_backtest(strategy: Strategy, data: pd.DataFrame, config: Config):
```

**Agent Output:**
```
DOC_SUMMARY:
- [UPDATE] README.md Add breaking change warning
- [UPDATE] docs/api/backtesting.md Update function signature
- [ADD] docs/migration/v2-to-v3.md Create migration guide
- [UPDATE] CHANGELOG.md Document breaking change

REVIEW_NOTES:
- [FILE docs/migration/v2-to-v3.md] [VERIFY_BEHAVIOR] Confirm migration steps
- [FILE README.md] [BREAKING_CHANGE] Verify version number and timing
```

### Example 3: Bug Fix (No Doc Changes)

**PR Changes:**
```python
# Fixed null pointer exception
- value = data.get('price')
+ value = data.get('price', 0.0)
```

**Agent Output:**
```
DOC_SUMMARY:
- [NO_CHANGE] No documentation updates required [Internal bug fix]

DOC_PATCHES:

REVIEW_NOTES:
```

## Support and Feedback

### Getting Help

1. **Check documentation:**
   - [Agent Configuration](.github/agents/README.md)
   - [Integration Guide](.github/agents/INTEGRATION.md)
   - [4C Principles](.github/agents/4C-PRINCIPLES.md)

2. **Review examples:**
   - [Example Output](.github/agents/example-output.md)
   - Real PR comments from the agent

3. **Open an issue:**
   - Label: `documentation`, `agent`
   - Include: PR link, expected vs actual behavior

### Providing Feedback

Help improve the agent:
- Report incorrect suggestions
- Share successful use cases
- Suggest new features
- Contribute improvements

### Contributing

To improve the agent:
1. Fork the repository
2. Edit `.github/agents/doc-pr-copilot-v2.md`
3. Test with example PRs
4. Submit PR with improvements

## Related Documentation

- [4C Principles](.github/agents/4C-PRINCIPLES.md) - Documentation standards
- [Integration Guide](.github/agents/INTEGRATION.md) - Technical setup
- [Example Output](.github/agents/example-output.md) - Sample responses
- [Agent Configuration](.github/agents/README.md) - All available agents

## Changelog

### v2.0.0 (Current)
- Initial implementation
- Support for MD, RST, docstrings
- 4C principles enforcement
- Structured output format (DOC_SUMMARY, DOC_PATCHES, REVIEW_NOTES)
- Ukrainian system prompt for native LLM understanding

### Planned Features
- Automatic patch application
- Multi-language support
- Custom validation rules per repository
- Integration with more LLM providers
- Enhanced context awareness
