# LLM Mathematical Reasoning Agent - Engineering Specification

## State Interface

```
ProofState = {
  goal: Statement,
  assumptions: List[Statement],  // max_size=5
  proven_lemmas: Set[Statement],
  subgoal_stack: Stack[Subgoal],
  step_count: Int,
  complexity_metric: Float,
  failed_tactics: Set[TacticID],
  context_tokens: Int
}

Subgoal = {
  statement: Statement,
  parent_goal: GoalID,
  priority: Float,  // 0.0-1.0
  time_budget: Int,  // steps allocated
  steps_used: Int
}

Statement = {
  type: {equation, inequality, existence, universal, implication},
  variables: Set[Variable],
  constraints: Set[Constraint],
  complexity: Int  // AST node count
}

Variable = {
  name: String,
  domain: Domain,
  constraints: Set[Constraint]
}
```

## Metric Definitions

```
progress(state_t, state_t+1) = 
  0.5 * goal_distance_reduction(state_t, state_t+1) +
  0.3 * proven_lemmas_value(state_t+1) +
  0.2 * subgoal_reduction(state_t, state_t+1)

goal_distance_reduction = 
  (syntactic_diff(goal, current) at t - syntactic_diff(goal, current) at t+1) / 
  initial_complexity

syntactic_diff(A, B) = 
  edit_distance(normalize(A), normalize(B)) / max(|A|, |B|)

complexity_growth(state) = 
  current_expression_size / initial_expression_size

stagnation_detected = 
  progress(t-3, t) < 0.05 AND steps > 10

confidence(state) = 
  sigmoid(
    2.0 * proven_lemmas_count - 
    1.0 * assumptions_used - 
    0.5 * complexity_growth(state) -
    1.5 * failed_tactics_count
  )

difficulty_estimate(problem) = 
  0.4 * variable_count +
  0.3 * quantifier_depth +
  0.2 * operator_complexity +
  0.1 * domain_restriction_count

relevance_decay(lemma, t) = 
  initial_relevance * exp(-lambda * (current_step - lemma_introduction_step))
  where lambda = 0.1
```

## Tactic Selection Scoring

```
score(tactic, state) = 
  w1 * pattern_match_score(tactic, state.goal) +
  w2 * success_rate(tactic, similar_problems) +
  w3 * complexity_penalty(tactic) +
  w4 * novelty_bonus(tactic, state.failed_tactics)

where:
  w1=0.4, w2=0.3, w3=-0.2, w4=0.1

pattern_match_score = {
  1.0 if exact_template_match,
  0.7 if structural_similarity > 0.8,
  0.4 if preconditions_satisfied,
  0.0 otherwise
}

complexity_penalty(tactic) = 
  -0.1 * expected_subgoals(tactic) - 
  0.05 * expected_new_variables(tactic)

TACTIC_RANKING:
1. IF (tactic.score > 0.7) -> apply immediately
2. IF (0.4 < tactic.score < 0.7) -> add to candidate_pool
3. IF (tactic.score < 0.4) -> skip

BACKTRACK_TRIGGER:
- progress < 0 for 5 consecutive steps, OR
- complexity_growth > 3.0, OR
- contradiction_detected, OR
- step_count > subgoal.time_budget
```

## Symbolic Manipulation Engine

```
normalize(expression) -> canonical_form:
  1. Expand all products
  2. Collect like terms
  3. Sort by lexicographic order
  4. Reduce to lowest terms
  5. Apply standard identities

safe_division(A, B, constraints):
  IF B in constraints.non_zero:
    return A/B
  ELIF provable(B != 0, constraints):
    add B != 0 to constraints.non_zero
    return A/B
  ELSE:
    CASE_SPLIT: [B=0, B!=0]

variable_substitution(expr, var, value, domain):
  CHECK: value ∈ domain(var)
  CHECK: no_circular_dependency(var, value)
  result = replace_all(expr, var, value)
  propagate_constraints(result)
  return result
```

## Error Detection Rules

