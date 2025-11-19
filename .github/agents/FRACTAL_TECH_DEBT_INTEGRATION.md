# Fractal Tech Debt Engine v2.0 Integration Guide

This document describes how to integrate the Fractal Tech Debt Engine v2.0 agent into your CI/CD workflow for systematic technical debt reduction in the TradePulse/ML-SDM ecosystem.

## Overview

The Fractal Tech Debt Engine v2.0 is a specialized LLM agent that analyzes Pull Requests for technical debt across 5 hierarchical levels (L0-L4) and provides structured recommendations for debt reduction while preserving:
- Financial behavior (PnL, risk profiles, backtest results)
- Scientific invariants (metrics, TACL/ML artifacts)
- Infrastructure stability (CI, deploy, monitoring)

## GitHub Actions Workflow Example

### Basic Tech Debt Review

```yaml
name: Tech Debt Review

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  tech-debt-analysis:
    name: Analyze Technical Debt
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

      - name: Load Fractal Tech Debt Engine configuration
        id: agent-config
        run: |
          echo "Loading Fractal Tech Debt Engine v2.0 system prompt"
          AGENT_PROMPT=$(cat .github/agents/fractal-tech-debt-engine-v2.md)
          echo "agent_prompt<<EOF" >> $GITHUB_OUTPUT
          echo "$AGENT_PROMPT" >> $GITHUB_OUTPUT
          echo "EOF" >> $GITHUB_OUTPUT

      - name: Analyze technical debt
        id: analyze
        uses: your-org/llm-action@v1
        with:
          system_prompt: ${{ steps.agent-config.outputs.agent_prompt }}
          user_input: |
            Проаналізуй цей Pull Request для виявлення технічного боргу:

            PR Title: ${{ github.event.pull_request.title }}
            PR Description: ${{ github.event.pull_request.body }}

            Режим роботи: STANDARD

            Diff:
            $(cat pr.diff)

            Надай аналіз у форматі TECH_DEBT_REPORT.
          model: "gpt-4"
          temperature: 0.1

      - name: Post tech debt report
        uses: actions/github-script@v7
        with:
          script: |
            const response = process.env.LLM_RESPONSE;
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `## 🔍 Technical Debt Analysis (Fractal Tech Debt Engine v2.0)\n\n${response}`
            });
```

### Mode-Specific Analysis

For different aggressiveness levels, you can customize the workflow:

```yaml
      - name: Determine analysis mode
        id: mode
        run: |
          # CONSERVATIVE mode for trading strategies and risk models
          if [[ $(cat pr.diff) =~ (strategies/|core/risk/|execution/) ]]; then
            echo "mode=CONSERVATIVE" >> $GITHUB_OUTPUT
          # AGGRESSIVE mode for infrastructure and tooling
          elif [[ $(cat pr.diff) =~ (infra/|tools/|scripts/) ]]; then
            echo "mode=AGGRESSIVE" >> $GITHUB_OUTPUT
          else
            echo "mode=STANDARD" >> $GITHUB_OUTPUT
          fi

      - name: Analyze technical debt with mode
        id: analyze
        uses: your-org/llm-action@v1
        with:
          system_prompt: ${{ steps.agent-config.outputs.agent_prompt }}
          user_input: |
            Проаналізуй цей Pull Request для виявлення технічного боргу:

            Режим роботи: ${{ steps.mode.outputs.mode }}

            Diff:
            $(cat pr.diff)

            Надай аналіз у форматі TECH_DEBT_REPORT.
          model: "gpt-4"
          temperature: 0.1
```

### Priority-Based Review

Focus on HIGH/CRITICAL technical debt:

```yaml
      - name: Analyze high-priority tech debt
        id: analyze-critical
        uses: your-org/llm-action@v1
        with:
          system_prompt: ${{ steps.agent-config.outputs.agent_prompt }}
          user_input: |
            Проаналізуй цей Pull Request з фокусом на HIGH/CRITICAL технічний борг:

            Пріоритетні домени:
            - Security-проблеми
            - Код, що обробляє гроші, позиції, ордери, PnL
            - Risk-модулі та розрахунки ризику
            - Data-пайплайни, які впливають на якість сигналів

            Diff:
            $(cat pr.diff)

            Надай аналіз у форматі TECH_DEBT_REPORT з фокусом на HIGH/CRITICAL пріоритети.
          model: "gpt-4"
          temperature: 0.1
```

## Manual Integration

### Command Line Usage

You can also use the agent manually with any LLM tool:

```bash
# 1. Get the PR diff
git diff main...feature-branch > pr.diff

# 2. Load the system prompt
AGENT_PROMPT=$(cat .github/agents/fractal-tech-debt-engine-v2.md)

# 3. Create the user input
cat > user_input.txt <<EOF
Проаналізуй цей Pull Request для виявлення технічного боргу:

Режим роботи: STANDARD

Diff:
$(cat pr.diff)

