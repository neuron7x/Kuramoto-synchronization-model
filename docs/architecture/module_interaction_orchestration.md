# Module Interaction Orchestration Architecture

## Overview

This document describes the module interaction orchestration architecture that implements the requirement: **"Оркеструвати - Керувати послідовністю взаємодії модулів"** (Orchestrate - Manage the sequence of module interactions).

## Problem Statement

The TradePulse platform consists of multiple modules that need to interact in a specific sequence:

1. **Data Ingestion** → Load market data
2. **Validation** → Ensure data quality
3. **Feature Engineering** → Extract signals and indicators
4. **Signal Generation** → Generate trading signals
5. **Neuromodulation** → Apply adaptive controls
6. **Risk Assessment** → Evaluate risk
7. **Execution** → Execute trades
8. **Post-Execution** → Handle confirmations and feedback

Previously, these interactions were managed ad-hoc or hardcoded into specific components. This made it difficult to:
- Add new modules without modifying existing code
- Reorder module execution for experimentation
- Understand dependencies between modules
- Detect circular dependencies
- Enable/disable modules dynamically
- Handle errors gracefully while preserving partial results

## Solution: ModuleInteractionOrchestrator

The `ModuleInteractionOrchestrator` provides a centralized, declarative way to define and manage module interactions.

### Architecture Diagram

```
┌────────────────────────────────────────────────────────────────┐
│                ModuleInteractionOrchestrator                   │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │              Module Registry                             │ │
│  │  • Register/Remove modules                               │ │
│  │  • Enable/Disable modules                                │ │
│  │  • Query module information                              │ │
│  └──────────────────────────────────────────────────────────┘ │
│                            ↓                                   │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │          Dependency Resolution Engine                    │ │
│  │  • Topological Sort (Kahn's Algorithm)                   │ │
│  │  • Circular Dependency Detection                         │ │
│  │  • Priority-based Ordering                               │ │
│  └──────────────────────────────────────────────────────────┘ │
│                            ↓                                   │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │              Phase-Based Organizer                       │ │
│  │  INGESTION → VALIDATION → FEATURE_ENGINEERING →          │ │
│  │  SIGNAL_GENERATION → NEUROMODULATION →                   │ │
│  │  RISK_ASSESSMENT → EXECUTION → POST_EXECUTION            │ │
│  └──────────────────────────────────────────────────────────┘ │
│                            ↓                                   │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │              Execution Engine                            │ │
│  │  • Sequential execution                                  │ │
│  │  • Context accumulation                                  │ │
│  │  • Error handling & rollback                             │ │
│  └──────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
                            ↓
              ┌─────────────────────────────┐
              │    ExecutionContext         │
              │  • Shared data              │
              │  • Metadata                 │
              │  • Error tracking           │
              └─────────────────────────────┘
```

### Key Components

#### 1. ModuleDefinition

Defines a single module in the orchestration:

```python
@dataclass
class ModuleDefinition:
    name: str                    # Unique identifier
    phase: ModulePhase           # Execution phase
    dependencies: List[str]      # Required modules
    handler: Callable            # Module logic
    enabled: bool = True         # Active flag
    priority: int = 0            # Phase-local priority
```

#### 2. ModulePhase

Standard phases for module organization:

```python
class ModulePhase(str, Enum):
    INGESTION = "ingestion"
    VALIDATION = "validation"
    FEATURE_ENGINEERING = "feature_engineering"
    SIGNAL_GENERATION = "signal_generation"
    NEUROMODULATION = "neuromodulation"
    RISK_ASSESSMENT = "risk_assessment"
    EXECUTION = "execution"
    POST_EXECUTION = "post_execution"
```

#### 3. ExecutionContext

Shared context for data exchange:

```python
@dataclass
class ExecutionContext:
    data: Dict[str, Any]           # Module outputs
    metadata: Dict[str, Any]       # Execution info
    errors: List[str]              # Error log
```

