# Test Taxonomy for Physics-Grounded Code

> Claude Code: this document defines WHAT KIND of test to write for each
> invariant type. Do not write assert statements without understanding
> which category you're in.

## The Hierarchy

```
                    ┌─────────────────────┐
                    │  FALSIFICATION TEST  │  ← Can this physics be WRONG?
                    │  (breaks the theory) │     If yes → bug in implementation
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  CONVERGENCE TEST   │  ← Does the system reach
                    │  (asymptotic claim) │     the predicted steady state?
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  PROPERTY TEST      │  ← Does the invariant hold
                    │  (bounded/typed)    │     for ALL inputs? (fuzzing)
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  REGRESSION TEST    │  ← Does the same input give
                    │  (snapshot)         │     the same output? (lowest value)
                    └─────────────────────┘
```

## Test Types Explained

### 1. FALSIFICATION TEST (P0)

**Purpose**: Can the physics prediction be violated?
**When**: The theory makes an unambiguous prediction (e.g., R→0 when K<K_c)
**How**: Set up conditions where theory predicts X, check X holds.

```python
# GOOD: tests a physics prediction
def test_subcritical_decay():
    """INV-K2: K < K_c must produce R → 0."""
    N = 200
    g0 = lorentzian_g0(gamma=1.0)  # g(0) for Lorentzian
    K_c = 2.0 / (np.pi * g0)
    K = 0.1 * K_c  # well below critical

    R_final = simulate_kuramoto(N=N, K=K, steps=10000, seed=42)
    epsilon = 3.0 / np.sqrt(N)  # finite-size bound

    assert R_final < epsilon, (
        f"INV-K2 VIOLATED: R={R_final:.4f} > ε={epsilon:.4f} "
        f"at K={K:.4f} < K_c={K_c:.4f}. "
        f"Physics requires R→0 in subcritical regime."
    )
```

```python
# BAD: tests a number, not physics
def test_R_value():
    R = compute_R(phases)
    assert R < 0.3  # why 0.3? What physics does this check?
```

**Error message MUST include**: which invariant, what was expected, what was observed, WHY it's wrong.

### 2. CONVERGENCE TEST

**Purpose**: Does the system approach the theoretical steady state?
**When**: Asymptotic predictions (t→∞ behavior)
**How**: Run simulation, check trajectory trends, not single-point values.

```python
# GOOD: checks convergence trajectory
def test_R_converges_above_Kc():
    """INV-K3: K > K_c must produce nonzero steady-state R."""
    K = 2.0 * K_c
    R_trajectory = simulate_kuramoto_trajectory(N=500, K=K, steps=20000)

    # Check: R should stabilize above zero
    R_late = R_trajectory[-1000:]  # last 1000 steps
    R_mean = np.mean(R_late)
    R_std = np.std(R_late)

    assert R_mean > 0.1, f"INV-K3: R_mean={R_mean:.4f}, expected > 0 above K_c"
    assert R_std < 0.1 * R_mean, f"R not stabilized: std/mean = {R_std/R_mean:.2f}"
```

### 3. PROPERTY TEST (Fuzzing/Hypothesis)

**Purpose**: Does a universal bound hold for ALL inputs?
**When**: The invariant is ∀-quantified (e.g., R ∈ [0,1] always)
**How**: Use hypothesis/property-based testing to sample random inputs.

```python
from hypothesis import given, strategies as st

@given(
    phases=st.lists(
        st.floats(min_value=-np.pi, max_value=np.pi),
        min_size=2, max_size=1000
    )
)
def test_R_always_bounded(phases):
    """INV-K1: R ∈ [0,1] for any phase configuration."""
    R = kuramoto_order_parameter(np.array(phases))
    assert 0 <= R <= 1 + 1e-10, f"INV-K1 VIOLATED: R={R}"
```

### 4. SWEEP TEST