Надай аналіз у форматі TECH_DEBT_REPORT.
EOF

# 4. Call your LLM tool
your-llm-tool \
  --system "$AGENT_PROMPT" \
  --user "$(cat user_input.txt)" \
  --model gpt-4 \
  --temperature 0.1
```

### Python Integration

```python
#!/usr/bin/env python3
"""
Example Python integration for Fractal Tech Debt Engine v2.0
"""
import subprocess
from pathlib import Path

# Load agent system prompt
agent_prompt_path = Path(".github/agents/fractal-tech-debt-engine-v2.md")
agent_prompt = agent_prompt_path.read_text(encoding='utf-8')

# Get PR diff
diff_output = subprocess.check_output(
    ["git", "diff", "main...HEAD"],
    text=True
)

# Prepare user input
user_input = f"""
Проаналізуй цей Pull Request для виявлення технічного боргу:

Режим роботи: STANDARD

Diff:
{diff_output}

Надай аналіз у форматі TECH_DEBT_REPORT.
"""

# Call LLM (example using OpenAI API)
import openai

response = openai.ChatCompletion.create(
    model="gpt-4",
    temperature=0.1,
    messages=[
        {"role": "system", "content": agent_prompt},
        {"role": "user", "content": user_input}
    ]
)

print(response.choices[0].message.content)
```

## Operational Modes

The agent supports three operational modes:

### CONSERVATIVE Mode
Use when analyzing:
- Trading strategies (`strategies/`, `core/trading/`)
- Risk models (`core/risk/`, `rl/risk/`)
- Production pipelines (`execution/`, `markets/`)
- Backtesting logic (`backtest/`)

Focus: Small, local improvements only. No structural changes.

### STANDARD Mode (Default)
Use when analyzing:
- Data pipelines (`data/`, `analytics/`)
- Core infrastructure (`core/`, `infra/`)
- Observation systems (`observability/`, `monitoring/`)
- Configuration (`config/`, `configs/`)

Focus: Balanced approach with moderate structural changes.

### AGGRESSIVE Mode
Use when analyzing:
- Tooling and scripts (`tools/`, `scripts/`)
- Development utilities (`utils/`, `cli/`)
- Documentation (`docs/`)
- Test infrastructure (`tests/`)

Focus: Significant refactoring allowed with detailed planning.

## Output Formats

The agent provides three output formats:

### TECH_DEBT_REPORT
Comprehensive structured report with:
- Scope and summary
- Findings categorized by [LEVEL][TYPE][PRIORITY]
- Suggested changes with rationale and patches
- Test requirements
- Risk assessment
- Decision hints

### GITHUB_REVIEW_COMMENTS
File-specific comments with line numbers for direct GitHub integration.

### PATCH_ONLY
Direct diff patches ready to apply.

## Integration with CI/CD Pipeline

### Pre-Merge Analysis

```yaml
# Add to .github/workflows/pr-checks.yml
- name: Tech Debt Gate
  run: |
    # Run analysis
    python .github/agents/validate-fractal-tech-debt.py

    # Block if HIGH/CRITICAL issues found
    if grep -q "HIGH/CRITICAL" tech_debt_report.txt; then
      echo "❌ HIGH/CRITICAL technical debt detected. Review required."
      exit 1
    fi
```

### Post-Merge Tracking

```yaml
# Add to .github/workflows/tech-debt-tracking.yml
on:
  push:
    branches: [main]

jobs:
  track-debt:
    runs-on: ubuntu-latest
    steps:
      - name: Run tech debt analysis
        # Analyze and create issues for follow-up

      - name: Update tech debt dashboard
        # Update metrics and visualizations
```

## Best Practices

1. **Start with CONSERVATIVE mode** for critical paths
2. **Use STANDARD mode** for most changes
3. **Reserve AGGRESSIVE mode** for dedicated refactoring PRs
4. **Focus on HIGH/CRITICAL debt** first
5. **Track debt over time** using metrics
6. **Integrate with code review** process
7. **Run validation** before merging

## Validation

Validate your configuration:

```bash
python .github/agents/validate-fractal-tech-debt.py
```

## Troubleshooting

### Common Issues

1. **Agent not detecting debt**: Ensure diff is comprehensive and includes context
2. **Too many findings**: Use mode adjustment or priority filtering
3. **False positives**: Review anti-hallucination rules in section 10
4. **Missing context**: Provide full file context for complex changes

### Support

For issues or questions:
- Check agent configuration: `.github/agents/fractal-tech-debt-engine-v2.md`
- Review validation: `.github/agents/validate-fractal-tech-debt.py`
- See examples: `.github/agents/example-output.md`

## References

- [Fractal Tech Debt Engine v2.0 System Prompt](fractal-tech-debt-engine-v2.md)
- [Agent Configuration Schema](schema.json)
- [4C Principles](4C-PRINCIPLES.md)
- [Architecture Guide](ARCHITECTURE.md)