#### 4. ModuleInteractionOrchestrator

Main orchestration engine:

```python
class ModuleInteractionOrchestrator:
    def register_module(self, module: ModuleDefinition)
    def build_execution_sequence(self) -> List[str]
    def execute(self, initial_context=None) -> ExecutionContext
    def disable_module(self, name: str)
    def enable_module(self, name: str)
```

## Integration with Existing Architecture

### Relationship with Other Orchestrators

TradePulse has multiple orchestrators, each serving a distinct purpose:

| Orchestrator | Purpose | Scope |
|--------------|---------|-------|
| **ModuleInteractionOrchestrator** | Sequence module interactions | Pipeline coordination |
| **TradePulseOrchestrator** | High-level system façade | End-to-end workflows |
| **ModeOrchestrator** | Trading mode state machine | Mode transitions |
| **StrategyOrchestrator** | Parallel strategy evaluation | Strategy concurrency |

These orchestrators are **complementary** and can be used together:

```python
# System-level orchestrator
system = build_tradepulse_system()
tp_orchestrator = TradePulseOrchestrator(system)

# Module sequence orchestrator
module_orchestrator = ModuleInteractionOrchestrator()

# Define pipeline using module orchestrator
def ingestion_module(context_data):
    source = context_data.get("data_source")
    return {"market_data": tp_orchestrator.ingest_market_data(source)}

def feature_module(context_data):
    market_data = context_data.get("market_data")
    return {"features": tp_orchestrator.build_features(market_data)}

# Register modules
module_orchestrator.register_module(
    ModuleDefinition(name="ingest", phase=ModulePhase.INGESTION, 
                    handler=ingestion_module)
)

module_orchestrator.register_module(
    ModuleDefinition(name="features", phase=ModulePhase.FEATURE_ENGINEERING,
                    handler=feature_module, dependencies=["ingest"])
)

# Execute
context = module_orchestrator.execute()
```

## Design Decisions

### 1. Topological Sort for Dependency Resolution

**Choice**: Use Kahn's algorithm for topological sorting.

**Rationale**:
- O(V + E) time complexity
- Detects cycles naturally
- Works well with priority ordering
- Simple to understand and debug

### 2. Phase-Based Organization

**Choice**: Organize modules into predefined phases.

**Rationale**:
- Provides logical structure
- Makes system easier to understand
- Enables phase-level operations (list, filter, disable)
- Aligns with trading pipeline stages

### 3. Stop-on-Error Execution

**Choice**: Stop execution at first error, preserve partial results.

**Rationale**:
- Trading systems must fail fast
- Partial results useful for debugging
- Prevents cascading failures
- Maintains data consistency

### 4. Explicit Dependencies

**Choice**: Require explicit dependency declarations.

**Rationale**:
- Makes dependencies visible and auditable
- Enables validation and cycle detection
- Supports parallel optimization (future)
- Prevents implicit coupling

### 5. Dynamic Enable/Disable

**Choice**: Allow runtime enable/disable without removing modules.

**Rationale**:
- Supports A/B testing
- Enables feature flags
- Facilitates gradual rollouts
- Allows quick rollbacks

## Usage Patterns

### Pattern 1: Linear Pipeline

Sequential module execution:

```python
orchestrator.register_module(ModuleDefinition("A", phase=INGESTION, ...))
orchestrator.register_module(ModuleDefinition("B", phase=VALIDATION, 
                                             dependencies=["A"], ...))
orchestrator.register_module(ModuleDefinition("C", phase=FEATURES, 
                                             dependencies=["B"], ...))
```

Execution order: A → B → C

### Pattern 2: Parallel Fan-Out

Multiple modules depending on one:

