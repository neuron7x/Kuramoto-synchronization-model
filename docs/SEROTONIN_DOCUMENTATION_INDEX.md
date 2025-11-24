# Serotonin Controller Documentation Index

**Last Updated:** 2025-11-24  
**Status:** Current  
**Module Version:** v2.4.0

---

## Quick Navigation

| Document | Purpose | Audience |
|----------|---------|----------|
| [**Architecture Decision Record**](adr/0002-serotonin-controller-architecture.md) | Complete ADR with design rationale, trade-offs, and validation | Architects, Technical Leads |
| [**Bibliography**](SEROTONIN_BIBLIOGRAPHY.md) | Comprehensive academic references (44 sources, APA 7th Ed) | Researchers, Validators, Compliance |
| [**Future Iterations (UA)**](/SEROTONIN_FUTURE_ITERATIONS_UA.md) | Roadmap for optional enhancements (Ukrainian) | Product Managers, Developers |
| [**Source Code**](/src/tradepulse/core/neuro/serotonin/serotonin_controller.py) | Python implementation with inline citations | Developers, Code Reviewers |

---

## Document Overview

### 1. Architecture Decision Record (ADR-0002)
**Location:** `docs/adr/0002-serotonin-controller-architecture.md`

**Contents:**
- Business context and requirements
- Architectural decision with 5 key components
- Theoretical foundations with academic citations
- Trade-off analysis (Simple Threshold vs Hysteretic vs PID)
- STPA safety analysis with hazard identification
- NFR mechanisms per ISO/IEC 25010:2023
- Implementation roadmap and validation results

**Key Additions (2025-11-24):**
- ✅ 44 academic citations added to References section
- ✅ Inline citations in Decision section (neuroscience foundations)
- ✅ Inline citations in Rationale section (computational models)
- ✅ STPA methodology references (Leveson 2011, 2018)
- ✅ Technical standards (NIST AI RMF, ISO/IEC 25010:2023)

**When to Use:**
- Making architectural changes to the controller
- Justifying design decisions to stakeholders
- Conducting architecture reviews
- Onboarding senior engineers

---

### 2. Comprehensive Bibliography
**Location:** `docs/SEROTONIN_BIBLIOGRAPHY.md`

**Contents:**
- 44 peer-reviewed sources organized by domain
- Full APA 7th Edition citations (USA 2025 standard)
- DOI/URL links for all sources
- Key findings and relevance for each source
- Citation counts and validation status

**Research Domains Covered:**
1. Neuroscience and Serotonin Research (11 sources)
2. Tonic and Phasic Neuromodulation (4 sources)
3. Neuromodulation and Decision-Making (3 sources)
4. Computational Models and Control Theory (3 sources)
5. Hysteresis and Nonlinear Dynamics (3 sources)
6. Desensitization and Adaptation Mechanisms (3 sources)
7. Risk Aversion and Behavioral Inhibition (2 sources)
8. Technical Standards and Frameworks (3 sources)
9. Safety Analysis and STPA (3 sources)
10. Time Series Analysis and Signal Processing (2 sources)
11. Performance Optimization and Real-Time Systems (2 sources)
12. Software Architecture and Quality Attributes (2 sources)
13. Financial Risk Management (3 sources)

**When to Use:**
- Validating scientific foundations
- Writing research papers or technical reports
- Regulatory compliance documentation
- Literature review for enhancements
- Teaching/training on neuromodulation

---

### 3. Future Iterations Plan (Ukrainian)
**Location:** `SEROTONIN_FUTURE_ITERATIONS_UA.md`

**Contents:**
- Current status confirmation (v2.4.0 = 100% complete)
- 9 optional enhancement proposals for future versions
- Priority rankings and effort estimates
- Risk/benefit analysis for each proposal

**Proposed Enhancements:**
- v2.5.0: Configurable hysteresis, extended persistence, deeper telemetry
- v2.6.0: Pattern recognition, adaptive threshold learning
- v2.7.0: Multi-neuromodulator integration, A/B testing framework

**Recent Updates (2025-11-24):**
- ✅ Added links to new bibliography
- ✅ Referenced ADR with theoretical foundations

**When to Use:**
- Planning future development sprints
- Prioritizing feature requests
- Evaluating enhancement proposals

---

### 4. Source Code Implementation
**Location:** `src/tradepulse/core/neuro/serotonin/serotonin_controller.py`

**Contents:**
- Complete Python implementation (546 lines)
- Comprehensive module-level docstring with 15 key references
- Enhanced class docstring with biological motivation
- Inline code comments referencing specific papers

**Key Components:**
- `SerotoninConfig`: Frozen dataclass for configuration
- `SerotoninController`: Main controller class with:
  - Tonic/phasic EMA filtering
  - Hysteretic state machine
  - Desensitization mechanism
  - Cooldown logic
  - Performance tracking
  - State validation utilities

**Recent Enhancements (2025-11-24):**
- ✅ Extended module docstring with theoretical foundation
- ✅ Added 15 inline citations to key papers
- ✅ Enhanced class docstring with neuroscience motivation
- ✅ Added practical examples to docstring

**When to Use:**
- Implementing code changes
- Conducting code reviews
- Understanding implementation details
- Debugging controller behavior

---

## Neuroscience Foundations

### Core Principles

The serotonin controller is grounded in three decades of neuroscience research:

1. **Opponent Process Theory** (Daw et al., 2002; Cools et al., 2011)
   - Serotonin opposes dopamine in decision-making
   - Promotes behavioral inhibition vs. dopamine's activation
   - Critical for adaptive risk management

