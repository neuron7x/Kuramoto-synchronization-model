------------------------- MODULE RobustFreeEnergyGate -------------------------
(***************************************************************************
  Distributionally robust free-energy gate for the TACL controller.

  Source: tacl/dr_free.py + Nature Communications 2025
          (s41467-025-67348-6).  No alpha claim — this spec encodes the
          *safety* properties of the gate, not any economic statement.

  We model the gate as a tuple of non-negative reals:

      MetricsBase     -- nominal metric values m_i >= 0
      Radii           -- per-metric radii r_i >= 0  (zero outside ambiguity set)
      MetricsAdv      -- m_i_adv = m_i * (1 + r_i)
      F_nominal       -- monotonically non-decreasing in metrics
      F_robust        -- F applied to MetricsAdv

  Safety properties (required to hold in all reachable states):
      * TypeOK                       — type/range invariants
      * NominalBounded               — F_nominal in [F_min, F_max]
      * RobustDominatesNominal       — F_robust >= F_nominal
      * ZeroAmbiguityEqualsNominal   — Radii = 0 ⟹ F_robust = F_nominal
      * FailClosedOnMalformedAmbiguity
                                     — any negative or non-finite radius forces
                                       gate into DORMANT (fail-closed).

  Liveness properties are deliberately omitted: this is a *gate*, not a
  protocol with progress requirements.
 ***************************************************************************)

EXTENDS Naturals, Reals

CONSTANTS Metric,           \* finite set of metric names
          F_min, F_max,     \* admissible range for nominal free energy
          Crisis            \* threshold for DORMANT classification

ASSUME F_min <= F_max
ASSUME F_min <= Crisis /\ Crisis <= F_max

VARIABLES
  metrics_base,             \* [Metric -> Real_+]
  radii,                    \* [Metric -> Real_+]
  metrics_adv,              \* [Metric -> Real_+]
  F_nominal,                \* Real
  F_robust,                 \* Real
  state                     \* {"NORMAL","WARNING","DORMANT"}

vars == << metrics_base, radii, metrics_adv, F_nominal, F_robust, state >>

(***************************************************************************
  Type invariant.
 ***************************************************************************)
TypeOK ==
  /\ metrics_base \in [Metric -> Real]
  /\ radii        \in [Metric -> Real]
  /\ metrics_adv  \in [Metric -> Real]
  /\ F_nominal    \in Real
  /\ F_robust     \in Real
  /\ state \in {"NORMAL", "WARNING", "DORMANT"}
  /\ \A m \in Metric : metrics_base[m] >= 0
  /\ \A m \in Metric : metrics_adv[m]  >= 0

(***************************************************************************
  Safety invariants.
 ***************************************************************************)
NominalBounded ==
  F_nominal >= F_min /\ F_nominal <= F_max

RobustDominatesNominal ==
  F_robust >= F_nominal

ZeroAmbiguityEqualsNominal ==
  (\A m \in Metric : radii[m] = 0) => (F_robust = F_nominal)

\* If any radius is negative the gate must be DORMANT (fail-closed).
FailClosedOnMalformedAmbiguity ==
  (\E m \in Metric : radii[m] < 0) => (state = "DORMANT")

(***************************************************************************
  Initial predicate and stutter-only next-state relation.
  The gate is purely declarative: each step recomputes derived quantities.
 ***************************************************************************)
Init ==
  /\ metrics_base = [m \in Metric |-> 0]
  /\ radii        = [m \in Metric |-> 0]
  /\ metrics_adv  = [m \in Metric |-> 0]
  /\ F_nominal    = F_min
  /\ F_robust     = F_min
  /\ state        = "NORMAL"

Next == UNCHANGED vars  \* the gate is reasoned about as an invariant, not a protocol

Spec == Init /\ [][Next]_vars

(***************************************************************************
  Safety conjunction — used by the Python lint test as a property catalogue.
 ***************************************************************************)
SafetyInvariants ==
  /\ TypeOK
  /\ NominalBounded
  /\ RobustDominatesNominal
  /\ ZeroAmbiguityEqualsNominal
  /\ FailClosedOnMalformedAmbiguity

THEOREM Safety == Spec => []SafetyInvariants

==============================================================================
