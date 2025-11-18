"""Demonstration of the Principal System Architect prompt system.

This example shows how to use the system architect prompt templates
to create comprehensive architectural documentation including:
- Architecture Decision Records (ADR)
- ATAM (Architecture Trade-Off Analysis)
- STPA (System Theoretic Process Analysis)
- Non-Functional Requirements (NFR) following ISO/IEC 25010

Run this directly:
    python examples/system_architect_prompt_demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add project root to path for direct execution
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.agent.prompting.system_architect_prompt import (
    ADRTemplate,
    ATAMTemplate,
    ArchitecturalFramework,
    ConfidenceLevel,
    NFRTemplate,
    STPATemplate,
    create_system_architect_prompt,
)


def demo_system_prompt_creation() -> None:
    """Demonstrate creating the system architect prompt."""
    print("=" * 80)
    print("SYSTEM ARCHITECT PROMPT GENERATION")
    print("=" * 80)

    # Create full system prompt
    full_prompt = create_system_architect_prompt()
    print(f"\n✓ Generated system prompt: {len(full_prompt)} characters")
    print(f"\nFirst 500 characters:\n{full_prompt[:500]}...")

    # Create customized prompt without RAG
    custom_prompt = create_system_architect_prompt(
        include_rag_context=False,
        custom_frameworks=["C4 Model", "Event Storming"],
    )
    print(f"\n✓ Generated custom prompt: {len(custom_prompt)} characters")

    # Show available frameworks
    print("\n✓ Available Architectural Frameworks:")
    for framework in ArchitecturalFramework:
        print(f"  - {framework.name}: {framework.value}")


def demo_adr_creation() -> None:
    """Demonstrate creating an Architecture Decision Record."""
    print("\n" + "=" * 80)
    print("ARCHITECTURE DECISION RECORD (ADR)")
    print("=" * 80)

    adr = ADRTemplate(
        adr_id="ADR-2024-001",
        title="Adopt Event-Driven Architecture for Order Processing",
        status="Accepted",
        context="""
Current monolithic architecture struggles with:
- Peak load during market hours (10,000+ orders/sec)
- Tight coupling between order validation, execution, and settlement
- Difficult to scale individual components independently
- Long deployment cycles affecting all services

Business drivers:
- Need to support 5x traffic growth in next 6 months
- Reduce time-to-market for new trading features
- Improve system resilience and fault isolation
        """.strip(),
        decision="""
Migrate to event-driven microservices architecture with:
- Apache Kafka as event backbone (at-least-once delivery)
- Command Query Responsibility Segregation (CQRS) for order state
- Event Sourcing for audit trail and replays
- Saga pattern for distributed transactions
        """.strip(),
        rationale="""
**Pros**:
- Independent scaling: can scale order validation separately from execution
- Fault isolation: failure in settlement doesn't block order intake
- Temporal decoupling: services can be offline and catch up via event replay
- Audit trail: complete event history for regulatory compliance

**Cons**:
- Eventual consistency requires careful UX design
- Increased operational complexity (monitoring, debugging distributed flows)
- Higher infrastructure costs (Kafka cluster, increased compute)

**Trade-offs**:
- Latency: slight increase (50ms) due to async processing
- vs Scalability: 10x improvement in throughput capacity
- Complexity: +40% operational overhead
- vs Resilience: 3x improvement in MTTR

**Alternatives Considered**:
1. Vertical scaling monolith: rejected due to cost and single point of failure
2. Synchronous microservices: rejected due to cascading failure risk
3. Serverless functions: rejected due to cold start latency requirements
        """.strip(),
        consequences="""
**Positive**:
- Throughput SLO: 50,000 orders/sec (5x current capacity)
- Availability SLO: 99.95% (up from 99.5%)
- Deployment frequency: 10x increase (independent service deploys)

**Negative**:
- Initial migration: 6 month timeline, 4 FTE
- Ongoing OPEX: +$15k/month for Kafka and additional compute
- Team learning curve: 2 month ramp-up for event-driven patterns

