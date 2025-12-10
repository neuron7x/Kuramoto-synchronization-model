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

### SEROTONIN STABILITY CONTROLLER (5-HT Layer) v1.0

**File:** `serotonin-stability-controller.md`

**Purpose:** Acts as a meta-cognitive stability layer for the human+AI system, dampening extremes and protecting long-term wellbeing and sustainable productivity. Inspired by the serotonergic system's role in mood regulation and impulse control.

**Scope:**
- Work pattern analysis and cognitive load monitoring
- Scope management and decision quality assessment
- Burnout prevention and pacing guidance
- Cognitive hygiene and workflow optimization
- Self-talk reframing and emotional state stabilization

**Key Features:**
- Quantitative stability scoring (serotonin_score ∈ [0.0, 1.0])
- Risk modulation guidance (increase caution / maintain / relax)
- Tempo adjustment recommendations (slow_down / keep_steady / micro-step)
- Priority shifting to prevent overcommitment
- Concrete micro-interventions (≤15 minutes each)
- Long-term guardrails to prevent pattern repetition
- Language reframing from harsh/chaotic to calm/precise

**Output Format:**
- `SEROTONIN SNAPSHOT`: Quantitative stability assessment with main risk identified
- `STABILIZING MOVES`: 3-7 immediate actions (30-90 minute horizon)
- `MEDIUM-HORIZON GUARDRAILS`: 3-5 rules for 7-30 day sustainability
- `LANGUAGE REFRAME`: Self-talk transformation from extreme to neutral

**Usage:**
Invoke this agent when:
- User expresses burnout, overwhelm, or despair
- Scope has expanded beyond reasonable bounds
- Decisions are driven by fear, panic, or mania
- Work patterns show unsustainable pace (all-nighters, no breaks)
- Language becomes extreme or self-destructive
- Too many parallel tasks or context switches

**Constraints:**
This agent does NOT provide medical, psychiatric, or pharmacological advice. It works strictly within the domain of workflow optimization, decision hygiene, and process improvement.

**Resources:**
- [Configuration File](serotonin-stability-controller.md) - Complete agent system prompt
- [Validation Script](validate-serotonin-stability.py) - Configuration validation tool

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
