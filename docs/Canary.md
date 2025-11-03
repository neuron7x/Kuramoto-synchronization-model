# Exchange Canary Jobs

- Nightly live read-only checks for Binance, Coinbase (Advanced Trade), Kraken:
  - /time sanity (+/- 5min)
  - symbols or exchangeInfo present
  - Authenticated balance returns structure (no amounts asserted)
- Fail-fast with retries and exponential backoff.
- Public endpoints in unit-tests use VCR cassettes for stability, rotated every 14 days (tools/rotate_cassettes.py).
- Private endpoints are live-only in canaries and never recorded.

Secrets (read-only):
- BINANCE_API_KEY, BINANCE_API_SECRET
- COINBASE_API_KEY, COINBASE_API_SECRET, COINBASE_API_PASSPHRASE (Advanced Trade)
- KRAKEN_API_KEY, KRAKEN_API_SECRET
