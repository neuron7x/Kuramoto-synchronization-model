## Exchange connector environment contract

Each authenticated connector reads credentials from environment variables (or an injected vault resolver) using a fixed prefix.

### Binance
- `BINANCE_API_KEY`
- `BINANCE_API_SECRET`

### Coinbase Advanced Trade
- `COINBASE_API_KEY`
- `COINBASE_API_SECRET`
- `COINBASE_API_PASSPHRASE`

If any required variable is missing, the connector raises `CredentialError` during `connect()` to fail fast with an actionable message. Optional secrets (for future extensions) must use the same prefix.
