# export_tradepulse_schema.py

Export the TradePulse configuration JSON schema for validation and documentation.

## Description

This utility exports the JSON schema for TradePulse configuration settings. The schema can be used for:
- Validating configuration files
- Generating documentation
- IDE autocomplete and validation
- Configuration tooling integration

## Usage

### Export schema to stdout

```bash
python scripts/export_tradepulse_schema.py
```

### Export schema to file

```bash
python scripts/export_tradepulse_schema.py --output schemas/tradepulse-config.json
```

### Custom indentation

```bash
python scripts/export_tradepulse_schema.py --indent 4
```

### Combined example

```bash
python scripts/export_tradepulse_schema.py \
  --output docs/config-schema.json \
  --indent 2
```

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--output` | `None` | Destination path for schema (stdout if omitted) |
| `--indent` | `2` | JSON indentation level |

## Output Format

The generated schema is a JSON Schema Draft 7 compliant document describing all TradePulse configuration options, including:

- Field types and constraints
- Default values
- Descriptions
- Nested structures (Kuramoto, Ricci, data sources, etc.)
- Validation rules

## Exit Codes

- `0`: Success

## Examples

### Generate schema for IDE integration

```bash
python scripts/export_tradepulse_schema.py --output .vscode/tradepulse-schema.json
```

### Validate configuration against schema

```bash
# Export schema
python scripts/export_tradepulse_schema.py --output /tmp/schema.json

# Validate config (requires jsonschema tool)
jsonschema -i config/production.yaml /tmp/schema.json
```

### Generate documentation

```bash
# Export schema with nice formatting
python scripts/export_tradepulse_schema.py --indent 4 > docs/config-reference.json

# Convert to markdown with json-schema-for-humans or similar tool
```

## Requirements

- Python 3.11+
- core.config module (TradePulse configuration system)

## Use Cases

1. **Configuration validation**: Ensure config files match expected schema
2. **Documentation generation**: Auto-generate configuration reference docs
3. **IDE support**: Enable autocomplete and validation in editors
4. **CI/CD validation**: Validate configuration in deployment pipelines
5. **API integration**: Provide schema to external tools and services
