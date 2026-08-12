# GeoSync Physics Interface Contracts

Status: INTERFACE_CONTRACT_DRAFT
Scope: canonical GeoSync weighted Kuramoto lane.

## Contract: GeoSync Kuramoto output

| field | type | shape | units | valid range | failure mode |
|---|---|---|---|---|---|
| `theta` | float array | `(T,N)` | radians | finite | NaN/Inf or wrong rank |
| `R` | float array | `(T,)` | dimensionless | `[0,1]` | outside unit interval |
| `Phi` | float | scalar | 1/time | finite | inconsistent with `K_c` |
| `K_c` | float | scalar | 1/time | positive or infinity | finite for zero graph |
| `lambda_max_A` | float | scalar | dimensionless | `>=0` | negative spectral radius |

## Contract: accepted adjacency input

| field | type | shape | units | valid range | failure mode |
|---|---|---|---|---|---|
| `A` | float array | `(N,N)` | dimensionless canonical weight | symmetric, zero diagonal, `A_ij >= 0` | signed adjacency enters boundary or RHS |

## Contract: adapter boundary

Any market-data, Ricci, BN-Syn, MFN+, or report layer consuming GeoSync physics output must declare:

```text
sampling_dt
shape
units
valid_range
conversion_fn
failure_mode
```

## Stop rule

No downstream subsystem may consume `theta`, `R`, `Phi`, or `K_c` without a contract test.
