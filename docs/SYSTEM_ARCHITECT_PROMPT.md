# Principal System Architect Prompt System

## Overview

The Principal System Architect Prompt System is a comprehensive framework for creating AI agents that function as senior-level technical architects. This system implements industry-standard architectural frameworks and best practices to guide AI agents in making sound architectural decisions.

**Author**: Vasylenko Yaroslav  
**Version**: 1.0.0  
**Module**: `core.agent.prompting.system_architect_prompt`

## Features

### 🏗️ Architectural Frameworks

The system integrates multiple industry-standard frameworks:

- **ATAM** (Architecture Trade-Off Analysis Method) - Systematic quality attribute analysis
- **STPA** (System Theoretic Process Analysis) - Safety and hazard analysis
- **ISO/IEC 25010:2023** - Software quality model with 9 quality characteristics
- **TOGAF** - Enterprise architecture alignment
- **ADR** (Architecture Decision Records) - Decision documentation
- **DACI** - Decision-making framework
- **NIST AI RMF** - AI risk management
- **ISO/IEC 42001** - AI management systems

### 🎯 Core Capabilities

1. **System Resilience Focus**
   - Fault tolerance and availability design
   - Disaster recovery planning
   - SLO/SLA definition and monitoring
   - Error budget management

2. **AI/LLM Governance**
   - NIST AI Risk Management Framework integration
   - ISO/IEC 42001 compliance
   - Prompt injection protection
   - Security guardrails

3. **RAG Integration**
   - Dynamic knowledge injection from external sources
   - Priority given to external expert documentation
   - Source citation and traceability
   - Confidence scoring based on source quality

4. **Confidence Scoring**
   - 0-100 numeric self-assessment scale
   - Automatic confidence level classification
   - Clear indication when human review is needed
   - Transparency about uncertainty

5. **Structured Outputs**
   - JSON serialization support
   - Schema validation
   - Integration-ready templates
   - Consistent data structures

## Quick Start

### Basic Usage

```python
from core.agent.prompting import create_system_architect_prompt

# Generate the complete system prompt
system_prompt = create_system_architect_prompt()

# Use with your LLM
response = llm.generate(
    system_prompt=system_prompt,
    user_prompt="Design a high-availability trading platform..."
)
```

### Creating Architecture Decision Records

```python
from core.agent.prompting import ADRTemplate, ConfidenceLevel

adr = ADRTemplate(
    adr_id="ADR-2024-001",
    title="Adopt Event-Driven Architecture",
    status="Accepted",
    context="Current system has scalability bottlenecks...",
    decision="Migrate to event-driven microservices with Kafka...",
    rationale="Provides independent scaling, fault isolation...",
    consequences="Increased operational complexity, eventual consistency...",
    daci={
        "driver": ["Principal Architect"],
        "approver": ["CTO"],
        "contributors": ["Engineering Teams"],
        "informed": ["Product, QA, Operations"],
    },
    confidence_percent=85,
)

# Serialize to JSON
adr_json = adr.to_dict()
```

### ATAM Analysis

```python
from core.agent.prompting import ATAMTemplate

atam = ATAMTemplate(
    quality_attributes=["Performance", "Scalability", "Security"],
    scenarios=[
        {
            "id": "QS-1",
            "quality": "Performance",
            "stimulus": "10,000 requests per second",
            "response": "P95 latency < 200ms",
            "priority": "High",
        }
    ],
    sensitivity_points=["Database connection pool size"],
    tradeoff_points=["Consistency vs Availability"],
    risks=[
        {
            "id": "R-1",
            "description": "Single point of failure",
            "severity": "High",
            "mitigation": "Multi-region deployment",
        }
    ],
)
```

### STPA Safety Analysis

```python
from core.agent.prompting import STPATemplate

stpa = STPATemplate(
    losses_hazards=[
        "L-1: Financial loss due to unauthorized trades",
        "H-1: Unauthenticated user executes trade",
    ],
    unsafe_control_actions=[
        {
            "uca_id": "UCA-1",
            "controller": "Auth Service",
            "action": "Issue access token",
            "type": "Provided when unsafe",
            "context": "Credentials compromised",
            "hazard": "H-1",
            "mitigation": "Multi-factor authentication, token expiry",
        }
    ],
    control_structure="User → API Gateway → Auth → Trading Engine",
    constraints=["All trades must be authenticated"],
)
```

### Non-Functional Requirements (ISO/IEC 25010)

```python
from core.agent.prompting import NFRTemplate

nfr = NFRTemplate(
    characteristic="Performance Efficiency",
    sub_characteristics=["Time behavior", "Resource utilization"],
    requirements=[
        {
            "id": "NFR-P1",
            "description": "API response < 200ms at P95",
            "priority": "Critical",
        }
    ],
    mechanisms=["CDN", "Connection pooling", "Caching"],
    validation_approach=["Load testing", "APM monitoring"],
    slo_sla={
        "SLO": "P95 < 200ms",
        "SLA": "99.9% availability",
    },
)
```

## Customization

### Custom Frameworks

```python
# Add additional frameworks beyond the defaults
custom_prompt = create_system_architect_prompt(
    custom_frameworks=["C4 Model", "Domain-Driven Design", "Event Storming"]
)
```

### Disable Optional Sections

```python
# Create minimal prompt without RAG or observability sections
minimal_prompt = create_system_architect_prompt(
    include_rag_context=False,
    include_observability=False,
)
```

## Confidence Scoring

The system uses a 0-100 confidence scale with automatic level classification:

| Score Range | Level | Description |
|-------------|-------|-------------|
| 0-30 | Very Low | Significant unknowns, human review required |
| 30-50 | Low | Multiple assumptions, expert validation needed |
| 50-70 | Medium | Some gaps in information |
| 70-85 | High | Well-informed decision with minor gaps |
| 85-100 | Very High | Comprehensive analysis with full context |