2. **Dual Timescale Dynamics** (Cohen et al., 2015; Matias et al., 2017)
   - Tonic: slow baseline modulation (minutes to hours)
   - Phasic: rapid transient responses (seconds)
   - Both are necessary for flexible behavior

3. **Risk Aversion & Patience** (Schweighofer et al., 2008; Miyazaki et al., 2011)
   - Elevated serotonin promotes waiting for delayed rewards
   - Serotonin depletion increases impulsivity and risk-seeking
   - Direct relevance to trading under stress

4. **Homeostatic Adaptation** (Roth, 2011; Turrigiano, 2011)
   - Chronic stimulation causes desensitization
   - Prevents perpetual hold states during extended stress
   - Maintains system responsiveness

### Key Research Papers

**Must-Read Papers:**
1. Cools et al. (2011) - Serotonin and dopamine unification
2. Dayan & Huys (2009) - Serotonin in affective control
3. Cohen et al. (2015) - Multiple timescale signaling
4. Matias et al. (2017) - Cognitive flexibility patterns

**Supporting Evidence:**
5. Daw et al. (2002) - Opponent interactions model
6. Crockett et al. (2009) - Punishment-induced inhibition
7. Schweighofer et al. (2008) - Delayed reward discounting
8. Roth (2011) - Receptor desensitization

See [SEROTONIN_BIBLIOGRAPHY.md](SEROTONIN_BIBLIOGRAPHY.md) for complete citations.

---

## Technical Standards Compliance

### Standards Referenced

1. **NIST AI RMF 1.0** (2023)
   - DOI: 10.6028/NIST.AI.100-1
   - Framework for AI risk management
   - Applied to trading system governance

2. **ISO/IEC 25010:2023**
   - Product quality model for software systems
   - Defines 8 quality characteristics
   - Used for NFR analysis in ADR

3. **IEC 61508**
   - Functional safety standard
   - Informs safety-critical system design
   - Referenced in risk management approach

### Safety Analysis Methodology

**STPA (System-Theoretic Process Analysis)**
- Source: Leveson (2011, 2018)
- Identifies unsafe control actions
- Applied to hazard analysis in ADR-0002
- Results documented in UCA table

---

## Testing and Validation

### Test Files

1. `tests/unit/tradepulse/core/neuro/serotonin/test_serotonin_controller_simplified.py`
   - Unit tests for core functionality
   - Hysteresis behavior validation
   - Cooldown timing tests

2. `tests/core/neuro/serotonin/test_serotonin_controller.py`
   - Integration tests
   - End-to-end workflows

3. `core/neuro/tests/test_serotonin_controller.py`
   - Additional test coverage

### Validation Status

- ✅ Unit test coverage: 95%+
- ✅ Property-based tests: Invariant checking
- ✅ Performance tests: < 100μs step latency verified
- ✅ Integration tests: End-to-end validation complete

---

## Usage Examples

### Basic Usage

```python
from tradepulse.core.neuro.serotonin.serotonin_controller import SerotoninController

# Initialize controller
controller = SerotoninController("configs/serotonin.yaml")

# Process market signals
result = controller.step(
    stress=0.5,      # Market stress indicator
    drawdown=0.1,    # Portfolio drawdown
    novelty=0.0      # Regime change signal
)

# Check if trading should be paused
if result['hold']:
    print("Trading paused due to elevated stress")
    print(f"Recovery time estimate: {controller.estimate_recovery_time()} ticks")
else:
    print(f"Position size multiplier: {controller.get_position_size_multiplier():.2f}")
```

### Advanced Usage

See `examples/serotonin_practical_integration.py` for complete integration example.

---

## Maintenance Schedule

| Task | Frequency | Next Due |
|------|-----------|----------|
| Bibliography review | Quarterly | 2026-02-24 |
| URL/DOI validation | Semi-annually | 2026-05-24 |
| ADR review | Quarterly | 2026-02-17 |
| Code documentation sync | Ad-hoc | As needed |

---

## Contributing

### Adding New Citations

When adding functionality based on new research:

1. Add full citation to `docs/SEROTONIN_BIBLIOGRAPHY.md`
   - Follow APA 7th Edition format
   - Include DOI/URL
   - Add key findings and relevance

2. Add inline citation in `docs/adr/0002-serotonin-controller-architecture.md`
   - Reference in relevant section
   - Explain connection to design decision

3. Add citation to code if implementing specific algorithm
   - Module docstring for theoretical foundation
   - Inline comment for specific technique

4. Update this index document if adding new documentation

### Citation Format (APA 7th Edition)

**Journal Article:**
```
Author, A. A., Author, B. B., & Author, C. C. (Year). Title of article. 
    Journal Name, Volume(Issue), pages. https://doi.org/XX.XXXX/XXXX
```

**Book:**
```
Author, A. A. (Year). Title of book (Edition). Publisher. 
    https://doi.org/XX.XXXX/XXXX
```

**Technical Report:**
```
Organization. (Year). Title of report. Publisher. 
    https://doi.org/XX.XXXX/XXXX
```

---

## Contact & Support

- **Repository:** https://github.com/neuron7x/TradePulse
- **Issues:** https://github.com/neuron7x/TradePulse/issues
- **Documentation:** https://github.com/neuron7x/TradePulse/tree/main/docs

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-11-24 | Initial documentation index with bibliography links |

---

**Document Classification:** Technical Documentation  
**Access Level:** Public  
**Maintained By:** TradePulse Development Team