```python
orchestrator.register_module(ModuleDefinition("data", phase=INGESTION, ...))
orchestrator.register_module(ModuleDefinition("sma", phase=FEATURES, 
                                             dependencies=["data"], ...))
orchestrator.register_module(ModuleDefinition("rsi", phase=FEATURES, 
                                             dependencies=["data"], ...))
orchestrator.register_module(ModuleDefinition("macd", phase=FEATURES, 
                                             dependencies=["data"], ...))
```

Execution order: data → (sma, rsi, macd in parallel potential)

### Pattern 3: Fan-In Aggregation

Multiple modules feeding into one:

```python
orchestrator.register_module(ModuleDefinition("sma", phase=FEATURES, ...))
orchestrator.register_module(ModuleDefinition("rsi", phase=FEATURES, ...))
orchestrator.register_module(ModuleDefinition("signal", phase=SIGNAL_GENERATION,
                                             dependencies=["sma", "rsi"], ...))
```

Execution order: (sma, rsi) → signal

### Pattern 4: Complex DAG

Diamond dependency pattern:

```python
# A
# ├─> B
# │   └─> D
# └─> C
#     └─> D
```

All dependencies automatically resolved.

## Performance Characteristics

| Operation | Time Complexity | Space Complexity |
|-----------|----------------|------------------|
| Register Module | O(1) | O(1) |
| Build Sequence | O(V + E) | O(V + E) |
| Execute | O(V) | O(V) |
| Disable/Enable | O(1) | O(1) |

Where:
- V = number of modules
- E = number of dependencies

## Error Handling

### Error Propagation

1. Module handler raises exception
2. Exception caught by orchestrator
3. Error logged in context
4. Execution stops immediately
5. Partial results preserved in context

```python
context = orchestrator.execute()

if context.has_error():
    # Access error information
    for error in context.errors:
        logger.error(error)
    
    # Check what succeeded
    succeeded = context.metadata.get("modules_executed", [])
    
    # Access partial results
    partial_data = context.data
```

## Testing Strategy

### Unit Tests
- Module registration/removal
- Dependency resolution
- Circular dependency detection
- Phase-based filtering
- Priority ordering
- Error handling

### Integration Tests
- Full pipeline execution
- Parallel module scenarios
- Dynamic enable/disable
- Error propagation
- Context accumulation

### Example Test

```python
def test_dependency_ordering():
    orch = ModuleInteractionOrchestrator()
    
    orch.register_module(
        ModuleDefinition("B", phase=INGESTION, dependencies=["A"])
    )
    orch.register_module(
        ModuleDefinition("A", phase=INGESTION)
    )
    
    sequence = orch.get_sequence()
    assert sequence.index("A") < sequence.index("B")
```

## Future Enhancements

### 1. Parallel Execution
Execute independent modules concurrently using thread pool or async/await.

### 2. Conditional Execution
Skip modules based on runtime conditions:
```python
ModuleDefinition(..., condition=lambda ctx: ctx.get("mode") == "live")
```

### 3. Retry Logic
Automatic retry for transient failures:
```python
ModuleDefinition(..., max_retries=3, retry_delay=1.0)
```

### 4. Performance Metrics
Track execution time per module:
```python
context.metadata["timings"] = {"module1": 0.5, "module2": 1.2}
```

### 5. Visualization
Generate execution graph diagrams:
```python
orchestrator.visualize_dependencies(output="graph.png")
```

## Conclusion

The `ModuleInteractionOrchestrator` provides a robust, flexible solution for managing module interactions in the TradePulse trading system. It ensures correct execution order, detects configuration errors, and enables dynamic control—all while maintaining clear, auditable dependencies between modules.

## References

- Implementation: `core/orchestrator/interaction_sequencer.py`
- Documentation: `docs/MODULE_INTERACTION_ORCHESTRATOR.md`
- Tests: `tests/core/orchestrator/test_interaction_sequencer.py`
- Demo: `examples/module_interaction_orchestrator_demo.py`
- Integration: `tests/integration/test_module_interaction_orchestrator.py`
