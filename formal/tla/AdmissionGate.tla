------------------------------ MODULE AdmissionGate ------------------------------
(***************************************************************************
  Formal specification of the four-barrier event-admission gate shipped in
  PR #322 / PR #323 (``core/events/admission.py``).

  The gate runs four barriers in strict order on every ``DomainEvent`` that
  reaches ``PostgresEventStore.append``:

      B1 STRUCTURAL  — schema re-validation
      B2 CAUSAL      — (aggregate_type, event_type) transition must be
                       declared in the AggregateTransitionRegistry
      B3 STATE       — semantic validator inspects live aggregate state
      B4 INVARIANT   — domain-rule breach

  A verdict is one of ACCEPT or REJECT(barrier, code). First rejection wins.

  This module encodes the protocol as a state machine and asserts three
  safety properties under TLC model checking:

      TypeOK                   — every emitted verdict is well-formed
      SafeFirstRejectionWins   — an accepted verdict has no barrier
      RejectCodeMatchesBarrier — each reject cites the canonical code
                                 for its barrier (no mis-labelling)
 ***************************************************************************)
EXTENDS Naturals, Sequences, FiniteSets, TLC

CONSTANTS
  EventTypes,          \* e.g. {"evt_a", "evt_b", "evt_c"}
  RegisteredEvents,    \* subset of EventTypes declared in the registry
  StructurallyValid,   \* subset of EventTypes with a valid schema
  StateValid,          \* subset of EventTypes passing B3
  InvariantValid,      \* subset of EventTypes passing B4
  MaxEvents            \* bound on submitted events (state-space control)

VARIABLES
  pending,             \* sequence of events awaiting a verdict
  verdicts             \* sequence of emitted verdicts

vars == <<pending, verdicts>>

Barriers == {"B1_STRUCTURAL", "B2_CAUSAL", "B3_STATE", "B4_INVARIANT"}
Codes    == {"OK", "E_STRUCTURAL_INVALID", "E_TRANSITION_UNKNOWN",
             "E_STATE_INCONSISTENT", "E_INVARIANT_VIOLATED"}

Verdict(accepted, barrier, code) ==
  [accepted |-> accepted, barrier |-> barrier, code |-> code]

ComputeVerdict(evt) ==
  IF evt \notin StructurallyValid
    THEN Verdict(FALSE, "B1_STRUCTURAL", "E_STRUCTURAL_INVALID")
  ELSE IF evt \notin RegisteredEvents
    THEN Verdict(FALSE, "B2_CAUSAL",     "E_TRANSITION_UNKNOWN")
  ELSE IF evt \notin StateValid
    THEN Verdict(FALSE, "B3_STATE",      "E_STATE_INCONSISTENT")
  ELSE IF evt \notin InvariantValid
    THEN Verdict(FALSE, "B4_INVARIANT",  "E_INVARIANT_VIOLATED")
  ELSE     Verdict(TRUE,  "NONE",        "OK")

Init ==
  /\ pending = << >>
  /\ verdicts = << >>

Submit ==
  /\ Len(pending) + Len(verdicts) < MaxEvents
  /\ \E evt \in EventTypes :
       pending' = Append(pending, evt)
  /\ UNCHANGED verdicts

Decide ==
  /\ Len(pending) > 0
  /\ verdicts' = Append(verdicts, ComputeVerdict(Head(pending)))
  /\ pending' = Tail(pending)

Next == Submit \/ Decide

Spec == Init /\ [][Next]_vars /\ WF_vars(Decide)

(*
 * ---------------------------------------------------------------------------
 * SAFETY INVARIANTS (checked by TLC via MC.cfg)
 * ---------------------------------------------------------------------------
 *)

TypeOK ==
  /\ pending \in Seq(EventTypes)
  /\ \A i \in DOMAIN verdicts :
       /\ verdicts[i].accepted \in BOOLEAN
       /\ verdicts[i].barrier \in Barriers \cup {"NONE"}
       /\ verdicts[i].code \in Codes

(* First-rejection-wins: an accepted verdict is never labelled with a barrier
   other than "NONE", and its code is exactly "OK". *)
SafeFirstRejectionWins ==
  \A i \in DOMAIN verdicts :
    verdicts[i].accepted =>
      /\ verdicts[i].barrier = "NONE"
      /\ verdicts[i].code = "OK"

(* Every rejection cites the canonical code for its barrier. *)
RejectCodeMatchesBarrier ==
  \A i \in DOMAIN verdicts :
    ~verdicts[i].accepted =>
      \/ (verdicts[i].barrier = "B1_STRUCTURAL" /\ verdicts[i].code = "E_STRUCTURAL_INVALID")
      \/ (verdicts[i].barrier = "B2_CAUSAL"     /\ verdicts[i].code = "E_TRANSITION_UNKNOWN")
      \/ (verdicts[i].barrier = "B3_STATE"      /\ verdicts[i].code = "E_STATE_INCONSISTENT")
      \/ (verdicts[i].barrier = "B4_INVARIANT"  /\ verdicts[i].code = "E_INVARIANT_VIOLATED")

==============================================================================
