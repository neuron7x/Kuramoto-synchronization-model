# GitHub Actions Local Testing with `act`

This directory contains example configuration files for testing GitHub Actions workflows locally using [nektos/act](https://github.com/nektos/act).

## Setup

1. Install `act`: Follow instructions at https://github.com/nektos/act

2. Copy example files to create your local configuration:
   ```bash
   cp tests.secrets.example tests.secrets
   cp tests.env.example tests.env
   ```

3. Edit `tests.secrets` and `tests.env` with your local values (these files are gitignored)

## Configuration Files

- **tests.secrets.example**: Template for GitHub secrets used in workflows
- **tests.env.example**: Template for environment variables used in workflows

## Usage

Run workflows locally:
```bash
# Run a specific workflow
act -W .github/workflows/tests.yml

# Run with custom secrets and env files
act -W .github/workflows/tests.yml --secret-file .github/act/tests.secrets --env-file .github/act/tests.env
```

## Security

**NEVER commit real secrets to these files!** The `.example` files should only contain:
- Placeholder values
- Example formats
- Non-sensitive defaults

Real secrets and sensitive data should only exist in your local copies (which are gitignored).
