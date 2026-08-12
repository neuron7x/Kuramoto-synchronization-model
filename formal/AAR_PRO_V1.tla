---- MODULE AAR_PRO_V1 ----
EXTENDS Naturals, Sequences

(***************************************************************************)
(* Lightweight formal model for the AAR-PRO-V1 control episode.            *)
(* The implementation tests still execute Python; this spec records the     *)
(* safety invariants that must remain true for any conforming runtime.       *)
(***************************************************************************)

CONSTANTS
    INTENT_DECLARED,
    MODEL_SEALED,
    ACTION_DISPATCHED,
    AFFERENTATION_RECEIVED,
    ERROR_COMPUTED,
    DECISION_RENDERED,
    MEMORY_ANCHORED,
    INVALID_INPUT,
    ROLLBACK_REQUIRED,
    SANCTIONED_MATCH

VARIABLES phase, modelSeq, actionSeq, observedSeq, witness, closed

Phases ==
    << INTENT_DECLARED,
       MODEL_SEALED,
       ACTION_DISPATCHED,
       AFFERENTATION_RECEIVED,
       ERROR_COMPUTED,
       DECISION_RENDERED,
       MEMORY_ANCHORED >>

Init ==
    /\ phase = INTENT_DECLARED
    /\ modelSeq = 0
    /\ actionSeq = 0
    /\ observedSeq = 0
    /\ witness = SANCTIONED_MATCH
    /\ closed = FALSE

SealModel(seq) ==
    /\ phase = INTENT_DECLARED
    /\ seq > modelSeq
    /\ phase' = MODEL_SEALED
    /\ modelSeq' = seq
    /\ UNCHANGED << actionSeq, observedSeq, witness, closed >>

Dispatch(seq) ==
    /\ phase = MODEL_SEALED
    /\ modelSeq < seq
    /\ phase' = ACTION_DISPATCHED
    /\ actionSeq' = seq
    /\ UNCHANGED << modelSeq, observedSeq, witness, closed >>

Receive(seq) ==
    /\ phase = ACTION_DISPATCHED
    /\ IF actionSeq < seq
       THEN /\ phase' = AFFERENTATION_RECEIVED
            /\ observedSeq' = seq
            /\ witness' = SANCTIONED_MATCH
            /\ closed' = FALSE
       ELSE /\ phase' = ERROR_COMPUTED
            /\ observedSeq' = seq
            /\ witness' \in { INVALID_INPUT, ROLLBACK_REQUIRED }
            /\ closed' = TRUE
    /\ UNCHANGED << modelSeq, actionSeq >>

Compute ==
    /\ phase = AFFERENTATION_RECEIVED
    /\ modelSeq < actionSeq
    /\ actionSeq < observedSeq
    /\ phase' = ERROR_COMPUTED
    /\ witness' \in { SANCTIONED_MATCH, ROLLBACK_REQUIRED }
    /\ UNCHANGED << modelSeq, actionSeq, observedSeq, closed >>

Render ==
    /\ phase = ERROR_COMPUTED
    /\ witness # INVALID_INPUT
    /\ closed = FALSE
    /\ phase' = DECISION_RENDERED
    /\ UNCHANGED << modelSeq, actionSeq, observedSeq, witness, closed >>

Persist ==
    /\ phase = DECISION_RENDERED
    /\ phase' = MEMORY_ANCHORED
    /\ closed' = TRUE
    /\ UNCHANGED << modelSeq, actionSeq, observedSeq, witness >>

Next ==
    \/ \E seq \in Nat : SealModel(seq)
    \/ \E seq \in Nat : Dispatch(seq)
    \/ \E seq \in Nat : Receive(seq)
    \/ Compute
    \/ Render
    \/ Persist

ChronologyInvariant ==
    phase \in { AFFERENTATION_RECEIVED, ERROR_COMPUTED, DECISION_RENDERED, MEMORY_ANCHORED }
        /\ witness = SANCTIONED_MATCH
        => modelSeq < actionSeq /\ actionSeq < observedSeq

FailClosedInvariant ==
    witness \in { INVALID_INPUT, ROLLBACK_REQUIRED } => closed \/ phase = ERROR_COMPUTED

NoMemoryWithoutDecision ==
    phase = MEMORY_ANCHORED => closed /\ witness # INVALID_INPUT

Spec == Init /\ [][Next]_<<phase, modelSeq, actionSeq, observedSeq, witness, closed>>

====
