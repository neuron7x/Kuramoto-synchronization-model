# GeoSync Units Table

Status: DIMENSIONAL_CONTRACT_DRAFT
Scope: canonical GeoSync weighted Kuramoto core.

## Base convention

The canonical model treats phase as radians and time as arbitrary simulation time units unless a market-data adapter explicitly declares physical sampling time.

Radians are dimensionless in SI algebra, but this contract keeps `rad` labels for traceability.

## Dimensional table

| symbol | meaning | dimension | implementation carrier | guard |
|---|---|---|---|---|
| `theta_i` | phase | rad | `theta` | finite real |
| `dt` | time step / simulation increment | time | `dt` | positive finite when used by an integrator |
| `d theta_i / dt` | phase velocity | rad / time | RHS output | finite real |
| `omega_i` | intrinsic angular frequency | rad / time | `omega` | finite real |
| `A_ij` | graph edge weight | dimensionless in canonical lane | `A` | non-negative, symmetric, zero diagonal |
| `K` | coupling strength | 1 / time | `K` or absorbed into scaled `A` in trajectory tests | finite, non-negative |
| `gamma` | Lorentzian half-width | rad / time | `lorentzian_half_width` | positive finite |
| `lambda_max(A)` | spectral radius | dimensionless | eigvalsh of `A` | non-negative |
| `Phi` | onset scalar | rad / time | `K*lambda_max(A)-2*gamma` | finite |
| `K_c` | critical coupling | 1 / time | `2*gamma/lambda_max(A)` | positive or infinity |
| `R` | order parameter | dimensionless | `order_parameter(theta)` | `[0,1]` |
| `V` | coupling potential | edge-weight units | `coupling_potential(theta,A)` | non-negative when `A>=0` |

## Homogeneity checks

Equation:

```text
d theta_i / dt = omega_i + K * sum_j A_ij * sin(theta_j - theta_i)
```

Dimensional expansion:

```text
[d theta_i / dt] = rad / time
[omega_i] = rad / time
[K] = 1 / time
[A_ij] = 1
[sin(theta_j - theta_i)] = 1
[K * sum_j A_ij * sin(...)] = 1 / time
```

Because radians are dimensionless in SI but tracked semantically, RHS terms are compatible as angular-rate terms.

Boundary:

```text
Phi = K * lambda_max(A) - 2 * gamma
```

Dimensional expansion:

```text
[K * lambda_max(A)] = 1 / time
[gamma] = 1 / time
[Phi] = 1 / time
```

Critical coupling:

```text
K_c = 2 * gamma / lambda_max(A)
```

Dimensional expansion:

```text
[gamma / lambda_max(A)] = 1 / time
[K_c] = 1 / time
```

## Failure conditions

```text
A is treated as dimensional without updating K units
K and gamma are compared with incompatible sampling-time conventions
market-data adapter consumes theta/R without declared sampling_dt
range guard is claimed as dimensional analysis
```
