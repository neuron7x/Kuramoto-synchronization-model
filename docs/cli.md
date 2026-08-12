# GeoSync CLI Reference

The GeoSync CLI orchestrates ingestion, backtesting, optimisation, execution,
and reporting pipelines. This reference covers the developer-experience
improvements added for deterministic runs and improved shell ergonomics.

For a command-by-command breakdown generated directly from `geosync-cli --help`,
see the auto-generated [GeoSync CLI Command Reference](geosync_cli_reference.md).

## Global Improvements

- **Typed exit codes** – configuration errors exit with code `2`, artifact
  issues with `3`, computation failures with `4`. CI jobs can branch on the
  category without parsing logs.
- **Step logs** – every command emits `▶`/`✓`/`✖` markers with durations so
  engineers can trace long-running jobs quickly.
- **Idempotent artifacts** – when an output file is unchanged, the CLI reports
  `unchanged` and skips rewrites while still logging the SHA256 digest.
- **Artifact hashes** – all persisted files include their digest in the CLI
  output. Capture these hashes in notebooks or experiment trackers for full
  lineage.

## Shell Completion

Generate shell completion snippets using the dedicated command:

```bash
geosync-cli completion bash   # bash, zsh, or fish
```

Add the emitted line to your shell profile. Example (`~/.bashrc`):

```bash
eval "$(_GEOSYNC_CLI_COMPLETE=bash_source geosync-cli)"
```

## Output Rendering Options

Commands that produce analytics (`backtest`, `optimize`, `exec`, `report`) now
support `--output` (alias `--output-format`) with the following values:

- `table` – renders a Markdown-friendly table to stdout.
- `jsonl` – prints line-delimited JSON objects for piping into `jq`, Logstash, or
  notebook tooling.
- `parquet` – writes a columnar companion artifact alongside the configured
  results path (e.g., `backtest.parquet`).

Example:

```bash
geosync-cli backtest --config configs/runbook/backtest.yaml --output jsonl | jq '.'
```

## Template Generation

Template generation now uses `--template-output` to avoid collisions with the
new output rendering flag:

```bash
geosync-cli backtest --generate-config --template-output configs/runbook/backtest.yaml
```

## Integration with `jq`

Pair JSONL output with `jq` to build quick sanity checks or dashboards:

```bash
geosync-cli exec --config configs/runbook/exec.yaml --output jsonl \
  | jq 'select(.metric == "latest_signal")'
```

For multi-line reports, use `--output jsonl` on the `report` command to emit
section metadata that feeds nightly regression dashboards.

## Companion Parquet Artifacts

When `--output parquet` is provided the CLI writes an additional Parquet file
next to the configured results path. Use this for faster notebook iteration or
for feeding delta ingestion jobs.

## Troubleshooting Exit Codes

| Exit Code | Category              | Typical Cause                      |
| --------- | --------------------- | ---------------------------------- |
| 1         | Unknown               | Unexpected runtime error           |
| 2         | Configuration error   | Missing config field, invalid enum |
| 3         | Artifact error        | Missing dataset, permission issue  |
| 4         | Compute error         | Strategy bug, divergence           |

Wrap CLI invocations with shell logic to branch based on severity:

```bash
if ! geosync-cli backtest --config configs/runbook/backtest.yaml; then
  case $? in
    2) echo "config error" ;;
    3) echo "data missing" ;;
    4) echo "strategy failure" ;;
    *) echo "unexpected failure" ;;
  esac
fi
```

Use these capabilities to embed the CLI into research automation, nightly
quality gates, and on-demand investigations without sacrificing reproducibility.