```
type_check(operation, operands):
  FOR each operand in operands:
    IF operand.type NOT in operation.valid_types:
      THROW TypeError(operation, operand, expected_types)
  return operation.result_type

scope_check(variable, context):
  IF variable NOT in context.bound_variables:
    THROW UndefinedVariable(variable, context)
  IF variable.binding_level < context.current_level:
    THROW ScopeViolation(variable, context)

circular_dependency_check(goal, proof_chain):
  IF goal in proof_chain:
    THROW CircularReasoning(goal, proof_chain)
  
quantifier_order_check(transformation):
  IF swaps_quantifiers(transformation):
    CHECK equivalence_conditions_met(transformation)
    IF NOT met:
      THROW QuantifierOrderError(transformation)
```

## Proof Strategy Decision Tree

```
select_strategy(problem):
  
  // Level 1: Problem type
  IF problem.type == existence:
    IF constructive_witness_obvious:
      RETURN construction_proof
    ELSE:
      RETURN contradiction_proof
  
  // Level 2: Structure
  IF problem.has_recursive_structure:
    IF base_case_trivial AND inductive_step_clear:
      RETURN induction_proof
  
  IF problem.type == universal AND negation_simpler:
    RETURN contrapositive_proof
  
  // Level 3: Domain
  IF problem.domain == finite:
    RETURN case_exhaustion_proof
  
  IF problem.has_natural_partition:
    partition_quality = evaluate_partition(problem)
    IF partition_quality > 0.6:
      RETURN case_analysis_proof
  
  // Default
  RETURN direct_proof

evaluate_partition(problem):
  cases = identify_cases(problem)
  score = 1.0 / len(cases)  // fewer cases better
  score *= min(case_complexity(c) for c in cases) / problem.complexity
  return score
```

## Context Management

```
context_budget = 8000 tokens  // reserve for reasoning

WHEN context_usage > 0.8 * context_budget:
  PRUNE:
    1. Remove failed_approaches older than 20 steps
    2. Compress proven_lemmas: keep statement, drop proof
    3. Merge redundant subgoals
    4. Discard lemmas with relevance_decay < 0.1

INVARIANT: 
  assumptions.size <= 5
  active_subgoals <= 7
  
IF violation:
  collapse_lowest_priority_subgoal()
```

## Execution Trace Examples

### Example 1: Inequality with Domain Constraints

**INPUT:**

```
Prove: For all x in R with x > 0, show (x + 1/x) >= 2
```

**TRACE:**

```
[INIT STATE]
goal: for all x>0: x + 1/x >= 2
assumptions: []
proven_lemmas: {}
complexity: 5 nodes
difficulty_estimate: 0.4*1 + 0.3*1 + 0.2*2 + 0.1*1 = 0.81

[STRATEGY SELECT]
pattern_match_score(AM-GM_inequality, goal) = 0.9  // recognizes a+b form
pattern_match_score(direct_algebra, goal) = 0.6
score(AM-GM) = 0.4*0.9 + 0.3*0.85 + 0.2*(-0.1) + 0.1*0 = 0.595
score(direct) = 0.4*0.6 + 0.3*0.70 + 0.2*(-0.2) + 0.1*0 = 0.410
SELECTED: AM-GM_inequality

[STEP 1]
ACTION: Apply AM-GM: (a+b)/2 >= sqrt(ab) for a,b > 0
INSTANTIATE: a=x, b=1/x
CHECK: x > 0? YES (in constraints)
CHECK: 1/x > 0? NEED_PROOF

[STEP 1.1 - SUBGOAL]
goal: 1/x > 0 given x > 0
proven: division_preserves_sign(positive, positive) -> positive
RESULT: 1/x > 0 ✓
proven_lemmas += {1/x > 0 for x>0}

[STEP 2]
APPLY: (x + 1/x)/2 >= sqrt(x * 1/x)
SIMPLIFY: sqrt(x * 1/x) = sqrt(1) = 1
RESULT: (x + 1/x)/2 >= 1

[STEP 3]
MULTIPLY both sides by 2:
CHECK: 2 > 0? YES
RESULT: x + 1/x >= 2

[VALIDATION]
edge_cases_check:
  x -> 0+: LHS -> +inf ✓
  x -> +inf: LHS -> +inf ✓
  x = 1: LHS = 2 ✓ (equality case)

logic_chain: 
  x>0 -> 1/x>0 -> AM-GM applicable -> conclusion
  NO GAPS ✓

[FINAL STATE]
steps_taken: 3
complexity_growth: 1.2
confidence: sigmoid(2*1 - 1*0 - 0.5*1.2 - 1.5*0) = 0.79
PROOF COMPLETE
```

**OUTPUT:**

