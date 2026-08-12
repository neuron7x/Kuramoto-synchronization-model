# Substrate Oracle Specification

`agent/substrate_oracle.py` classifies input substrate and emits deterministic `action_intent.json`.

## Rules
- If NaN exists: `ABORT`.
- If stale feed (`>30` min): `BLOCK`.
- If schema unknown: `QUARANTINE`.
- If OHLC-only: `DORMANT` and block precursor claims.
- If bid/ask, depth, or OFI present: `GO`.

## Exit Codes
- `0` healthy transition (`GO` or non-fatal block)
- `1` fatal invariant violation (`NAN_ABORT`)
- `2` dead substrate (`OHLC_ONLY` or schema drift)

## Artifacts
- `action_intent.json`
- `action_intent.sha256`

## Related Formal Docs
- `docs/architecture/substrate_signal_governance.md`
- `docs/research/sentiment_ricci_interpretation.md`
