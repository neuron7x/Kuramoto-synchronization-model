# GitHub Agents Configuration

This directory contains configuration files for LLM-based agents that assist with repository automation and quality assurance.

## Available Agents

### DOC PR COPILOT v2

**File:** `doc-pr-copilot-v2.md`

**Purpose:** Automatically analyzes Pull Request changes and generates documentation patches to keep documentation synchronized with code changes.

**Scope:**
- README files and markdown documentation
- API documentation (endpoints, schemas, CLI)
- Inline documentation (docstrings, comments)
- Changelog and release notes

**Key Features:**
- Analyzes PR diffs to identify documentation impact
- Generates ready-to-apply documentation patches
- Ensures documentation follows 4C principles (Clarity, Conciseness, Correctness, Consistency)
- Identifies areas requiring manual review

**Output Format:**
- `DOC_SUMMARY`: High-level list of documentation changes
- `DOC_PATCHES`: Structured patches ready for application
- `REVIEW_NOTES`: Items requiring human verification

**Usage:**
The agent system prompt is designed to be used with LLM-based PR automation tools. Configure your PR bot or GitHub Action to use the system prompt from `doc-pr-copilot-v2.md` when analyzing pull requests.

### FRACTAL TECH DEBT ENGINE v2.0

**File:** `fractal-tech-debt-engine-v2.md`

**Purpose:** Systematically reduces technical debt in the TradePulse/ML-SDM ecosystem through Pull Requests, focusing on neuro-inspired algorithmic trading, neuro-economic and RL modules, data pipelines, backtesting, and infrastructure.

**Scope:**
- Trading strategies and risk models
- Data pipelines and transformations
- Neuromodulation and RL modules
- Infrastructure, CI/CD, and observability
- Experiment reproducibility

**Key Features:**
- Fractal analysis across 5 hierarchical levels (L0-L4: Repository → Module → File → Class → Function)
- Three operational modes: CONSERVATIVE, STANDARD, AGGRESSIVE
- Taxonomy of 9 technical debt types (DESIGN, CODE_STYLE, COMPLEXITY, TESTING, OBSERVABILITY, SECURITY, PERFORMANCE, DATA_QUALITY, EXPERIMENT_REPRO)
- Risk-based prioritization (HIGH/CRITICAL, MEDIUM, LOW)
- Financial and data invariant preservation
- Minimal, localized, reversible refactoring approach

**Output Format:**
- `TECH_DEBT_REPORT`: Structured findings with scope, summary, findings, suggested changes, tests, risk assessment, and decision hints
- `GITHUB_REVIEW_COMMENTS`: File-level comments with line numbers
- `PATCH_ONLY`: Direct diff patches when appropriate

**Usage:**
Use this agent to analyze Pull Requests for technical debt in the TradePulse codebase. The agent applies a consistent 5-step fractal protocol (INTENT → MISMATCH → REFACTOR PLAN → SAFE PATCH → VERIFY LOOP) at each level of analysis, ensuring changes preserve trading behavior, scientific invariants, and system stability.

**Resources:**
- [Integration Guide](FRACTAL_TECH_DEBT_INTEGRATION.md) - Detailed workflow examples and best practices
- [Example Outputs](fractal-tech-debt-example-output.md) - Sample reports and comments
- [Validation Script](validate-fractal-tech-debt.py) - Configuration validation tool

## Adding New Agents

To add a new agent:
1. Create a new markdown file in this directory
2. Include a clear role definition and scope
3. Define input/output formats
4. Document working principles and constraints
5. Update this README with the new agent information

## Integration

These agents are designed to work with:
- GitHub Actions workflows
- PR automation bots
- LLM-based code review tools
- CI/CD pipelines

Refer to `.github/workflows/` for workflow integration examples.
