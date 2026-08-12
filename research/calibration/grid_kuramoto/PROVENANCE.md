# PROVENANCE — CALIB-GRID-001 embedded grid data

All numbers in `grid_data.py` are transcribed verbatim from the cited
peer-reviewed / textbook sources. **No** runtime dependency on
`pandapower` / `pypower` is introduced; the canonical data is small,
fully reproducible, and sha-pinnable.

## Reduction formulae (with equation references)

| Quantity | Formula | Reference |
|---|---|---|
| True coupling | `K_ij = |V_i| |V_j| B_ij` | Dörfler & Bullo, PNAS 2013 110(6):2005, Eq. (2) — lossless network-reduced swing model |
| True nat. freq. | `ω_i = P_i / d_i`, mean-centred | Dörfler & Bullo, PNAS 2013, Supporting Information Eq. (S15) |
| Sync condition | `‖B†ω‖_{E,∞} ≤ sin γ*`, `γ*≤π/2` | Dörfler & Bullo, PNAS 2013, Eq. (3) — exact/tight bound on the network-reduced model |
| Crit. coupling scale | `s_crit = ‖B₁†ω‖_{E,∞}` | derived from Eq. (3): uniform scale `K↦sK` ⇒ LHS scales `1/s` |
| Swing → Kuramoto | `m_i θ̈_i + d_i θ̇_i = ω_i − Σ_j K_ij sin(θ_i−θ_j)` | Dörfler & Bullo, PNAS 2013, § II; classical swing equation |

## § WSCC-9 — primary fixture (`wscc_9_bus`)

| Field | Value | Source (page / table) |
|---|---|---|
| System | WSCC 3-machine, 9-bus | P. M. Anderson & A. A. Fouad, *Power System Control and Stability*, 2nd ed., IEEE Press/Wiley 2003, Example 2.6 |
| Reduced internal-node `B` (3×3) | imag part of Kron-reduced `Y_bus` | Anderson & Fouad, Ex. 2.6 / Fig. 2.18 reduced network |
| Internal voltage `|V|` | `[1.0566, 1.0502, 1.0170]` p.u. | Anderson & Fouad, Ex. 2.6 |
| Mechanical power `P` | `[0.716, 1.630, 0.850]` p.u. (100 MVA base) | Anderson & Fouad, Table 2.1 dispatch |
| Inertia `H` (s) | `[23.64, 6.40, 3.01]`; `m = 2H/ω_s`, `ω_s = 2π·60` | Anderson & Fouad, Table 2.1 |
| Damping `d` | uniform `2.0` p.u. | Dörfler & Bullo, PNAS 2013, Fig. 1 caption |

Identical machine/network data is used by Dörfler & Bullo (PNAS 2013,
Fig. 1) and Sauer & Pai, *Power System Dynamics and Stability*,
Prentice Hall 1998.

## § IEEE-39 — secondary fixture (`ieee_39_new_england`)

| Field | Value | Source |
|---|---|---|
| System | IEEE 39-bus "New England", 10-machine | T. Athay, R. Podmore, S. Virmani, *A practical method for the direct analysis of transient stability*, IEEE Trans. PAS-98(2):573–584, 1979 |
| Inertia `H` (s) | gens 30–39, 100 MVA base | M. A. Pai, *Energy Function Analysis for Power System Stability*, Kluwer 1989, Appendix D |
| Damping `d` | uniform `1.0` p.u. | convention (Pai 1989, App. D) |
| Reduced `B` (10×10) | Kron elimination of the 29 load buses of the Athay 1979 lossless branch reactances | derived; symmetric, zero diagonal |

The IEEE-39 reduced susceptance is a Kron-eliminated approximation of
the Athay 1979 lossless network rounded to 2 dp; it is exercised only
under `@slow` and is **not** part of the pre-registered WSCC-9 verdict.
It exists to show the calibration loop scales to a larger canonical
system, not to add a second pre-registered claim.

## Data lineage sha

`grid_data.py` is the sha-pinned data artifact. Any edit to the
embedded numbers changes its content hash and therefore the
`RESULTS.json::branch_sha`; a post-data edit is detectable and
invalidates the pre-registration (see `PREREGISTRATION.md` § 5).

## References

- Dörfler, F., Bullo, F. (2013). *Synchronization in complex oscillator
  networks and smart grids*. **PNAS** 110(6):2005–2010.
- Anderson, P. M., Fouad, A. A. (2003). *Power System Control and
  Stability*, 2nd ed. IEEE Press / Wiley.
- Athay, T., Podmore, R., Virmani, S. (1979). *A practical method for
  the direct analysis of transient stability*. **IEEE Trans. PAS**
  98(2):573–584.
- Pai, M. A. (1989). *Energy Function Analysis for Power System
  Stability*. Kluwer Academic.
- Sauer, P. W., Pai, M. A. (1998). *Power System Dynamics and
  Stability*. Prentice Hall.
