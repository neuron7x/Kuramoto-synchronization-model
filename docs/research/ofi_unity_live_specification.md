# OFI Unity Live Specification (Task 2)

`research/kernels/ofi_unity_live.py` executes OFI unity validation on a provided source snapshot.

## Inputs
- `--source`: `dukascopy|oanda|databento`
- `--input-csv`: CSV containing bid/ask columns
- `--output`: verdict JSON path

## Outputs
- JSON verdict with three-D gates (`DETECT`, `DISCRIMINATE`, `DELIVER`)
- Deterministic `replay_hash`

## Policy
- Missing data/dependencies => `FINAL=REJECT`
- No fabricated `SIGNAL_READY`
- `seed=42`, permutations=500