```
CLAIM: For all x > 0: x + 1/x >= 2

PROOF:
Let x > 0.

Since x > 0, we have 1/x > 0 by preservation of sign in division.

Applying AM-GM inequality with a = x and b = 1/x:
  (x + 1/x)/2 >= sqrt(x * 1/x) = sqrt(1) = 1

Multiplying both sides by 2:
  x + 1/x >= 2

Equality holds when x = 1/x, i.e., x = 1. QED
```

### Example 2: Combinatorial Induction with Branching

**INPUT:**

```
Prove: sum(k=1 to n) k^2 = n(n+1)(2n+1)/6 for all n in N
```

**TRACE:**

```
[INIT STATE]
goal: for all n in N: sum(k=1 to n) k^2 = n(n+1)(2n+1)/6
difficulty_estimate: 0.4*1 + 0.3*1 + 0.2*3 + 0.1*0 = 1.3
has_recursive_structure: TRUE (sum notation)

[STRATEGY SELECT]
pattern_match_score(induction, goal) = 1.0  // perfect match
score(induction) = 0.4*1.0 + 0.3*0.9 + 0.2*(-0.3) + 0.1*0.2 = 0.71
SELECTED: induction_proof

[INDUCTION SETUP]
CREATE subgoals:
  sg1: base_case(n=1), priority=0.9, budget=5
  sg2: inductive_step, priority=1.0, budget=15

[SUBGOAL 1: BASE CASE]
goal: 1^2 = 1(1+1)(2*1+1)/6
COMPUTE LHS: 1^2 = 1
COMPUTE RHS: 1*2*3/6 = 6/6 = 1
CHECK: 1 = 1 ✓
proven_lemmas += {P(1)}
steps_used: 2

[SUBGOAL 2: INDUCTIVE STEP]
goal: P(n) -> P(n+1)
assumptions: [sum(k=1 to n) k^2 = n(n+1)(2n+1)/6]  // IH

[STEP 2.1]
EXPAND: sum(k=1 to n+1) k^2
  = (sum(k=1 to n) k^2) + (n+1)^2
  
[STEP 2.2]
SUBSTITUTE inductive hypothesis:
  = n(n+1)(2n+1)/6 + (n+1)^2

[STEP 2.3]
FACTOR (n+1):
  = (n+1)[n(2n+1)/6 + (n+1)]
complexity_growth: 8/5 = 1.6

[STEP 2.4]
SIMPLIFY bracket:
  n(2n+1)/6 + (n+1) 
  = [n(2n+1) + 6(n+1)]/6
  = [2n² + n + 6n + 6]/6
  = [2n² + 7n + 6]/6

[STEP 2.5]
FACTOR numerator:
  2n² + 7n + 6 = (n+2)(2n+3)
CHECK factorization:
  (n+2)(2n+3) = 2n² + 3n + 4n + 6 = 2n² + 7n + 6 ✓

[STEP 2.6]
SUBSTITUTE back:
  (n+1)(n+2)(2n+3)/6

[STEP 2.7]
VERIFY this equals target:
  Target: (n+1)[(n+1)+1][2(n+1)+1]/6
        = (n+1)(n+2)(2n+3)/6 ✓

[VALIDATION]
induction_structure_check:
  - Base case proven: P(1) ✓
  - Inductive step proven: P(n)->P(n+1) ✓
  - Domain: N (discrete, well-ordered) ✓
  
edge_cases:
  n=2: sum k^2=1+4=5, RHS from formula = 2(2+1)(2*2+1)/6 = 2*3*5/6 = 30/6 = 5 ✓
  n=3: sum k^2=1+4+9=14, RHS from formula = 3(3+1)(2*3+1)/6 = 3*4*7/6 = 84/6 = 14 ✓

[FINAL STATE]
steps_taken: 9
subgoals_completed: 2/2
confidence: sigmoid(2*2 - 1*1 - 0.5*1.6 - 1.5*0) = 0.82
PROOF COMPLETE
```

**OUTPUT:**

