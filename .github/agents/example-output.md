# Example Output from DOC PR COPILOT v2

This document shows example outputs from the DOC PR COPILOT v2 agent for different types of PR changes.

## Example 1: New API Endpoint

**PR Changes:**
- Added new REST endpoint `/api/v1/strategies`
- Implemented GET and POST methods
- Added authentication middleware

**Agent Output:**

```
DOC_SUMMARY:
- [ADD] docs/api/strategies.md [New API endpoint documentation for strategy management]
- [UPDATE] README.md [Add strategies endpoint to API overview section]
- [UPDATE] CHANGELOG.md [Document new feature in unreleased section]

DOC_PATCHES:

- FILE: docs/api/strategies.md
  ACTION: ADD_FILE_OR_SECTION
  SECTION: "Strategy Management API"
  CONTENT: |
    # Strategy Management API
    
    ## GET /api/v1/strategies
    
    Retrieve list of available trading strategies.
    
    **Authentication:** Required
    
    **Response:**
    ```json
    {
      "strategies": [
        {
          "id": "string",
          "name": "string",
          "description": "string"
        }
      ]
    }
    ```
    
    ## POST /api/v1/strategies
    
    Create a new trading strategy.
    
    **Authentication:** Required
    
    **Request Body:**
    ```json
    {
      "name": "string",
      "config": {}
    }
    ```

- FILE: README.md
  ACTION: UPDATE_SECTION
  SECTION: "API Endpoints"
  BEFORE: |
    - `/api/v1/markets` - Market data access
    - `/api/v1/orders` - Order management
  AFTER: |
    - `/api/v1/markets` - Market data access
    - `/api/v1/orders` - Order management
    - `/api/v1/strategies` - Strategy management

- FILE: CHANGELOG.md
  ACTION: APPEND_ENTRY
  CONTENT: |
    - [Unreleased] Added strategy management API endpoints (GET, POST /api/v1/strategies)

REVIEW_NOTES:
- [FILE docs/api/strategies.md] [VERIFY_BEHAVIOR] Confirm error response codes and formats
- [FILE docs/api/strategies.md] [CHECK_TERMS] Verify "strategy" terminology is consistent with existing docs
```

## Example 2: Breaking Change

**PR Changes:**
- Changed configuration file format from JSON to YAML
- Updated config parser
- Added migration script

**Agent Output:**

```
DOC_SUMMARY:
- [UPDATE] README.md [Document breaking change in configuration format]
- [UPDATE] docs/configuration.md [Update configuration examples and format specification]
- [ADD] docs/migration/v2-config.md [Add migration guide for configuration format change]
- [UPDATE] CHANGELOG.md [Document breaking change with migration instructions]

DOC_PATCHES:

- FILE: README.md
  ACTION: UPDATE_SECTION
  SECTION: "Configuration"
  BEFORE: |
    Configuration is managed through `config.json`:
    ```json
    {
      "exchange": "binance",
      "api_key": "your-key"
    }
    ```
  AFTER: |
    ⚠️ **BREAKING CHANGE (v2.0):** Configuration format changed from JSON to YAML.
    
    Configuration is managed through `config.yaml`:
    ```yaml
    exchange: binance
    api_key: your-key
    ```
    
    See [migration guide](docs/migration/v2-config.md) for upgrading.

- FILE: docs/configuration.md
  ACTION: UPDATE_SECTION
  SECTION: "Configuration File Format"
  AFTER: |
    # Configuration File Format
    
    TradePulse uses YAML for configuration (changed from JSON in v2.0).
    
    ## File Location
    
    Default: `config.yaml` in project root.
    
    ## Structure
    
    ```yaml
    exchange: binance
    api_key: ${API_KEY}
    timeframes:
      - 1m
      - 5m
    ```
    
    Environment variables can be referenced using `${VAR_NAME}` syntax.

- FILE: docs/migration/v2-config.md
  ACTION: ADD_FILE_OR_SECTION
  SECTION: "Migration Guide: v1 to v2 Configuration"
  CONTENT: |
    # Migration Guide: v1 to v2 Configuration
    
    ## Overview
    
    Version 2.0 changes configuration format from JSON to YAML.
    
    ## Automatic Migration
    
    Run the migration script:
    ```bash
    python scripts/migrate_config.py config.json
    ```
    
    This creates `config.yaml` from your existing `config.json`.
    
    ## Manual Migration
    
    Convert JSON keys to YAML format:
    
    **Before (v1):**
    ```json
    {
      "exchange": "binance",
      "api_key": "key"
    }
    ```
    
    **After (v2):**
    ```yaml
    exchange: binance
    api_key: key
    ```
    
    ## Validation
    
    Validate new configuration:
    ```bash
    tradepulse config validate
    ```

- FILE: CHANGELOG.md
  ACTION: APPEND_ENTRY
  CONTENT: |
    - [v2.0.0] BREAKING: Configuration format changed from JSON to YAML. Use migration script: `python scripts/migrate_config.py config.json`

REVIEW_NOTES:
- [FILE docs/migration/v2-config.md] [MISSING_CONTEXT] Verify migration script path and command-line interface
```

