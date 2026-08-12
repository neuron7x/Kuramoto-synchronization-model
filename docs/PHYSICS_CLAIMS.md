# PHYSICS CLAIMS

This packet is synchronized with the current `physics_contracts/falsification_catalog.yaml` surface. The stale 10-law claim table has been replaced because the executable catalog now declares 47 laws.

New executable laws introduced by this PR and now represented here:

| Law | Domain | Positive witness | Negative control |
| --- | --- | --- | --- |
| `kuramoto_critical_scaling` | ricci_kuramoto | `tests/physics/test_kuramoto_critical_scaling.py::test_supercritical_R_matches_closed_form` | `tests/physics/test_kuramoto_critical_scaling.py::test_subcritical_and_invalid_are_rejected` |
| `kuramoto_subcritical_finite_size` | ricci_kuramoto | `tests/physics/test_kuramoto_subcritical_finite_size.py::test_subcritical_order_parameter_obeys_inverse_sqrt_n_noise_floor` | `tests/physics/test_kuramoto_subcritical_finite_size.py::test_supercritical_breaks_noise_floor_and_invalid_inputs_fail_closed` |
| `kuramoto_frequency_entrainment` | ricci_kuramoto | `tests/physics/test_kuramoto_frequency_entrainment.py::test_supercritical_locks_detuned_oscillators_to_common_frequency` | `tests/physics/test_kuramoto_frequency_entrainment.py::test_subcritical_entrainment_claim_is_falsified` |
| `ollivier_ricci_universal_upper_bound` | ricci_kuramoto | `tests/physics/test_ollivier_ricci_bounds.py::test_ollivier_upper_bound_is_universal` | `tests/physics/test_ollivier_ricci_bounds.py::test_symmetric_band_is_not_universal` |
| `ricci_flow_monotonicity` | ricci_kuramoto | `tests/physics/test_ricci_flow_monotonicity.py::test_f_functional_nonincreases_under_positive_ricci_flow` | `tests/physics/test_ricci_flow_monotonicity.py::test_negative_curvature_rewiring_injects_f_energy_is_rejected` |

Full catalog accounting:
- declared executable laws: 47
- required invariant per law: positive witness plus negative control
- governance law: `law_requires_positive_and_negative_witness`

Regenerate the complete expanded table with:

```bash
python tools/validate_physics_contracts.py
python tools/build_physics_review_packet.py
```
