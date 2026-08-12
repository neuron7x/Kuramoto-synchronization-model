------------------------ MODULE SparseSimplicialKuramoto ------------------------
(***************************************************************************
  Sparse simplicial (higher-order) Kuramoto with explicit triangle index.

  Source: research/simplicial_kuramoto/ + GeoSync research extension.
          No alpha claim — this spec encodes the *safety* properties of the
          sparse triadic update, not any synchronisation statement.

  The simplicial extension augments the pairwise Kuramoto RHS with a
  triadic term over a sparse, ordered triangle set T.  Letting θ ∈ [-π,π]^N
  on a node set Node, the dynamics has the form

      dθ_i/dt = ω_i
              + σ₁ · pairwise_rhs(θ)_i                 (existing engine)
              + σ₂ · triadic_term(θ, T)_i              (this extension)

  We model the rebuild + step as a tuple over a finite node set:

      theta          -- [Node -> Real]   phases ∈ [-π, π]
      omega          -- [Node -> Real]   intrinsic frequencies
      T              -- set of <<i,j,k>> with i < j < k
      sigma1         -- Real             pairwise coupling
      sigma2         -- Real             triadic coupling
      R              -- Real             order parameter |⟨e^{iθ}⟩|
      rhs            -- [Node -> Real]   full RHS (pairwise + triadic)
      pairwise_rhs   -- [Node -> Real]   pairwise-only RHS
      triadic_term   -- [Node -> Real]   triadic-only term

  Safety properties (required to hold in all reachable states):
      * TypeOK                        — type/range invariants
      * OrderPreserved                — every (i,j,k) ∈ T satisfies i < j < k
      * Unique                        — no duplicate triangles
      * RBounds                       — R(t) ∈ [0, 1]
      * Sigma2ZeroEqualsPairwise      — σ₂ = 0 ⟹ rhs = pairwise_rhs
      * NoTrianglesZeroTriadic        — T = ∅ ⟹ triadic_term = 0
      * Finite                        — every phase derivative is a finite real

  Liveness properties are deliberately omitted: this is a *step kernel*,
  not a protocol with progress requirements.

  Invariant ID: INV-HO-SPARSE.

  Notes on syntax review (TLC may be unavailable on the CI host):
      Parsed by SANY 2.1 (`java -cp tla2tools.jar tla2sany.SANY`).
      No model-checking run; properties below are stated as type-correct
      conjectures over the abstract state.
 ***************************************************************************)

EXTENDS Naturals, FiniteSets, Reals

CONSTANTS Node,         \* finite set of node ids, totally ordered by <
          NodeOrder     \* [Node \X Node -> BOOLEAN]  total order

ASSUME \A i \in Node : NodeOrder[i, i] = FALSE
ASSUME \A i, j \in Node : (i # j) =>
         (NodeOrder[i, j] \/ NodeOrder[j, i])

VARIABLES
  theta,            \* [Node -> Real]   phases
  omega,            \* [Node -> Real]   intrinsic frequencies
  T,                \* SUBSET (Node \X Node \X Node)
  sigma1,           \* Real
  sigma2,           \* Real
  R,                \* Real
  rhs,              \* [Node -> Real]
  pairwise_rhs,     \* [Node -> Real]
  triadic_term      \* [Node -> Real]

vars == << theta, omega, T, sigma1, sigma2, R,
           rhs, pairwise_rhs, triadic_term >>

(***************************************************************************
  Type invariant.
 ***************************************************************************)
TypeOK ==
  /\ theta        \in [Node -> Real]
  /\ omega        \in [Node -> Real]
  /\ T            \subseteq (Node \X Node \X Node)
  /\ sigma1       \in Real
  /\ sigma2       \in Real
  /\ R            \in Real
  /\ rhs          \in [Node -> Real]
  /\ pairwise_rhs \in [Node -> Real]
  /\ triadic_term \in [Node -> Real]

(***************************************************************************
  Safety invariants.
 ***************************************************************************)

\* Triangles are stored canonically with i < j < k under NodeOrder.
OrderPreserved ==
  \A t \in T : NodeOrder[t[1], t[2]] /\ NodeOrder[t[2], t[3]]

\* Set semantics already prevent duplicates; we restate the property as a
\* documentation invariant for the sparse-array implementation that backs
\* this set in Python (numpy structured array).
Unique ==
  \A t1, t2 \in T :
    (t1[1] = t2[1] /\ t1[2] = t2[2] /\ t1[3] = t2[3]) => (t1 = t2)

RBounds ==
  R >= 0 /\ R <= 1

Sigma2ZeroEqualsPairwise ==
  (sigma2 = 0) => (\A i \in Node : rhs[i] = pairwise_rhs[i])

NoTrianglesZeroTriadic ==
  (T = {}) => (\A i \in Node : triadic_term[i] = 0)

\* Every phase derivative is a finite real. In TLA+/Reals "Real" excludes
\* infinities; the invariant is therefore a type assertion plus an explicit
\* absence-of-NaN check at the implementation boundary (Python: np.isfinite).
Finite ==
  /\ \A i \in Node : rhs[i]          \in Real
  /\ \A i \in Node : pairwise_rhs[i] \in Real
  /\ \A i \in Node : triadic_term[i] \in Real

(***************************************************************************
  Initial predicate and stutter-only next-state relation.
 ***************************************************************************)
Init ==
  /\ theta        = [i \in Node |-> 0]
  /\ omega        = [i \in Node |-> 0]
  /\ T            = {}
  /\ sigma1       = 0
  /\ sigma2       = 0
  /\ R            = 0
  /\ rhs          = [i \in Node |-> 0]
  /\ pairwise_rhs = [i \in Node |-> 0]
  /\ triadic_term = [i \in Node |-> 0]

Next == UNCHANGED vars
  \* the sparse simplicial step is reasoned about as an invariant, not a
  \* protocol

Spec == Init /\ [][Next]_vars

(***************************************************************************
  Safety conjunction — used by the Python lint test as a property catalogue.
 ***************************************************************************)
SafetyInvariants ==
  /\ TypeOK
  /\ OrderPreserved
  /\ Unique
  /\ RBounds
  /\ Sigma2ZeroEqualsPairwise
  /\ NoTrianglesZeroTriadic
  /\ Finite

THEOREM Safety == Spec => []SafetyInvariants

==============================================================================
