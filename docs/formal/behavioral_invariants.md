# Behavioral Invariants Registry (Depth-First v1)

## Kernel Invariants
- **INV-KER-001**: For OFI unity output `u_t`, `0 <= u_t <= 1`.
- **INV-KER-002**: Output index is monotonic increasing.
- **INV-KER-003**: No NaN allowed in kernel output.

## Validation Invariants
- **INV-VAL-001**: Spearman IC is bounded in `[-1, 1]`.
- **INV-VAL-002**: Permutation p-value is bounded in `[0, 1]`.
- **INV-VAL-003**: Gate verdict is deterministic for fixed seed.

## Hash Invariants
- **INV-HAH-001**: `sha256(json.dumps(payload, sort_keys=True))` is deterministic.
- **INV-HAH-002**: Identical payloads produce identical hashes across runs.

## Parquet Invariants
- **INV-PQ-001**: Missing backend must fail with explicit diagnostic.
- **INV-PQ-002**: Missing file must fail with explicit diagnostic.

## Contract Invariants
- **INV-ZT-001**: Every harness call validates preconditions before execution.
- **INV-ZT-002**: Every harness call validates postconditions after execution.
- **INV-ZT-003**: Every harness call appends immutable audit entry.

## Compliance Invariants
- **INV-CMP-001**: Deployment is denied if any deterministic check fails.
- **INV-CMP-002**: Compliance certificate includes timestamp and pass counts.

## Truth Invariants
- **INV-TRU-001**: Proof certificate counts proved and verified theorems.
- **INV-TRU-002**: Truth oracle verdict is reproducible from purity audit outputs.