**Risk Mitigations**:
- Strangler pattern: migrate service-by-service starting with read-heavy services
- Chaos engineering: monthly game days to test failure scenarios
- Observability: distributed tracing and event flow visualization
- Runbooks: comprehensive incident response playbooks

**SLO/Error Budget Impact**:
- Error budget: allocate 20% for migration-related incidents
- Monitoring: Kafka lag, event processing latency, saga completion rate
        """.strip(),
        daci={
            "driver": ["Principal Architect (Yaroslav V.)"],
            "approver": ["CTO", "VP Engineering"],
            "contributors": [
                "Trading Platform Team",
                "SRE Team",
                "Security Team",
                "Data Engineering",
            ],
            "informed": ["Product Management", "Risk Management", "Compliance"],
        },
        confidence_percent=82,
        metadata={
            "estimated_cost": "$90,000 (migration) + $180k/year (OPEX)",
            "timeline": "6 months (migration) + 2 months (stabilization)",
            "risk_level": "Medium-High",
            "review_date": "2024-12-01",
            "related_adrs": ["ADR-2023-015 (CQRS evaluation)"],
        },
    )

    print("\n✓ ADR Created:")
    print(f"  ID: {adr.adr_id}")
    print(f"  Title: {adr.title}")
    print(f"  Status: {adr.status}")
    print(f"  Confidence: {adr.confidence_percent}% ({ConfidenceLevel.from_score(adr.confidence_percent).name})")

    # Serialize to JSON
    adr_dict = adr.to_dict()
    print(f"\n✓ ADR JSON (first 300 chars):")
    adr_json = json.dumps(adr_dict, indent=2)
    print(adr_json[:300] + "...")


def demo_atam_analysis() -> None:
    """Demonstrate ATAM (Architecture Trade-Off Analysis)."""
    print("\n" + "=" * 80)
    print("ATAM - ARCHITECTURE TRADE-OFF ANALYSIS")
    print("=" * 80)

    atam = ATAMTemplate(
        quality_attributes=[
            "Performance",
            "Scalability",
            "Availability",
            "Security",
            "Maintainability",
        ],
        scenarios=[
            {
                "id": "QS-1",
                "quality": "Performance",
                "stimulus": "10,000 order submissions per second during market open",
                "source": "Trading clients",
                "environment": "Peak load, all markets active",
                "artifact": "Order ingestion API",
                "response": "Process orders with P95 latency < 200ms",
                "response_measure": "95th percentile latency",
                "priority": "High",
                "risk": "Medium",
            },
            {
                "id": "QS-2",
                "quality": "Availability",
                "stimulus": "Single Kafka broker failure",
                "source": "Infrastructure failure",
                "environment": "Normal trading hours",
                "artifact": "Event streaming backbone",
                "response": "Continue processing with no data loss",
                "response_measure": "Zero order loss, < 30s recovery time",
                "priority": "High",
                "risk": "High",
            },
            {
                "id": "QS-3",
                "quality": "Security",
                "stimulus": "Authentication service compromise attempt",
                "source": "External attacker",
                "environment": "Production",
                "artifact": "Auth service + API Gateway",
                "response": "Block unauthorized access, alert security team",
                "response_measure": "Zero unauthorized trades, alert within 60s",
                "priority": "Critical",
                "risk": "High",
            },
            {
                "id": "QS-4",
                "quality": "Scalability",
                "stimulus": "5x traffic growth over 6 months",
                "source": "Business growth",
                "environment": "Gradual increase",
                "artifact": "Entire platform",
                "response": "Scale horizontally without code changes",
                "response_measure": "Auto-scale within 2 minutes",
                "priority": "High",
                "risk": "Medium",
            },
        ],
        sensitivity_points=[
            "Kafka partition count: directly affects parallelism and throughput",
            "Database connection pool size: impacts query performance under load",
            "Circuit breaker thresholds: balance between fault isolation and availability",
            "Event schema design: affects backward compatibility and evolution",
        ],
        tradeoff_points=[
            "Strong consistency vs. Availability: Chose availability (AP in CAP)",
            "Latency vs. Throughput: Optimized for throughput, accepting 50ms added latency",
            "Operational complexity vs. Scalability: Accepted 40% complexity increase for 10x scale",
            "Cost vs. Redundancy: 3x Kafka brokers for high availability",
        ],
        risks=[
            {
                "id": "R-1",
                "description": "Event schema evolution breaks backward compatibility",
                "severity": "Medium",
                "probability": "Medium",
                "mitigation": "Schema registry with compatibility checks, versioned events",
            },
            {
                "id": "R-2",
                "description": "Kafka cluster becomes single point of failure",
                "severity": "High",
                "probability": "Low",
                "mitigation": "Multi-region Kafka with automatic failover, regular DR drills",
            },
            {
                "id": "R-3",
                "description": "Distributed debugging becomes very difficult",
                "severity": "Medium",
                "probability": "High",
                "mitigation": "Distributed tracing (Jaeger), correlation IDs, centralized logging",
            },
        ],
        non_risks=[
            "Team experience with microservices: Already have 2 years experience",
            "Kafka operational expertise: SRE team has Kafka certification",
        ],
    )

    print("\n✓ ATAM Analysis Created:")
    print(f"  Quality Attributes: {len(atam.quality_attributes)}")
    print(f"  Scenarios: {len(atam.scenarios)}")
    print(f"  Sensitivity Points: {len(atam.sensitivity_points)}")
    print(f"  Trade-off Points: {len(atam.tradeoff_points)}")
    print(f"  Risks: {len(atam.risks)}")

    print("\n  Top Quality Scenarios:")
    for scenario in atam.scenarios[:2]:
        print(f"    - {scenario['id']}: {scenario['quality']} - {scenario['stimulus'][:60]}...")

    print("\n  Key Trade-offs:")
    for tradeoff in atam.tradeoff_points[:2]:
        print(f"    - {tradeoff}")


def demo_stpa_analysis() -> None:
    """Demonstrate STPA (System Theoretic Process Analysis)."""
    print("\n" + "=" * 80)
    print("STPA - UNSAFE CONTROL ACTION ANALYSIS")
    print("=" * 80)

    stpa = STPATemplate(
        losses_hazards=[
            "L-1: Financial loss due to unauthorized or erroneous trades",
            "L-2: Regulatory penalties for compliance violations",
            "L-3: Reputational damage from system failures",
            "H-1: Unauthenticated user executes trades",
            "H-2: Order executed despite risk limit breach",
            "H-3: Duplicate order execution",
            "H-4: Order routed to wrong market",
        ],
        unsafe_control_actions=[
            {
                "uca_id": "UCA-1",
                "controller": "Auth Service",
                "action": "Issue access token",
                "type": "Provided when unsafe",
                "context": "Credentials compromised or session expired",
                "hazard": "H-1",
                "consequence": "L-1",
                "mitigation": "Multi-factor authentication, token expiry, rate limiting",
            },
            {
                "uca_id": "UCA-2",
                "controller": "Risk Manager",
                "action": "Approve order for execution",
                "type": "Not provided when needed",
                "context": "Risk limits exceeded but check bypassed",
                "hazard": "H-2",
                "consequence": "L-1, L-2",
                "mitigation": "Redundant risk checks, kill switch, real-time monitoring",
            },
            {
                "uca_id": "UCA-3",
                "controller": "Order Router",
                "action": "Execute order",
                "type": "Provided when unsafe",
                "context": "Idempotency key not checked, duplicate request",
                "hazard": "H-3",
                "consequence": "L-1, L-3",
                "mitigation": "Idempotency keys, deduplication window, transaction IDs",
            },
            {
                "uca_id": "UCA-4",
                "controller": "Market Gateway",
                "action": "Route order to exchange",
                "type": "Incorrect routing",
                "context": "Market selector logic error or stale market data",
                "hazard": "H-4",
                "consequence": "L-1",
                "mitigation": "Market validation, routing rules audit, circuit breakers",
            },
            {
                "uca_id": "UCA-5",
                "controller": "Settlement Service",
                "action": "Confirm trade settlement",
                "type": "Stopped too soon",
                "context": "Service crash during settlement reconciliation",
                "hazard": "H-2",
                "consequence": "L-2, L-3",
                "mitigation": "Saga pattern, compensation transactions, audit trail",
            },
        ],
        control_structure="""
