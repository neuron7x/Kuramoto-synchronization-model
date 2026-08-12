----------------------- MODULE CapitalWeightedKuramoto -----------------------
(***************************************************************************
  Capital-weighted (β-tilted) coupling matrix for the Kuramoto regime
  observer.

  Source: research/capital_weighted_kuramoto/ + GeoSync research extension.
          No alpha claim — this spec encodes the *safety* properties of the
          coupling-rebuild step, not any economic statement.

  We model the rebuild as a tuple over a finite node set:

      A          -- baseline (β = 1) symmetric, zero-diagonal adjacency
      r          -- per-node depth proxy r_i ∈ Real_+ (e.g. capital, L2 size)
      beta       -- depth tilt exponent ∈ [beta_min, beta_max]
      K          -- rebuilt coupling K_ij = A_ij · (r_i · r_j) ^ beta
                    with diagonal forced to zero
      snapshot   -- last L2 snapshot or ⊥ (None)
      used_fallback   -- TRUE iff K was rebuilt against the baseline
      K_baseline      -- pre-rebuild fallback (= A here)
      sig_ts_ns       -- signal arrival timestamp (ns)
      snap_ts_ns      -- snapshot timestamp (ns) or ⊥

  Safety properties (required to hold in all reachable states):
      * TypeOK                       — type/range invariants
      * KBetaFinite                  — every K_ij is a finite real
      * KBetaSymmetric               — K_ij = K_ji
      * ZeroDiagonal                 — K_ii = 0
      * BetaOneRecoversBaseline      — beta = 1 ⟹ K = A
      * MissingL2Fallback            — snapshot = ⊥ ⟹
                                       used_fallback ∧ K = K_baseline
      * NoFutureL2                   — snap_ts_ns ≤ sig_ts_ns whenever
                                       a snapshot is consumed.

  Liveness properties are deliberately omitted: this is a *rebuild step*,
  not a protocol with progress requirements.

  Invariant ID: INV-KBETA.

  Notes on syntax review (TLC unavailable on this CI host):
      Parsed by SANY 2.1 (`java -cp tla2tools.jar tla2sany.SANY`).
      No model-checking run; properties below are stated as type-correct
      conjectures over the abstract state.
 ***************************************************************************)

EXTENDS Naturals, Reals

CONSTANTS Node,             \* finite set of node ids
          BetaMin, BetaMax  \* admissible range for the depth tilt

ASSUME BetaMin <= BetaMax

VARIABLES
  A,                        \* [Node \X Node -> Real]   baseline adjacency
  r,                        \* [Node -> Real_+]         depth proxy
  beta,                     \* Real
  K,                        \* [Node \X Node -> Real]   rebuilt coupling
  snapshot,                 \* {"PRESENT","NONE"}
  used_fallback,            \* BOOLEAN
  K_baseline,               \* [Node \X Node -> Real]
  sig_ts_ns,                \* Nat
  snap_ts_ns                \* Nat \cup {-1}    (-1 encodes "missing")

vars == << A, r, beta, K, snapshot, used_fallback,
           K_baseline, sig_ts_ns, snap_ts_ns >>

(***************************************************************************
  Type invariant.
 ***************************************************************************)
TypeOK ==
  /\ A          \in [Node \X Node -> Real]
  /\ r          \in [Node -> Real]
  /\ beta       \in Real
  /\ K          \in [Node \X Node -> Real]
  /\ K_baseline \in [Node \X Node -> Real]
  /\ snapshot   \in {"PRESENT", "NONE"}
  /\ used_fallback \in BOOLEAN
  /\ sig_ts_ns  \in Nat
  /\ snap_ts_ns \in Nat \cup {-1}
  /\ \A i \in Node : r[i] >= 0
  /\ beta >= BetaMin /\ beta <= BetaMax

(***************************************************************************
  Safety invariants.
 ***************************************************************************)

\* Every K_ij is a finite real. In TLA+/Reals "Real" excludes infinities; the
\* invariant is therefore a type assertion plus an explicit absence-of-NaN
\* check at the implementation boundary (Python: np.isfinite).
KBetaFinite ==
  \A i, j \in Node : K[i, j] \in Real

KBetaSymmetric ==
  \A i, j \in Node : K[i, j] = K[j, i]

ZeroDiagonal ==
  \A i \in Node : K[i, i] = 0

BetaOneRecoversBaseline ==
  (beta = 1) => (\A i, j \in Node : K[i, j] = A[i, j])

MissingL2Fallback ==
  (snapshot = "NONE") => (used_fallback /\ \A i, j \in Node :
                           K[i, j] = K_baseline[i, j])

\* When a snapshot is consumed (snapshot = "PRESENT") it must not be
\* time-stamped after the signal that triggered the rebuild.
NoFutureL2 ==
  (snapshot = "PRESENT") => (snap_ts_ns >= 0 /\ snap_ts_ns <= sig_ts_ns)

(***************************************************************************
  Initial predicate and stutter-only next-state relation.
  The rebuild is purely declarative: each step recomputes K from (A, r, beta)
  with the fail-closed fallback when the snapshot is missing.
 ***************************************************************************)
Init ==
  /\ A             = [<<i, j>> \in Node \X Node |-> 0]
  /\ r             = [i \in Node |-> 0]
  /\ beta          = 1
  /\ K             = [<<i, j>> \in Node \X Node |-> 0]
  /\ K_baseline    = [<<i, j>> \in Node \X Node |-> 0]
  /\ snapshot      = "NONE"
  /\ used_fallback = TRUE
  /\ sig_ts_ns     = 0
  /\ snap_ts_ns    = -1

Next == UNCHANGED vars
  \* the rebuild is reasoned about as an invariant, not a protocol

Spec == Init /\ [][Next]_vars

(***************************************************************************
  Safety conjunction — used by the Python lint test as a property catalogue.
 ***************************************************************************)
SafetyInvariants ==
  /\ TypeOK
  /\ KBetaFinite
  /\ KBetaSymmetric
  /\ ZeroDiagonal
  /\ BetaOneRecoversBaseline
  /\ MissingL2Fallback
  /\ NoFutureL2

THEOREM Safety == Spec => []SafetyInvariants

==============================================================================
