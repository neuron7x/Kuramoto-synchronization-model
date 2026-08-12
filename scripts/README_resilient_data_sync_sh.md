# resilient_data_sync.sh

Bash script for resilient data synchronization with comprehensive error handling.

## Description

This Bash script applies the following defensive scripting practices for reliable data synchronization:

- **Idempotency**: Uses lock files, content hashing, and execution markers
- **Structured logging**: JSON-formatted logs to stdout/stderr
- **Retry logic**: Exponential backoff with jitter for network operations
- **Timeouts**: Request-level timeouts and circuit breaker for remote resources
- **Environment validation**: Checks for required tools and their versions
- **Safe cleanup**: Proper trap handling for temporary files

## Usage

### Basic sync (default: sample.csv)

```bash
scripts/resilient_data_sync.sh
```

### Sync from URL

```bash
scripts/resilient_data_sync.sh \
  --source-url https://example.com/data.csv \
  --destination data/downloaded.csv
```

### Custom lock directory

```bash
scripts/resilient_data_sync.sh \
  --source-url https://example.com/data.csv \
  --destination data/output.csv \
  --lock-dir /var/lock/geosync
```

### Configure retries and timeouts

```bash
scripts/resilient_data_sync.sh \
  --source-url https://slow-server.com/data.csv \
  --max-retries 10 \
  --timeout 60 \
  --circuit-ttl 600
```

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--source-url` | `file://${REPO_ROOT}/sample.csv` | Source URL or file path |
| `--destination` | `${REPO_ROOT}/reports/resilient-sync/sample.csv` | Destination file path |
| `--lock-dir` | `${REPO_ROOT}/reports/resilient-sync/.locks` | Directory for lock files |
| `--max-retries` | `5` | Maximum retry attempts |
| `--timeout` | `30` | Request timeout in seconds |
| `--circuit-ttl` | `300` | Circuit breaker timeout in seconds |
| `--help`, `-h` | | Show help message |

## Features

### Idempotency

The script uses SHA-256 checksums to detect unchanged files and skip redundant downloads:

```bash
# First run: downloads file
scripts/resilient_data_sync.sh --source-url https://example.com/data.csv

# Second run: skips download (file unchanged)
scripts/resilient_data_sync.sh --source-url https://example.com/data.csv
```

### Lock Files

Prevents concurrent execution on the same source/destination pair:

```bash
# Terminal 1
scripts/resilient_data_sync.sh --source-url https://example.com/large.csv &

# Terminal 2 (will skip with warning)
scripts/resilient_data_sync.sh --source-url https://example.com/large.csv
```

### Circuit Breaker

Prevents repeated failures from overwhelming remote servers:

```bash
# First failure: opens circuit for 5 minutes
scripts/resilient_data_sync.sh --source-url https://broken.com/data.csv

# Subsequent attempts: blocked until TTL expires
scripts/resilient_data_sync.sh --source-url https://broken.com/data.csv
# Output: "circuit breaker open, seconds_until_retry=..."
```

### Structured Logging

All logs are JSON-formatted for easy parsing:

```json
{
  "ts": "2025-10-14T06:00:00.000000Z",
  "level": "info",
  "message": "download successful",
  "script": "resilient_data_sync.sh",
  "run_id": "abc123...",
  "pid": 12345,
  "version": "1.0.0",
  "attempt": "2"
}
```

### Retry with Exponential Backoff

Network operations automatically retry with increasing delays:

```
Attempt 1: immediate
Attempt 2: ~1s delay
Attempt 3: ~2s delay
Attempt 4: ~4s delay
Attempt 5: ~8s delay
```

Jitter is added to prevent thundering herd problems.

## Exit Codes

- `0`: Success (file synced or already up-to-date)
- `42`: Missing required command
- `64`: Invalid arguments
- `70`: Download failed after retries
- `75`: Circuit breaker open

## Environment

### Required Tools

The script validates these dependencies on startup:

- `curl`: HTTP downloads
- `python3`: Logging helper
- `sha256sum`: Checksum computation
- `mktemp`: Temporary file creation
- `flock`: File locking
- `timeout`: Command timeouts

### Variables

| Variable | Description |
|----------|-------------|
| `SCRIPT_NAME` | Script filename |
| `REPO_ROOT` | Repository root directory |
| `RUN_ID` | Unique run identifier (UUID) |
| `SCRIPT_VERSION` | Script version number |

## Examples

### Sync from local file

```bash
scripts/resilient_data_sync.sh \
  --source-url file:///data/source.csv \
  --destination /data/backup.csv
```

### Sync with long timeout

```bash
scripts/resilient_data_sync.sh \
  --source-url https://slow-api.com/export.csv \
  --timeout 120 \
  --max-retries 3
```

### Integration with CI/CD

```bash
#!/bin/bash
set -euo pipefail

# Download test data
scripts/resilient_data_sync.sh \
  --source-url https://cdn.example.com/test-data.csv \
  --destination tests/fixtures/data.csv

# Run tests
pytest tests/
```

### Monitor with jq

```bash
scripts/resilient_data_sync.sh --source-url https://example.com/data.csv 2>&1 | \
  jq -r 'select(.level == "error") | .message'
```

## Error Handling

### Network Failures

```bash
# Automatic retry with backoff
scripts/resilient_data_sync.sh --source-url https://unreliable.com/data.csv
# Output: Multiple "download failed" warnings, then success or circuit break
```

### Disk Space

```bash
# Check available space before sync
df -h "${destination_dir}"
scripts/resilient_data_sync.sh --destination /path/with/space/output.csv
```

### Corrupted Downloads

Checksums are verified automatically. The script only updates the destination if:
1. Download succeeds
2. File is readable
3. Checksum differs from existing file

## Best Practices

1. **Use absolute paths**: Avoid relative paths for production
2. **Monitor logs**: Parse JSON output for alerts
3. **Set realistic timeouts**: Match server response times
4. **Configure circuit breaker**: Prevent cascade failures
5. **Validate checksums**: Use `--checksum` for critical data

## Comparison with Python Version

| Feature | Bash | Python |
|---------|------|--------|
| Dependencies | curl, flock | httpx, tenacity |
| Parallel downloads | No | Yes (--max-workers) |
| Checksum verification | SHA-256 | SHA-256 |
| Pattern expansion | No | Yes (--pattern) |
| JSON output | Logs only | Results + logs |
| Platform support | Unix-like | Cross-platform |

Use Bash for:
- Simple single-file syncs
- Systems without Python
- Shell script integration

Use Python for:
- Batch operations
- Parallel downloads
- Windows support
- Advanced checksum validation

## Requirements

- Bash 4.0+
- curl
- Python 3.6+ (for logging helper)
- Standard Unix tools (sha256sum, mktemp, flock, timeout)

## License

MIT (see repository LICENSE file)
