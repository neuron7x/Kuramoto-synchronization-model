# Agent Integration Guide

This document describes how to integrate LLM-based agents into your CI/CD workflow.

## DOC PR COPILOT v2 Integration

### GitHub Actions Workflow Example

```yaml
name: Documentation Review

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  doc-review:
    name: Review Documentation Changes
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
      contents: read
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
      
      - name: Get PR diff
        id: diff
        run: |
          git fetch origin ${{ github.base_ref }}
          git diff origin/${{ github.base_ref }}...HEAD > pr.diff
      
      - name: Load agent configuration
        id: agent-config
        run: |
          echo "Loading DOC PR COPILOT v2 system prompt"
          AGENT_PROMPT=$(cat .github/agents/doc-pr-copilot-v2.md)
          echo "agent_prompt<<EOF" >> $GITHUB_OUTPUT
          echo "$AGENT_PROMPT" >> $GITHUB_OUTPUT
          echo "EOF" >> $GITHUB_OUTPUT
      
      - name: Analyze documentation impact
        uses: your-org/llm-action@v1
        with:
          system_prompt: ${{ steps.agent-config.outputs.agent_prompt }}
          user_input: |
            Please analyze this PR for documentation impact:
            
            PR Title: ${{ github.event.pull_request.title }}
            PR Description: ${{ github.event.pull_request.body }}
            
            Diff:
            $(cat pr.diff)
          model: "gpt-4"
          temperature: 0.1
      
      - name: Post documentation review
        uses: actions/github-script@v7
        with:
          script: |
            const response = process.env.LLM_RESPONSE;
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `## 📝 Documentation Review\n\n${response}`
            });
```

### Manual Integration

You can also use the agent manually with any LLM tool:

```bash
# 1. Get the PR diff
git diff main...feature-branch > pr.diff

# 2. Load the agent system prompt
SYSTEM_PROMPT=$(cat .github/agents/doc-pr-copilot-v2.md)

# 3. Prepare user input
USER_INPUT="Analyze this PR for documentation impact: $(cat pr.diff)"

# 4. Call your LLM API
curl https://api.openai.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d "{
    \"model\": \"gpt-4\",
    \"messages\": [
      {\"role\": \"system\", \"content\": \"$SYSTEM_PROMPT\"},
      {\"role\": \"user\", \"content\": \"$USER_INPUT\"}
    ],
    \"temperature\": 0.1
  }"
```

### Bot Integration

For PR bots (e.g., custom GitHub App):

```python
import openai
from pathlib import Path

# Load agent configuration
agent_prompt = Path(".github/agents/doc-pr-copilot-v2.md").read_text()

# Get PR data
pr_diff = get_pr_diff(pr_number)
pr_title = get_pr_title(pr_number)
pr_description = get_pr_description(pr_number)

# Prepare input
user_input = f"""
Analyze this PR for documentation impact:

PR Title: {pr_title}
PR Description: {pr_description}

Diff:
{pr_diff}
"""

# Call LLM
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": agent_prompt},
        {"role": "user", "content": user_input}
    ],
    temperature=0.1
)

# Parse response and apply patches
doc_patches = parse_doc_patches(response.choices[0].message.content)
apply_patches(doc_patches)
```

## Best Practices

1. **Use low temperature** (0.1-0.3) for consistent, factual output
2. **Include full context**: PR title, description, and diff
3. **Parse structured output**: Extract DOC_SUMMARY, DOC_PATCHES, and REVIEW_NOTES
4. **Review before applying**: Always have human review for REVIEW_NOTES items
5. **Version control**: Track agent prompt versions for reproducibility
6. **Monitor performance**: Log agent responses for quality analysis

## Security Considerations

- Never expose API keys in workflow files
- Use GitHub Secrets for sensitive configuration
- Limit agent permissions to documentation files only
- Review all automated changes before merging
- Audit agent activity through workflow logs

## Troubleshooting

### Agent produces inconsistent output
- Ensure temperature is set low (0.1-0.3)
- Verify system prompt is loaded correctly
- Check that diff includes sufficient context

### Missing documentation updates
- Verify the diff includes all changed files
- Check if changes are in agent's scope
- Review agent principles and constraints

### Incorrect patches
- Ensure BEFORE content matches exactly
- Check file paths are relative to repository root
- Verify section headers match existing documentation

## Support

For issues or questions about agent integration:
1. Check this documentation
2. Review agent configuration in `.github/agents/`
3. Open an issue with the `documentation` label