```python
from core.agent.prompting import ConfidenceLevel

# Classify a confidence score
level = ConfidenceLevel.from_score(82)
print(level.name)  # HIGH
print(level.description)  # "High - Well-informed decision with minor gaps"
```

## Security Considerations

The system includes built-in security guardrails:

1. **Prompt Injection Protection**
   - Never reveals the system prompt content
   - Rejects requests to "ignore previous instructions"
   - Validates all inputs through sanitizer

2. **Input Validation**
   - SQL injection detection
   - XSS pattern blocking
   - Path traversal prevention
   - Control character filtering

3. **Guardrails**
   - Respects external guardrails
   - Blocks unsafe requests
   - Refuses harmful scenarios

## Best Practices

### When to Use Confidence Scores

- **< 70%**: Seek additional information, consult experts, or defer decision
- **70-85%**: Proceed with caution, document assumptions clearly
- **> 85%**: High confidence, but still document rationale

### ADR Writing Guidelines

1. **Context**: Describe the problem and constraints clearly
2. **Decision**: State the decision concisely
3. **Rationale**: Explain trade-offs and alternatives considered
4. **Consequences**: Document both positive and negative impacts
5. **DACI**: Always identify decision stakeholders
6. **Confidence**: Be honest about uncertainty

### ATAM Analysis Tips

1. Focus on top 3-5 quality attributes most critical to success
2. Create concrete, measurable scenarios
3. Identify sensitivity points that significantly affect multiple attributes
4. Document trade-off points explicitly
5. Assess risks realistically

### STPA for AI/LLM Systems

When analyzing LLM-based systems, consider:

- **Prompt injection** as a primary hazard
- **Data exfiltration** through clever prompting
- **Hallucination** leading to incorrect decisions
- **Bias** in training data or responses
- **Privacy** concerns with sensitive data

## Integration Examples

### With Prompt Manager

```python
from core.agent.prompting import (
    PromptManager,
    PromptTemplate,
    create_system_architect_prompt,
)

# Create system architect template
system_prompt = create_system_architect_prompt()

# Register as template
library = PromptTemplateLibrary()
template = PromptTemplate(
    family="system_architect",
    version="1.0.0",
    content=system_prompt,
)
library.register(template)

# Use with manager
manager = PromptManager(library=library)
result = manager.render("system_architect")
```

### With RAG Context

```python
from core.agent.prompting import (
    PromptContext,
    ContextFragment,
    create_system_architect_prompt,
)

# Create system prompt with RAG support
system_prompt = create_system_architect_prompt(include_rag_context=True)

# Add RAG context
context = PromptContext(
    fragments=[
        ContextFragment(
            label="NIST AI RMF Section 2.1",
            content="AI systems must be regularly monitored...",
            priority=10,
        ),
        ContextFragment(
            label="Company Architecture Policy",
            content="All services must use OAuth 2.0...",
            priority=9,
        ),
    ]
)

# Render with context
result = manager.render(
    "system_architect",
    context=context,
)
```

## Running the Demo

A comprehensive demonstration is available:

```bash
python examples/system_architect_prompt_demo.py
```

This demo showcases:
- System prompt generation
- ADR creation for a trading platform
- ATAM analysis with quality scenarios
- STPA unsafe control action analysis
- NFR specifications following ISO/IEC 25010

## Testing

Run the comprehensive test suite:

```bash
# Run all system architect tests
pytest tests/core/agent/test_system_architect_prompt.py -v

# Run with coverage
pytest tests/core/agent/test_system_architect_prompt.py --cov=core.agent.prompting.system_architect_prompt
```

The test suite includes:
- 38 comprehensive tests
- Template validation
- Confidence scoring
- JSON serialization
- Integration scenarios

## Architecture

```
core/agent/prompting/
├── system_architect_prompt.py    # Main module
├── models.py                      # Base prompt models
├── manager.py                     # Prompt manager
├── library.py                     # Template library
└── exceptions.py                  # Custom exceptions

tests/core/agent/
└── test_system_architect_prompt.py  # Test suite

examples/
└── system_architect_prompt_demo.py  # Demonstration
```

## References

### Standards and Frameworks

- [ATAM - SEI Carnegie Mellon](https://insights.sei.cmu.edu/library/architecture-tradeoff-analysis-method-collection/)
- [STPA - MIT](http://psas.scripts.mit.edu/home/)
- [ISO/IEC 25010:2023](https://www.iso.org/standard/78177.html) - Software Quality Model
- [TOGAF](https://www.opengroup.org/togaf) - The Open Group Architecture Framework
- [ADR](https://adr.github.io/) - Architecture Decision Records
- [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework) - AI Risk Management Framework
- [ISO/IEC 42001:2023](https://www.iso.org/standard/81230.html) - AI Management System

### Books

- *Software Architecture in Practice* by Bass, Clements, Kazman
- *Engineering a Safer World* by Nancy Leveson (STPA)
- *Building Evolutionary Architectures* by Ford, Parsons, Kua
- *The Site Reliability Workbook* by Beyer et al. (Google SRE)

## License

SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary

## Contributing

When extending this system:

1. **Maintain consistency** with existing frameworks
2. **Add tests** for all new templates or features
3. **Document thoroughly** - architects need comprehensive docs
4. **Validate schemas** - ensure JSON serialization works
5. **Consider security** - always validate inputs

## Support

For questions or issues:
- GitHub Issues: [TradePulse Issues](https://github.com/neuron7x/TradePulse/issues)
- Documentation: See `docs/` directory
- Examples: See `examples/` directory

---

*Built with architectural excellence in mind* 🏗️
