# Backtest-to-Live Cookbook

This cookbook walks a new quant or engineer from an empty workspace to a
reproducible backtest and live execution run. Every stage includes concrete
configuration snippets, seed datasets, and operator checklists so the workflow
remains deterministic end-to-end.

## 1. Bootstrap the Workspace

1. **Clone the repository and install dependencies**
   ```bash
   git clone https://github.com/neuron7xLab/GeoSync.git
   cd GeoSync
   pip install -c constraints/security.txt -r requirements.txt
   ```
2. **Materialise starter seeds** using the provided fixtures:
   ```bash
   make seed-data # populates data/seeds/prices.csv and configs/seeds/*.yaml
   ```
3. **Verify tooling versions** (pin exact versions for deterministic runs):
   ```bash
   python --version   # >=3.10
   geosync-cli --version
   jq --version       # optional but recommended for JSONL post-processing
   ```

> ℹ️  Commit the outputs of `make seed-data` to an internal artifact registry so
> onboarding engineers can start from the same deterministic snapshot.

## 2. Prepare Configuration Templates

Use the CLI template renderer to scaffold canonical configs. Templates are
rendered once then tracked in Git.

```bash
geosync-cli ingest --generate-config --template-output configs/runbook/ingest.yaml
geosync-cli backtest --generate-config --template-output configs/runbook/backtest.yaml
geosync-cli exec --generate-config --template-output configs/runbook/exec.yaml
```

Update the generated YAML files with project specific values. Recommended
minimum fields are listed below.

### Ingest Template Essentials

```yaml
name: eurusd-minutes
source:
  kind: csv
  path: data/seeds/eurusd.csv
  timestamp_field: timestamp
  value_field: close
catalog:
  path: artifacts/catalog.json
versioning:
  backend: dvc
  repo_path: artifacts/versioning
metadata:
  seed_run: true
  owner: research-dx
```

### Backtest Template Essentials

```yaml
name: eurusd-signal-v1
results_path: reports/backtests/eurusd_v1.json
strategy:
  entrypoint: strategies.mean_reversion:run
  parameters:
    lookback: 20
    threshold: 1.5
execution:
  starting_cash: 100000
  slippage_bps: 2
metadata:
  risk_profile: sandbox
```

### Exec Template Essentials

```yaml
name: eurusd-live
results_path: reports/live/eurusd_signal.json
routing:
  venue: oanda-demo
  account: research-play
metadata:
  canary: true
```

## 3. Deterministic Ingestion Checklist

- [ ] Confirm seed CSV/Parquet files exist under `data/seeds`.
- [ ] Update ingest template path fields to point at the seed dataset.
- [ ] Run ingestion and capture the emitted SHA256 checksum.
- [ ] Register the artifact ID in the feature catalog for traceability.

```bash
geosync-cli ingest --config configs/runbook/ingest.yaml
```

Use the CLI step logs to confirm idempotency; repeated runs should report the
artifact as unchanged once committed.

## 4. Backtest Execution Checklist

- [ ] Embed the ingest lineage path inside `backtest.yaml`.
- [ ] Validate the strategy entrypoint is importable locally.
- [ ] Execute the backtest with JSONL output for quick sanity checks:
  ```bash
  geosync-cli backtest \
    --config configs/runbook/backtest.yaml \
    --output jsonl | jq '."metric"? // .' # sample jq integration
  ```
- [ ] Persist generated signals/returns to Parquet if downstream notebooks need
      columnar access:
  ```bash
  geosync-cli backtest --config configs/runbook/backtest.yaml --output parquet
  ```
- [ ] Capture the CLI-emitted SHA256 digest and add it to the experiment log.

## 5. Promotion Gate: Pre-Live Checklist

Before promoting the strategy to canary live execution:

- [ ] Backtest error budget: drawdown, Sharpe, and hit-rate metrics within
      approved tolerances.
- [ ] Feature catalog entry exists with checksum matching the latest backtest
      artifact.
- [ ] Risk sign-off recorded (attach Jira ticket ID in config `metadata`).
- [ ] Nightly regression for the strategy is green (link to quality gates).

## 6. Live Execution Dry Run

1. Copy the validated backtest parameters into the exec config.
2. Switch the data source to a paper-trading feed or delayed mirror.
3. Run a dry execution to ensure idempotency and logging:
   ```bash
   geosync-cli exec --config configs/runbook/exec.yaml --output table
   ```
4. Confirm the latest signal is registered in the catalog and the emitted hash
   matches prior dry runs.
5. Share the JSON result via `--output jsonl` when piping into monitoring
   dashboards that rely on `jq` or Logstash.

## 7. Go-Live Checklist

- [ ] Canary deployment approved and scheduled in deployment calendar.
- [ ] On-call rotation notified; incident playbook linked in the ticket.
- [ ] ISR dashboard thresholds configured (see UI performance playbook).
- [ ] Feature store snapshot locked to the ingestion checksum.
- [ ] Rollback plan documented with exit criteria.

Once checks are complete, promote the strategy using the platform’s deployment
automation. Archive configs, CLI outputs, and generated hashes together to
ensure the entire runbook remains reproducible.

---

Following this cookbook guarantees that onboarding engineers can reproduce
published results, trace artifacts via checksums, and escalate confidently when
moving from research backtests into controlled live trading.
