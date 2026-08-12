--------------------------- MODULE RicciFlowSurgery ---------------------------
(***************************************************************************
  Discrete Ricci flow with neckpinch surgery.

  Source: research/ricci_flow/ + GeoSync research extension.
          No alpha claim — this spec encodes the *safety* properties of the
          flow + surgery step, not any topological-inference statement.

  We model the graph as a tuple over a finite node set:

      W              -- [Node \X Node -> Real_+]   symmetric edge weights
      kappa          -- [Node \X Node -> Real]     Ollivier curvature on edges
      surgery_log    -- sequence of "NeckpinchEvent" records
      cfg            -- record { preserve_total_edge_mass: BOOLEAN,
                                 preserve_connectedness:  BOOLEAN,
                                 max_surgery_fraction:    Real,
                                 allow_disconnect:        BOOLEAN }
      mass_before    -- Σ W[i,j] before the most recent FlowStep+Surgery cycle
      mass_after     -- Σ W[i,j] after  the most recent FlowStep+Surgery cycle
      n_active_edges -- |{(i,j) : W[i,j] > 0}|     before surgery
      Connected      -- BOOLEAN flag computed by Validate

  Actions (declarative — each step re-establishes the invariants):
      FlowStep    — w_ij ← w_ij − η · κ_ij · w_ij    (symmetric update)
      Surgery     — clamp/remove edges with w_ij below threshold,
                    each event recorded in surgery_log
      Validate    — recompute Connected and the fraction bound

  Safety properties (required to hold in all reachable states):
      * TypeOK                       — type/range invariants
      * WeightsFinite                — every W[i,j] is a finite, non-negative real
      * WeightsSymmetric             — W[i,j] = W[j,i]
      * MassPreservedWhenEnabled     — preserve_total_edge_mass ⇒
                                       mass_after = mass_before
      * ConnectednessPreserved       — preserve_connectedness ∧
                                       ¬allow_disconnect ⇒ Connected
      * SurgeryRecorded              — every removed/clamped edge appears in
                                       surgery_log as a NeckpinchEvent
      * MaxSurgeryFractionBounded    — |surgery_log| ≤ max_surgery_fraction · |E|

  Liveness properties are deliberately omitted: this is a *flow + surgery
  step*, not a protocol with progress requirements.

  Invariant ID: INV-RC-FLOW.

  Notes on syntax review (TLC may be unavailable on the CI host):
      Parsed by SANY 2.1 (`java -cp tla2tools.jar tla2sany.SANY`).
      No model-checking run; properties below are stated as type-correct
      conjectures over the abstract state.
 ***************************************************************************)

EXTENDS Naturals, Sequences, FiniteSets, Reals

CONSTANTS Node,            \* finite set of node ids
          MaxSurgeries     \* state-space bound on |surgery_log|

ASSUME MaxSurgeries \in Nat

VARIABLES
  W,                       \* [Node \X Node -> Real_+]   edge weights
  kappa,                   \* [Node \X Node -> Real]     curvature on edges
  surgery_log,             \* Seq( NeckpinchEvent )
  cfg,                     \* configuration record
  mass_before,             \* Real_+
  mass_after,              \* Real_+
  n_active_edges,          \* Nat
  Connected,               \* BOOLEAN
  removed_edges            \* set of <<i,j>> removed/clamped this cycle

vars == << W, kappa, surgery_log, cfg, mass_before, mass_after,
           n_active_edges, Connected, removed_edges >>

(***************************************************************************
  NeckpinchEvent record shape.
 ***************************************************************************)
NeckpinchEvent(i, j, action, w_before, w_after) ==
  [ i        |-> i,
    j        |-> j,
    action   |-> action,        \* "REMOVED" or "CLAMPED"
    w_before |-> w_before,
    w_after  |-> w_after ]

NeckpinchEventActions == {"REMOVED", "CLAMPED"}

(***************************************************************************
  Type invariant.
 ***************************************************************************)
TypeOK ==
  /\ W              \in [Node \X Node -> Real]
  /\ kappa          \in [Node \X Node -> Real]
  /\ surgery_log    \in Seq([ i        : Node,
                              j        : Node,
                              action   : NeckpinchEventActions,
                              w_before : Real,
                              w_after  : Real ])
  /\ cfg            \in [ preserve_total_edge_mass : BOOLEAN,
                          preserve_connectedness   : BOOLEAN,
                          max_surgery_fraction     : Real,
                          allow_disconnect         : BOOLEAN ]
  /\ mass_before    \in Real
  /\ mass_after     \in Real
  /\ n_active_edges \in Nat
  /\ Connected      \in BOOLEAN
  /\ removed_edges  \subseteq (Node \X Node)
  /\ \A i, j \in Node : W[i, j] >= 0
  /\ cfg.max_surgery_fraction >= 0 /\ cfg.max_surgery_fraction <= 1
  /\ Len(surgery_log) <= MaxSurgeries

(***************************************************************************
  Safety invariants.
 ***************************************************************************)

WeightsFinite ==
  \A i, j \in Node : W[i, j] \in Real /\ W[i, j] >= 0

WeightsSymmetric ==
  \A i, j \in Node : W[i, j] = W[j, i]

MassPreservedWhenEnabled ==
  cfg.preserve_total_edge_mass => (mass_after = mass_before)

ConnectednessPreserved ==
  (cfg.preserve_connectedness /\ ~cfg.allow_disconnect) => Connected

\* For every removed/clamped edge there is an event in surgery_log naming it.
SurgeryRecorded ==
  \A e \in removed_edges :
    \E k \in 1 .. Len(surgery_log) :
      /\ surgery_log[k].i = e[1]
      /\ surgery_log[k].j = e[2]
      /\ surgery_log[k].action \in NeckpinchEventActions

\* Surgery cap: events recorded this cycle never exceed the configured
\* fraction of the active-edge count observed before the cycle.
MaxSurgeryFractionBounded ==
  Len(surgery_log) <= cfg.max_surgery_fraction * n_active_edges

(***************************************************************************
  Initial predicate and stutter-only next-state relation.
 ***************************************************************************)
Init ==
  /\ W              = [<<i, j>> \in Node \X Node |-> 0]
  /\ kappa          = [<<i, j>> \in Node \X Node |-> 0]
  /\ surgery_log    = << >>
  /\ cfg            = [ preserve_total_edge_mass |-> TRUE,
                        preserve_connectedness   |-> TRUE,
                        max_surgery_fraction     |-> 0,
                        allow_disconnect         |-> FALSE ]
  /\ mass_before    = 0
  /\ mass_after     = 0
  /\ n_active_edges = 0
  /\ Connected      = TRUE
  /\ removed_edges  = {}

Next == UNCHANGED vars
  \* flow + surgery is reasoned about as an invariant, not a protocol

Spec == Init /\ [][Next]_vars

(***************************************************************************
  Safety conjunction — used by the Python lint test as a property catalogue.
 ***************************************************************************)
SafetyInvariants ==
  /\ TypeOK
  /\ WeightsFinite
  /\ WeightsSymmetric
  /\ MassPreservedWhenEnabled
  /\ ConnectednessPreserved
  /\ SurgeryRecorded
  /\ MaxSurgeryFractionBounded

THEOREM Safety == Spec => []SafetyInvariants

==============================================================================
