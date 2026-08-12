# Configuration System

GeoSync uses a unified configuration layer powered by
[`pydantic-settings`](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).
Every service, domain module and CLI tool now reads its settings through the same
`GeoSyncSettings` model which merges values from multiple sources.

## Source precedence

Configuration values are resolved in the following order (highest priority first):

1. **Command line overrides** – values passed to `load_kuramoto_ricci_config(..., cli_overrides=...)`
   or via the new `--config-override` flag in CLI utilities.
2. **Process environment variables** – variables prefixed with `GEOSYNC_`.
3. **`.env` files** – the loader automatically reads a `.env` file from the current
   working directory if present.
4. **YAML files** – the base configuration is read from the file referenced by
   `config_file` (defaults to `configs/kuramoto_ricci_composite.yaml`).

Missing sources are skipped gracefully, so removing a `.env` file or YAML preset simply
falls back to default values embedded in the models.

## YAML layout

The YAML structure mirrors the Pydantic models. A minimal example looks like:

```yaml
kuramoto:
  timeframes: ["M1", "M5", "M15", "H1"]
  adaptive_window:
    enabled: true
    base_window: 200
  min_samples_per_scale: 64
ricci:
  temporal:
    window_size: 100
    n_snapshots: 8
    retain_history: true
  graph:
    n_levels: 20
    connection_threshold: 0.1
composite:
  thresholds:
    R_strong_emergent: 0.8
    R_proto_emergent: 0.4
    coherence_min: 0.6
    ricci_negative: -0.3
    temporal_ricci: -0.2
    topological_transition: 0.7
  signals:
    min_confidence: 0.5
```

All values are validated by the Pydantic models; invalid inputs raise a
`ConfigError` with a descriptive message.

## CLI usage

The Kuramoto–Ricci integration script demonstrates CLI overrides:

```bash
python scripts/integrate_kuramoto_ricci.py \
  --data sample.csv \
  --config configs/kuramoto_ricci_composite.yaml \
  --config-override kuramoto.base_window=256 \
  --config-override composite.thresholds.R_strong_emergent=0.9
```

`--config-override` accepts dot-delimited keys and `YAML` expressions for values. Lists
and booleans can be expressed naturally, for example
`--config-override kuramoto.timeframes=['M1','M5','H1']`.

## Environment variables and `.env`

Environment variables use the `GEOSYNC_` prefix and `__` as the nested delimiter:

```bash
export GEOSYNC_KURAMOTO__BASE_WINDOW=300
export GEOSYNC_COMPOSITE__THRESHOLDS__R_STRONG_EMERGENT=0.85
```

The same syntax works inside a `.env` file located in the working directory. When present,
values inside `.env` override the YAML baseline but remain below live environment variables
and CLI overrides.

### Exchange connector credentials

The live trading connectors under `execution.adapters` consume venue credentials from the
process environment (or `.env` files) and keep REST/WebSocket sessions authenticated. Set
the following keys before starting the live execution loop:

| Venue    | Required variables                                                 | Optional variables |
|----------|--------------------------------------------------------------------|--------------------|
| Binance  | `BINANCE_API_KEY`, `BINANCE_API_SECRET`                            | `BINANCE_RECV_WINDOW` |
| Coinbase | `COINBASE_API_KEY`, `COINBASE_API_SECRET`, `COINBASE_API_PASSPHRASE` | – |
| Kraken   | `KRAKEN_API_KEY`, `KRAKEN_API_SECRET`                              | `KRAKEN_OTP` |

Place these variables directly in the environment or commit them to your secret manager
flow (Vault, AWS Secrets Manager, etc.). `BINANCE_RECV_WINDOW` lets operators widen the
server timestamp tolerance when venues are under load. The connectors reuse the
credentials for HMAC signing, automatically rotate listen keys, and reconnect WebSocket
streams after transient failures.

Example `.env` snippet:

```dotenv
BINANCE_API_KEY=live_key_here
BINANCE_API_SECRET=live_secret_here
COINBASE_API_KEY=coinbase_key_here
COINBASE_API_SECRET=coinbase_secret_here
COINBASE_API_PASSPHRASE=optional_passphrase
KRAKEN_API_KEY=kraken_key_here
KRAKEN_API_SECRET=kraken_secret_here
KRAKEN_OTP=optional_totp_here
```

Sample configuration overlays that map symbols, rate limits, and risk tolerances for each
venue are available under `artifacts/configs/`. Copy the relevant template file, adjust the
notional limits, and load it alongside your primary strategy settings.

## Programmatic access

Python modules should use `load_kuramoto_ricci_config` to obtain a fully merged
`KuramotoRicciIntegrationConfig` instance:

```python
from core.config import load_kuramoto_ricci_config

cfg = load_kuramoto_ricci_config("configs/kuramoto_ricci_composite.yaml")
engine_kwargs = cfg.to_engine_kwargs()
```

For scripts that parse their own CLI arguments, convert `key=value` pairs with
`parse_cli_overrides` and forward the mapping to the loader:

```python
from core.config import load_kuramoto_ricci_config, parse_cli_overrides

overrides = parse_cli_overrides(["kuramoto.base_window=512"])
cfg = load_kuramoto_ricci_config("configs/custom.yaml", cli_overrides=overrides)
```

This keeps all configuration handling centralised and ensures new sources or validation
rules are automatically applied across the code base.

## Schema export

Generate a JSON schema describing the full configuration model with the helper script:

```bash
python scripts/export_geosync_schema.py --output schemas/geosync-settings.schema.json
```

Omitting `--output` prints the schema to standard output, which makes it easy to pipe
into tooling or inspect the structure inline. The schema is derived directly from
`GeoSyncSettings` so it always reflects the latest validation rules enforced at
startup.