## Example 3: Bug Fix (No Doc Changes)

**PR Changes:**
- Fixed null pointer exception in data parser
- Added error handling
- No changes to public API or behavior

**Agent Output:**

```
DOC_SUMMARY:
- [NO_CHANGE] No documentation updates required [Internal bug fix with no user-visible changes]

DOC_PATCHES:

REVIEW_NOTES:
```

## Example 4: New CLI Command

**PR Changes:**
- Added `tradepulse validate` command
- Validates configuration and dependencies
- Exits with status code 0 on success

**Agent Output:**

```
DOC_SUMMARY:
- [UPDATE] README.md [Add validate command to CLI reference]
- [UPDATE] docs/cli.md [Document new validate command with usage examples]
- [UPDATE] CHANGELOG.md [Add validate command to feature list]

DOC_PATCHES:

- FILE: README.md
  ACTION: UPDATE_SECTION
  SECTION: "Command Line Interface"
  BEFORE: |
    ```bash
    tradepulse run      # Start trading
    tradepulse backtest # Run backtest
    ```
  AFTER: |
    ```bash
    tradepulse run      # Start trading
    tradepulse backtest # Run backtest
    tradepulse validate # Validate configuration
    ```

- FILE: docs/cli.md
  ACTION: UPDATE_SECTION
  SECTION: "Commands"
  AFTER: |
    ## validate
    
    Validate configuration and check dependencies.
    
    **Usage:**
    ```bash
    tradepulse validate [OPTIONS]
    ```
    
    **Options:**
    - `--config PATH` - Path to configuration file (default: config.yaml)
    - `--strict` - Enable strict validation with warnings as errors
    
    **Exit Codes:**
    - `0` - Validation successful
    - `1` - Validation failed
    
    **Example:**
    ```bash
    tradepulse validate --config prod-config.yaml --strict
    ```

- FILE: CHANGELOG.md
  ACTION: APPEND_ENTRY
  CONTENT: |
    - [Unreleased] Added `validate` CLI command for configuration and dependency validation

REVIEW_NOTES:
```

## Output Format Notes

### DOC_SUMMARY
- Must be concise (1-2 sentences per item)
- TYPE must be one of: UPDATE, ADD, REMOVE, NO_CHANGE, REVIEW_NEEDED
- File paths relative to repository root

### DOC_PATCHES
- FILE: Path relative to repository root
- ACTION: One of UPDATE_SECTION, ADD_FILE_OR_SECTION, APPEND_ENTRY
- SECTION: Clear identifier for location in file
- BEFORE: Optional, exact match required
- AFTER/CONTENT: Complete, ready-to-apply text

### REVIEW_NOTES
- File path in brackets
- SHORT_ID for categorization
- Brief description of what needs verification
- Only include when human review is needed
