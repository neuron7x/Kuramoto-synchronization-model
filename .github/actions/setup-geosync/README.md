# Setup GeoSync Development Environment Action

This composite action provides a consistent way to set up Python and install GeoSync dependencies across all CI jobs.

## Features

- Sets up Python with specified version
- Caches pip dependencies
- Caches Python virtual environment with unified key pattern
- Installs production and optional dev dependencies
- Respects security constraints from `constraints/security.txt`

## Usage

### Basic Usage

```yaml
- uses: ./.github/actions/setup-geosync
  with:
    python-version: '3.11'
```

### With Custom Cache Prefix

```yaml
- uses: ./.github/actions/setup-geosync
  with:
    python-version: '3.12'
    cache-prefix: venv-custom
```

### Without Dev Dependencies

```yaml
- uses: ./.github/actions/setup-geosync
  with:
    python-version: '3.11'
    install-dev: 'false'
```

## Inputs

| Name | Description | Required | Default |
|------|-------------|----------|---------|
| `python-version` | Python version to install | Yes | - |
| `install-dev` | Whether to install dev dependencies | No | `true` |
| `cache-prefix` | Prefix for venv cache key | No | `venv` |

## Outputs

| Name | Description |
|------|-------------|
| `cache-hit` | Whether the venv cache was hit (`'true'` or `'false'`) |
| `python-version` | The actual Python version that was set up |

### Using Outputs

```yaml
- uses: ./.github/actions/setup-geosync
  id: setup
  with:
    python-version: '3.11'

- name: Check cache status
  run: |
    echo "Cache hit: ${{ steps.setup.outputs.cache-hit }}"
    echo "Python version: ${{ steps.setup.outputs.python-version }}"
```

## Cache Strategy

The action uses a deterministic cache key pattern:

```
{cache-prefix}-{runner.os}-py{python-version}-{hash(requirements*.lock, constraints/security.txt)}
```

This ensures:
- Cache is invalidated when dependencies change
- Different jobs can have separate caches (via prefix)
- Cache is shared across jobs with same prefix
- OS and Python version specific caches

## Example Jobs

See `.github/workflows/tests.yml` for real-world usage examples in:
- `lint` job
- `fast-unit-tests` job
- `security-fast` job
- `full-test-suite` job
- And many more...

## Benefits

- **DRY**: Single source of truth for dependency installation
- **Consistency**: All jobs use identical setup logic
- **Performance**: Intelligent caching reduces CI time
- **Maintainability**: Updates apply to all jobs automatically
