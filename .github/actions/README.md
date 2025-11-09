# Reusable GitHub Actions

This directory contains custom composite actions for reuse across workflows.

## 2025 Best Practice
Composite actions reduce duplication, improve maintainability, and ensure consistency across workflows.

## Available Actions

### setup-python-env

Sets up Python environment with dependencies and intelligent caching.

**Usage:**
```yaml
- uses: ./.github/actions/setup-python-env
  with:
    python-version: '3.11'
    install-dev-deps: 'true'
    cache-key-prefix: 'myworkflow'
```

**Inputs:**
- `python-version` (optional): Python version to install (default: '3.11')
- `install-dev-deps` (optional): Install dev dependencies (default: 'false')
- `cache-key-prefix` (optional): Custom cache key prefix (default: 'pip')

**Outputs:**
- `cache-hit`: Whether the cache was successfully restored
- `python-version`: Actual Python version installed

**Features:**
- Multi-level caching (pip cache + venv)
- Security-constrained dependency installation
- Automatic verification of installation
- Grouped output for better readability

**Example:**
```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      
      - name: Setup Python with deps
        uses: ./.github/actions/setup-python-env
        with:
          python-version: '3.11'
          install-dev-deps: 'true'
      
      - name: Run tests
        run: pytest tests/
```

## Creating New Actions

### Structure
```
.github/actions/
├── action-name/
│   ├── action.yml     # Action definition
│   └── README.md      # Action documentation
└── README.md          # This file
```

### Best Practices

1. **Use composite actions for:**
   - Common setup steps (environment, dependencies)
   - Repeated configuration patterns
   - Complex multi-step operations

2. **Provide clear inputs/outputs:**
   ```yaml
   inputs:
     param-name:
       description: 'Clear description'
       required: true
       default: 'sensible-default'
   
   outputs:
     result:
       description: 'What this output contains'
       value: ${{ steps.step-id.outputs.value }}
   ```

3. **Use proper shell:**
   ```yaml
   - name: Run command
     shell: bash  # Explicit shell
     run: |
       echo "Command output"
   ```

4. **Document thoroughly:**
   - Clear description
   - Input/output documentation
   - Usage examples
   - Error handling notes

5. **Version control:**
   - Tag action versions
   - Maintain changelog
   - Test before deploying

## Testing Actions

### Local Testing
```bash
# Test action YAML syntax
yamllint .github/actions/*/action.yml

# Validate action structure
actionlint .github/actions/*/action.yml
```

### Integration Testing
Create a test workflow that uses the action:

```yaml
name: Test Custom Actions
on: [push]
jobs:
  test-action:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: ./.github/actions/your-action
        with:
          param: 'test-value'
```

## Migration Guide

### Before (Duplicated Code)
```yaml
# workflow-1.yml
- name: Set up Python
  uses: actions/setup-python@v6
  with:
    python-version: '3.11'
- name: Install deps
  run: pip install -r requirements.txt

# workflow-2.yml
- name: Set up Python
  uses: actions/setup-python@v6
  with:
    python-version: '3.11'
- name: Install deps
  run: pip install -r requirements.txt
```

### After (Reusable Action)
```yaml
# Both workflows
- uses: ./.github/actions/setup-python-env
  with:
    python-version: '3.11'
```

## Troubleshooting

### Action not found
- Ensure the action directory exists
- Check the path in `uses:` statement
- Verify `action.yml` exists and is valid

### Caching issues
- Clear caches via GitHub UI
- Update cache key when dependencies change
- Use unique cache-key-prefix for different workflows

### Permission errors
- Composite actions inherit permissions from workflow
- Set proper `permissions:` in workflow file

## References

- [GitHub Actions: Creating composite actions](https://docs.github.com/en/actions/creating-actions/creating-a-composite-action)
- [Metadata syntax for GitHub Actions](https://docs.github.com/en/actions/creating-actions/metadata-syntax-for-github-actions)
- [Reusing workflows](https://docs.github.com/en/actions/using-workflows/reusing-workflows)

---

**Maintained by**: TradePulse DevOps Team
**Last Updated**: 2025-11-09