Client App
  ↓
API Gateway (Rate limiting, TLS termination)
  ↓
Auth Service (Token validation, MFA)
  ↓
Order Validation (Schema, business rules)
  ↓
Risk Manager (Position limits, exposure checks)
  ↓
Order Router (Market selection, routing logic)
  ↓
Market Gateway (Exchange connectivity)
  ↓
Settlement Service (Confirmation, reconciliation)
        """.strip(),
        constraints=[
            "C-1: All orders must pass authentication before processing",
            "C-2: Risk limits must be checked before every execution",
            "C-3: Orders must have unique idempotency keys",
            "C-4: Market routing must validate exchange availability",
            "C-5: Settlement must complete or fully compensate",
            "C-6: Audit trail must capture all control decisions",
            "C-7: Circuit breakers must trigger on repeated failures",
        ],
    )

    print("\n✓ STPA Analysis Created:")
    print(f"  Losses/Hazards: {len(stpa.losses_hazards)}")
    print(f"  Unsafe Control Actions: {len(stpa.unsafe_control_actions)}")
    print(f"  Safety Constraints: {len(stpa.constraints)}")

    print("\n  Critical UCAs:")
    for uca in stpa.unsafe_control_actions[:3]:
        print(f"    - {uca['uca_id']}: {uca['controller']} - {uca['action']}")
        print(f"      Hazard: {uca['hazard']}, Mitigation: {uca['mitigation']}")


def demo_nfr_specification() -> None:
    """Demonstrate NFR specification following ISO/IEC 25010."""
    print("\n" + "=" * 80)
    print("NFR SPECIFICATION - ISO/IEC 25010")
    print("=" * 80)

    nfrs = [
        NFRTemplate(
            characteristic="Performance Efficiency",
            sub_characteristics=["Time behavior", "Resource utilization", "Capacity"],
            requirements=[
                {
                    "id": "NFR-P1",
                    "description": "Order submission API responds within 200ms at P95",
                    "rationale": "User experience requires near-instant feedback",
                    "priority": "Critical",
                },
                {
                    "id": "NFR-P2",
                    "description": "System sustains 50,000 orders/second throughput",
                    "rationale": "Business growth projection for next 12 months",
                    "priority": "High",
                },
                {
                    "id": "NFR-P3",
                    "description": "CPU utilization stays below 70% under normal load",
                    "rationale": "Headroom for traffic spikes and failover scenarios",
                    "priority": "Medium",
                },
            ],
            mechanisms=[
                "CDN for static assets",
                "Database connection pooling",
                "Query optimization and indexing",
                "Async processing via Kafka",
                "Caching with Redis (30s TTL)",
                "Horizontal auto-scaling (2-20 instances)",
            ],
            validation_approach=[
                "Load testing with k6 (weekly)",
                "APM monitoring (New Relic)",
                "Synthetic transactions (1-min intervals)",
                "Quarterly capacity planning review",
            ],
            slo_sla={
                "SLO_Latency": "P95 < 200ms, P99 < 500ms",
                "SLO_Throughput": "50,000 orders/sec sustained",
                "SLA_Availability": "99.95% monthly uptime",
            },
        ),
        NFRTemplate(
            characteristic="Reliability",
            sub_characteristics=["Availability", "Fault tolerance", "Recoverability"],
            requirements=[
                {
                    "id": "NFR-R1",
                    "description": "System achieves 99.95% availability (4.38h downtime/year)",
                    "rationale": "Contractual SLA with enterprise clients",
                    "priority": "Critical",
                },
                {
                    "id": "NFR-R2",
                    "description": "Service degrades gracefully under partial failures",
                    "rationale": "User experience priority over complete outage",
                    "priority": "High",
                },
                {
                    "id": "NFR-R3",
                    "description": "RTO < 1 hour, RPO < 15 minutes for critical services",
                    "rationale": "Regulatory requirement for financial systems",
                    "priority": "Critical",
                },
            ],
            mechanisms=[
                "Multi-AZ deployment across 3 availability zones",
                "Circuit breakers (Hystrix pattern)",
                "Retry with exponential backoff",
                "Health checks and automated failover",
                "Read replicas for database (3x)",
                "Kafka replication factor 3",
                "Regular automated backups (15-min RPO)",
            ],
            validation_approach=[
                "Chaos engineering (monthly game days)",
                "Disaster recovery drills (quarterly)",
                "Fault injection testing (weekly)",
                "SLO dashboards and alerting",
            ],
            slo_sla={
                "SLO_Availability": "99.95% (21.6 minutes downtime/month)",
                "SLO_MTTR": "Mean Time To Recovery < 30 minutes",
                "SLO_ErrorRate": "Error rate < 0.1% of requests",
            },
        ),
        NFRTemplate(
            characteristic="Security",
            sub_characteristics=[
                "Confidentiality",
                "Integrity",
                "Non-repudiation",
                "Authenticity",
            ],
            requirements=[
                {
                    "id": "NFR-S1",
                    "description": "All data encrypted at rest (AES-256) and in transit (TLS 1.3)",
                    "rationale": "Compliance with PCI DSS and SOC 2",
                    "priority": "Critical",
                },
                {
                    "id": "NFR-S2",
                    "description": "Multi-factor authentication required for all user accounts",
                    "rationale": "Regulatory requirement, industry best practice",
                    "priority": "Critical",
                },
                {
                    "id": "NFR-S3",
                    "description": "Complete audit trail of all financial transactions",
                    "rationale": "Regulatory compliance, fraud investigation",
                    "priority": "Critical",
                },
                {
                    "id": "NFR-S4",
                    "description": "Zero critical vulnerabilities in production",
                    "rationale": "Security posture, risk management",
                    "priority": "High",
                },
            ],
            mechanisms=[
                "TLS 1.3 for all API endpoints",
                "AES-256 encryption at rest",
                "OAuth 2.0 + OpenID Connect",
                "Hardware security modules (HSM) for key management",
                "WAF (Web Application Firewall)",
                "Rate limiting and DDoS protection",
                "Regular penetration testing",
                "SIEM for security monitoring",
                "Secrets management (HashiCorp Vault)",
            ],
            validation_approach=[
                "Security audit (quarterly)",
                "Penetration testing (bi-annual)",
                "Vulnerability scanning (weekly)",
                "Code security review (every PR)",
                "Compliance audit (annual SOC 2)",
            ],
            slo_sla={
                "SLO_VulnerabilityResponse": "Critical CVE patched within 24 hours",
                "SLO_IncidentResponse": "Security incidents acknowledged within 15 minutes",
            },
        ),
    ]

    print("\n✓ NFR Specifications Created:")
    for nfr in nfrs:
        print(f"\n  {nfr.characteristic}:")
        print(f"    Sub-characteristics: {', '.join(nfr.sub_characteristics)}")
        print(f"    Requirements: {len(nfr.requirements)}")
        print(f"    Mechanisms: {len(nfr.mechanisms)}")
        print(f"    SLO/SLA: {len(nfr.slo_sla)} defined")


def main() -> None:
    """Run all demonstrations."""
    print("\n" + "🏗️ " * 20)
    print("PRINCIPAL SYSTEM ARCHITECT PROMPT DEMONSTRATION")
    print("🏗️ " * 20)

    demo_system_prompt_creation()
    demo_adr_creation()
    demo_atam_analysis()
    demo_stpa_analysis()
    demo_nfr_specification()

    print("\n" + "=" * 80)
    print("✓ All demonstrations completed successfully!")
    print("=" * 80)
    print("\nThis demonstrates a comprehensive architectural documentation workflow:")
    print("1. System Architect Prompt - provides the agent's identity and capabilities")
    print("2. ADR - documents architectural decisions with full context and rationale")
    print("3. ATAM - analyzes quality attributes and trade-offs systematically")
    print("4. STPA - identifies unsafe control actions and safety constraints")
    print("5. NFR - specifies non-functional requirements following ISO/IEC 25010")
    print("\nAll templates support JSON serialization for integration with other systems.")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
