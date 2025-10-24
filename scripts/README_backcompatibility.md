# Backwards Compatibility Guardrail

`backcompatibility.py` provides a reproducible workflow for verifying that API
responses remain stable across releases. The script replays historical traffic,
compares responses against curated baselines with configurable tolerances, and
emits actionable artefacts (counterexamples, reports, alerts, and stability
metrics) to block regressions before they reach production.

## Usage

1. Create a configuration file (`.json` or `.yaml`) that describes the datasets
   to replay, tolerance thresholds, whitelist rules, and report locations.

   ```json
   {
     "report_dir": "reports/backcompat",
     "blocking_threshold": 0.0,
     "alerts": {
       "channels": ["stdout", "file"],
       "recipients": ["oncall@tradepulse.example"],
       "escalation_after_failures": 1
     },
     "datasets": [
       {
         "name": "core-api",
         "traffic": "data/core_traffic.jsonl",
         "baseline": "data/core_baseline.json",
         "actual": "artifacts/core_candidate.json",
         "tolerance": {
           "absolute": 0.01,
           "relative": 0.001,
           "overrides": {
             "$.orders[*].price": {"absolute": 0.05}
           }
         },
         "whitelist": ["$.metadata.*"],
         "counterexamples": "reports/counterexamples/core.jsonl",
         "contract_snapshot": "reports/contracts/core.json"
       }
     ],
     "stability_history": "reports/stability.json",
     "auto_update_baseline": false
   }
   ```

2. Execute the runner:

   ```bash
   python -m scripts.backcompatibility --config backcompat.json --verbose
   ```

   Optional overrides:

   - `--report-dir` – redirect artefacts to a temporary directory
   - `--http-base-url` / `--http-timeout` – replay traffic against a live
     service instead of loading canned candidate responses
   - `--update-baseline` – force automatic baselining when no regressions are
     detected
   - `--release-channel` – label reports and govern auto-baseline policies

## Outputs

- **Markdown report** with dataset summaries, blocking differences, and metrics
- **Counterexample log** (`*.jsonl`) containing structured repro steps
- **Contract snapshot** (`*.json`) capturing the current response surface
- **Stability history** (`stability.json`) for dashboard integrations
- **Alerts** via stdout or JSON file suitable for paging workflows

The script exits with code `1` whenever the ratio of blocking deviations exceeds
the configured threshold, enabling CI to block releases.

## Testing

Run the dedicated tests:

```bash
python -m pytest scripts/tests/test_backcompatibility.py -v
```

## Data Format

- **Traffic**: Newline-delimited JSON objects with `id`, `method`, `path`, and
  optional `query`, `headers`, and `body` fields.
- **Baseline / Candidate**: JSON mapping of `record_id` to arbitrary response
  payloads (e.g., decoded JSON, composite objects, or structured fixtures).

Counterexample files and contract snapshots are automatically created by the
runner. Provide empty placeholder files only when required for access control
rules in CI/CD systems.