```
CLAIM: For all n in N: sum(k=1 to n) k^2 = n(n+1)(2n+1)/6

PROOF BY INDUCTION:

Base case (n=1):
  LHS = 1^2 = 1
  RHS = 1*2*3/6 = 1
  Therefore P(1) holds.

Inductive step:
  Assume P(n): sum(k=1 to n) k^2 = n(n+1)(2n+1)/6
  
  Prove P(n+1):
    sum(k=1 to n+1) k^2 
    = (sum(k=1 to n) k^2) + (n+1)^2
    = n(n+1)(2n+1)/6 + (n+1)^2          [by IH]
    = (n+1)[n(2n+1)/6 + (n+1)]         [factor (n+1)]
    = (n+1)[n(2n+1) + 6(n+1)]/6        [common denominator]
    = (n+1)(2n² + 7n + 6)/6            [expand]
    = (n+1)(n+2)(2n+3)/6               [factor]
    = (n+1)[(n+1)+1][2(n+1)+1]/6       [rewrite]
  
  Therefore P(n+1) holds.

By induction, the formula holds for all n in N. QED
```

## Operational Parameters

```
DEFAULT_CONFIG = {
  max_steps: 50,
  max_subgoals: 7,
  max_assumptions: 5,
  context_budget: 8000,
  
  backtrack_threshold: 5,  // steps without progress
  complexity_alarm: 3.0,   // growth factor
  
  weights: {
    pattern_match: 0.4,
    success_rate: 0.3,
    complexity: -0.2,
    novelty: 0.1
  },
  
  relevance_decay_lambda: 0.1,
  confidence_threshold: 0.5,
  
  rigor_level: 2  // 0=exploratory, 1=standard, 2=rigorous, 3=formal
}
```

## Production Specification v1.0

### SECTION 1: CORE TYPE SYSTEM

```javascript
// #1, #10: Canonical AST with unambiguous semantics
Type =
  | Real
  | Integer
  | Boolean
  | Function(input: Type, output: Type)
  | Product(types: List[Type])

Domain =
  | Reals
  | PositiveReals
  | Integers
  | Naturals
  | Interval(lower: Bound, upper: Bound)
  | Finite(elements: Set[Value])

Bound = Open(Value) | Closed(Value) | Unbounded

Term =
  | Var(name: String, type: Type)
  | Const(value: Value, type: Type)
  | App(function: Term, argument: Term)
  | Lambda(param: Variable, body: Term)

Formula =
  | Atom(relation: Relation, terms: List[Term])
  | Not(formula: Formula)
  | And(left: Formula, right: Formula)
  | Or(left: Formula, right: Formula)
  | Implies(premise: Formula, conclusion: Formula)
  | Forall(variable: Variable, body: Formula)
  | Exists(variable: Variable, body: Formula)

Relation =
  | Eq | Neq | Lt | Leq | Gt | Geq
  | Custom(name: String, arity: Int)

AST =
  | TermNode(term: Term)
  | FormulaNode(formula: Formula)

// Canonical form rules
normalize(ast: AST) -> AST:
  MATCH ast:
    | FormulaNode(Not(Not(phi))): normalize(FormulaNode(phi))
    | FormulaNode(And(phi, psi)): And(normalize(phi), normalize(psi))
    | FormulaNode(Or(phi, psi)): Or(normalize(phi), normalize(psi))
    | TermNode(App(Lambda(x, body), arg)): substitute(body, x, arg)
    | _: ast

// #1: No implicit shortcuts allowed
INVARIANT: for all ast: AST. is_canonical(ast)
  where is_canonical checks:
    - No nested double negations
    - Variables renamed to canonical form (x0, x1, ...)
    - Terms in normal form (no unevaluated beta-redexes)
```

### SECTION 2: BINDING & SUBSTITUTION

```javascript
// #2: apply_bindings as total function
Substitution = Map[Variable, Term]

apply_bindings(formula: Formula, sigma: Substitution) -> Formula:
  MATCH formula:
    | Atom(rel, terms):
        Atom(rel, [substitute_term(t, sigma) for t in terms])
    
    | Not(phi):
        Not(apply_bindings(phi, sigma))
    | And(phi, psi):
        And(apply_bindings(phi, sigma), apply_bindings(psi, sigma))
    | Or(phi, psi):
        Or(apply_bindings(phi, sigma), apply_bindings(psi, sigma))
    | Implies(phi, psi):
        Implies(apply_bindings(phi, sigma), apply_bindings(psi, sigma))
    | Forall(x, body):
        Forall(x, apply_bindings(body, sigma.remove(x)))
    | Exists(x, body):
        Exists(x, apply_bindings(body, sigma.remove(x)))
```