**Purpose**: Does a parameter sweep reproduce known qualitative behavior?
**When**: Monotonicity, scaling laws, bifurcation diagrams.
**How**: Vary parameter, check expected trend.

```python
def test_R_monotone_in_K():
    """INV-K4: R_∞ increases with K (standard model only)."""
    K_values = np.linspace(0.5, 5.0, 20)
    R_values = [steady_state_R(K=K, N=200) for K in K_values]

    # Check monotonicity (allow small violations from finite-size noise)
    violations = sum(1 for i in range(len(R_values)-1) if R_values[i+1] < R_values[i] - 0.05)
    assert violations <= 2, f"INV-K4: {violations} monotonicity violations in K-sweep"
```

### 5. ENSEMBLE TEST

**Purpose**: Statistical predictions (means, variances, distributions)
**When**: Finite-size scaling, distribution tests
**How**: Run many realizations, compute statistics, compare to theory.

```python
def test_finite_size_scaling():
    """INV-K5: ⟨R⟩ ~ 1/√N in incoherent regime."""
    K = 0  # completely incoherent
    N_values = [50, 100, 200, 500]
    n_trials = 100

    for N in N_values:
        Rs = [compute_R_steady(N=N, K=K, seed=s) for s in range(n_trials)]
        R_mean = np.mean(Rs)
        R_theory = 1.0 / np.sqrt(N)

        assert abs(R_mean - R_theory) < 3 * R_theory, (
            f"INV-K5: ⟨R⟩={R_mean:.4f}, theory=1/√{N}={R_theory:.4f}"
        )
```

### 6. TRAJECTORY TEST (Lyapunov)

**Purpose**: A quantity must be monotonic along trajectories.
**When**: Lyapunov stability, free energy descent, entropy production.
**How**: Record quantity at each step, check non-increasing/non-decreasing.

```python
def test_lyapunov_non_increasing():
    """INV-K7: V = -(K·N/2)·R² non-increasing for identical frequencies."""
    trajectory = simulate_identical_freq(K=2.0, N=100, steps=5000)
    V = -(K * N / 2) * trajectory.R**2

    violations = np.sum(np.diff(V) > 1e-8)  # allow numerical noise
    assert violations == 0, (
        f"INV-K7 VIOLATED: Lyapunov function increased {violations} times"
    )
```

## Priority System

| Priority | Meaning | CI Gate? | Example |
|----------|---------|----------|---------|
| P0 | Physics MUST hold. Violation = bug. | YES, blocks merge | R ∈ [0,1], Lyapunov monotone |
| P1 | Physics SHOULD hold. Violation = investigate. | WARNING | Finite-size scaling, monotonicity |
| P2 | Physics EXPECTED. Violation = known limitation. | NO | Distribution tests, exact scaling |

## Decision Tree for Claude Code

```
Writing a test for module X?
│
├─ Does X compute a physical quantity?
│   ├─ YES → Read .claude/physics/INVARIANTS.yaml
│   │        Find all invariants for this quantity
│   │        Write tests for EACH invariant (P0 first)
│   │        Include invariant ID in docstring and error message
│   │        
│   └─ NO → Standard unit test (input/output contract)
│
├─ What type of assertion?
│   ├─ "X == specific_number" → SUSPICIOUS. Is this a regression test?
│   │                           If physics, use theoretical bounds instead.
│   ├─ "X < threshold" → WHERE does threshold come from? 
│   │                     Must be derived from theory, not arbitrary.
│   ├─ "X increases with Y" → Sweep test. Account for noise/finite-size.
│   └─ "X is always in [a,b]" → Property test. Use hypothesis fuzzing.
│
└─ Error message checklist:
    □ Which invariant? (INV-K2, INV-5HT1, etc.)
    □ What was expected? (from theory)
    □ What was observed? (actual value)
    □ Why is it wrong? (physical reasoning)
    □ Parameters used? (K, N, steps, seed)
```
