# TradePulse Operational Artifacts - Complete Index

This document serves as the master index for all operational artifacts in TradePulse, providing a comprehensive navigation guide for production operations, incident management, monitoring, and system lifecycle procedures.

## 🎯 Quick Navigation

### 🚨 **Emergency Response**
Start here during an incident:
1. [`incident_coordination_procedures.md`](incident_coordination_procedures.md) - Master incident response process
2. [`sla_alert_playbooks.md`](sla_alert_playbooks.md) - Alert-specific response procedures
3. [`incident_playbooks.md`](incident_playbooks.md) - Scenario-based playbooks

### 📊 **Production Operations**
Daily operational reference:
1. [`system_lifecycle_operations.md`](system_lifecycle_operations.md) - Complete lifecycle guide
2. [`operational_readiness_runbooks.md`](operational_readiness_runbooks.md) - Pre-launch checklist
3. [`operational_handbook.md`](operational_handbook.md) - Governance and controls

### 🎛️ **Monitoring & Dashboards**
Access monitoring and observability:
1. Production Operations Dashboard - [`../observability/dashboards/tradepulse-production-operations.json`](../observability/dashboards/tradepulse-production-operations.json)
2. SLO Policies - [`../observability/slo_policies.json`](../observability/slo_policies.json)
3. Alert Definitions - [`../observability/alerts.json`](../observability/alerts.json)

---

## 📚 Complete Artifact Catalog

### I. Operational Documentation

#### A. Master Operational Guides

**1. System Lifecycle Operations** [`system_lifecycle_operations.md`](system_lifecycle_operations.md)
- **Purpose**: Complete operational lifecycle from pre-production to shutdown
- **Use When**: Planning daily operations, executing startup/shutdown procedures
- **Key Sections**:
  - Pre-production preparation (24h, 12h, 4h, 1h before)
  - Production startup phase (T-30min to T+30min)
  - Active operations (continuous monitoring, hourly/daily tasks)
  - Production shutdown phase (settlement, reconciliation)
  - Maintenance windows (scheduled and emergency)
  - Operational schedules (daily, weekly, monthly, quarterly)
  - Backup and recovery operations
  - Capacity planning
- **Owner**: SRE Team + Operations Team

**2. Operational Readiness Runbooks** [`operational_readiness_runbooks.md`](operational_readiness_runbooks.md)
- **Purpose**: Pre-launch control checklist and operational alignment
- **Use When**: Before any production deployment or trading session
- **Key Sections**:
  - Pre-launch control checklist
  - Launch and halt scripts
  - SLA monitoring packet
  - Integrated runbook references
  - On-call discipline enhancements
- **Owner**: SRE Team

**3. Operational Handbook** [`operational_handbook.md`](operational_handbook.md)
- **Purpose**: Operational excellence and governance context
- **Use When**: Understanding operational standards and policies
- **Key Sections**:
  - Runbooks, releases, and on-call discipline
  - Golden data and quality playbooks
  - Reproducible end-to-end examples
  - Performance budgets
  - Data lake lifecycle
- **Owner**: Platform Team

#### B. Operations-Specific Guides

**4. OPERATIONS.md** [`OPERATIONS.md`](OPERATIONS.md)
- **Purpose**: Thermodynamic validation and progressive rollout operations
- **Use When**: Triaging validation failures, performing rollouts
- **Key Sections**:
  - Reading validate-energy failures
  - Restoring service without downtime
  - Approving changes that increase free energy
  - Manual rollout confirmation
- **Owner**: Platform Team

---

### II. Incident Management

#### A. Incident Response Framework

**5. Incident Coordination Procedures** [`incident_coordination_procedures.md`](incident_coordination_procedures.md)
- **Purpose**: Master incident management process
- **Use When**: Any incident declaration, coordination, or postmortem
- **Key Sections**:
  - Incident lifecycle (detection → postmortem → prevention)
  - Roles and responsibilities (IC, TL, CL, SO)
  - Incident severity classification (Sev 1-4)
  - Incident declaration process
  - Coordination workflows (alert-triggered, scenario-based, multi-system)
  - Communication protocols (internal, external, templates)
  - Resolution and handoff procedures
  - Postmortem process (timeline, requirements, quality standards)
  - Integration with existing playbooks
- **Owner**: SRE Team

**6. SLA/Alert Response Playbooks** [`sla_alert_playbooks.md`](sla_alert_playbooks.md)
- **Purpose**: Alert-specific response procedures and SLA tracking
- **Use When**: An alert fires in production
- **Key Sections**:
  - Quick reference matrix (alert → SLA → response time)
  - SLA definitions (API latency, ingestion, signal pipeline)
  - Alert response procedures for each alert:
    - TradePulseOrderErrorRate
    - TradePulseOrderLatency
    - TradePulseOrderAckLatency
    - TradePulseSignalToFillLatency
    - TradePulseDataIngestionFailures
    - TradePulseDataFreshness
    - TradePulseBacktestFailures
    - TradePulseOptimizationSlow
  - Escalation matrix
  - SLA breach procedures
  - Communication templates
  - Postmortem requirements
- **Owner**: SRE Team

**7. Incident Playbooks** [`incident_playbooks.md`](incident_playbooks.md)
- **Purpose**: Scenario-based incident response procedures
- **Use When**: Specific incident scenarios occur
- **Key Sections**:
  - Execution Lag (symptoms, actions, diagnostics, mitigations)
  - Rejected Orders (symptoms, actions, diagnostics, mitigations)
  - Data Gaps (symptoms, actions, diagnostics, mitigations)
  - On-call simulation drills
- **Owner**: Trading Operations Team

#### B. Incident Templates and Tracking

**8. Incident Report Template** [`../reports/incidents/incident_report_template.md`](../reports/incidents/incident_report_template.md)
- **Purpose**: Operational template for active incidents
- **Use When**: Declaring an incident

**9. Postmortem Template** [`../reports/incidents/postmortem_template.md`](../reports/incidents/postmortem_template.md)
- **Purpose**: Detailed postmortem structure
- **Use When**: Within 24-72 hours after incident resolution

**10. Action Item Register** [`../reports/incidents/action_item_register.md`](../reports/incidents/action_item_register.md)
- **Purpose**: Centralized CAPA tracking
- **Use When**: Recording and tracking corrective actions

---

### III. Operational Runbooks

#### A. Domain-Specific Runbooks

**11. Live Trading Runbook** [`runbook_live_trading.md`](runbook_live_trading.md)
- **Purpose**: Step-by-step trading operations
- **Use When**: Operating live trading systems
- **Owner**: Trading Operations Team

**12. Data Incident Runbook** [`runbook_data_incident.md`](runbook_data_incident.md)
- **Purpose**: Data feed containment and recovery
- **Use When**: Data quality issues or ingestion failures
- **Owner**: Data Pipeline Team

**13. Disaster Recovery Runbook** [`runbook_disaster_recovery.md`](runbook_disaster_recovery.md)
- **Purpose**: Regional failover and recovery procedures
- **Use When**: Site failure or disaster scenario
- **Owner**: SRE Team

**14. Kill Switch Failover Runbook** [`runbook_kill_switch_failover.md`](runbook_kill_switch_failover.md)
- **Purpose**: Emergency trading halt procedures
- **Use When**: Critical system failure requiring immediate halt
- **Owner**: Risk Officer + SRE Team

**15. Secret Rotation Runbook** [`runbook_secret_rotation.md`](runbook_secret_rotation.md)
- **Purpose**: Credential rotation with Vault automation
- **Use When**: Scheduled rotation or credential compromise suspected
- **Owner**: Security Team

**16. Secret Leak Runbook** [`runbook_secret_leak.md`](runbook_secret_leak.md)
- **Purpose**: Security incident response for credential exposure
- **Use When**: Suspected or confirmed credential leak
- **Owner**: Security Team

**17. Release Validation Runbook** [`runbook_release_validation.md`](runbook_release_validation.md)
- **Purpose**: Pre-release and post-release validation
- **Use When**: Deploying to production
- **Owner**: Release Management Team

**18. Time Synchronization Runbook** [`runbook_time_synchronization.md`](runbook_time_synchronization.md)
- **Purpose**: NTP/PTP monitoring and drift remediation
- **Use When**: Time sync issues or regular verification
- **Owner**: Infrastructure Team

**19. Inference Incident Runbook** [`runbook_inference_incident.md`](runbook_inference_incident.md)
- **Purpose**: Inference service degradation response
- **Use When**: Inference latency, error rate, or quality regressions
- **Owner**: MLOps + SRE Team

**20. Latency Degradation Runbook** [`runbook_latency_degradation.md`](runbook_latency_degradation.md)
- **Purpose**: Critical path latency regression response
- **Use When**: p95/p99 latency breaches across signal/order/inference
- **Owner**: SRE Team

**21. Model Rollback Runbook** [`runbook_model_rollback.md`](runbook_model_rollback.md)
- **Purpose**: Standardized model rollback procedure
- **Use When**: Model regression, drift response, or canary failure
- **Owner**: MLOps Team

**22. Data Drift Response Runbook** [`runbook_data_drift_response.md`](runbook_data_drift_response.md)
- **Purpose**: Drift triage and remediation
- **Use When**: Feature drift alerts or data quality regressions
- **Owner**: Data + MLOps Team

#### B. Testing and Resilience

**23. Stress Playbooks** [`stress_playbooks.md`](stress_playbooks.md)
- **Purpose**: Stress testing and resilience validation
- **Use When**: Planning chaos tests or market stress simulations
- **Key Sections**:
  - Replay catalogue (historic stress events)
  - Fault-injection matrix
  - Portfolio allocation frameworks
  - Automation and reporting hooks
- **Owner**: Research Team + SRE Team

---

### IV. Monitoring and Observability

#### A. Dashboards

**20. Production Operations Dashboard** [`../observability/dashboards/tradepulse-production-operations.json`](../observability/dashboards/tradepulse-production-operations.json)
- **Purpose**: Comprehensive production monitoring
- **Features**:
  - System health status indicator
  - Active alerts panel
  - SLO error budget tracking
  - System operational mode
  - Order execution metrics
  - Latency SLA tracking
  - Data pipeline health
  - Active alerts table
  - Strategy operations
  - Resource utilization
- **Refresh**: 10 seconds
- **Links**: Direct links to incident and SLA playbooks

**21. Overview Dashboard** [`../observability/dashboards/tradepulse-overview.json`](../observability/dashboards/tradepulse-overview.json)
- **Purpose**: General system overview
- **Features**: Order throughput, error rates, basic metrics

**22. Latency Insights Dashboard** [`../observability/dashboards/tradepulse-latency-insights.json`](../observability/dashboards/tradepulse-latency-insights.json)
- **Purpose**: Detailed latency analysis
- **Features**: P50/P95/P99 latencies, breakdown by component

**23. Queue Operations Dashboard** [`../observability/dashboards/tradepulse-queue-operations.json`](../observability/dashboards/tradepulse-queue-operations.json)
- **Purpose**: Queue health monitoring
- **Features**: Queue depths, processing rates, backlog

**24. Resource Utilization Dashboard** [`../observability/dashboards/tradepulse-resource-utilization.json`](../observability/dashboards/tradepulse-resource-utilization.json)
- **Purpose**: Infrastructure resource monitoring
- **Features**: CPU, memory, disk, network utilization

#### B. Alerts and SLOs

**25. Alert Definitions** [`../observability/alerts.json`](../observability/alerts.json)
- **Purpose**: Declarative Prometheus alert rules
- **Coverage**: Execution, data, strategy alerts
- **Integration**: Referenced by SLA/Alert Playbooks

**26. SLO Policies** [`../observability/slo_policies.json`](../observability/slo_policies.json)
- **Purpose**: Service Level Objective definitions
- **Coverage**:
  - API Latency SLO (99%, <350ms, 1.5% error budget)
  - Ingestion Availability SLO (99%, 1% error budget)
  - Signal Pipeline SLO (P95 <250ms, 2% error budget)
- **Features**: Burn rate thresholds, evaluation periods

**27. Metrics Catalog** [`../observability/metrics.json`](../observability/metrics.json)
- **Purpose**: Canonical metric definitions
- **Coverage**: All Prometheus metrics with labels and types

**28. Observability README** [`../observability/README.md`](../observability/README.md)
- **Purpose**: Observability as code documentation
- **Coverage**: Layout, building, integration, health monitoring

---

### V. Release and Quality

**29. Release Readiness Report** [`../reports/release_readiness.md`](../reports/release_readiness.md)
- **Purpose**: Pre-deployment validation checklist
- **Use When**: Before any production deployment

**30. Production Cutover Checklist** [`../reports/prod_cutover_readiness_checklist.md`](../reports/prod_cutover_readiness_checklist.md)
- **Purpose**: Final go/no-go gate
- **Use When**: Immediately before production cutover

**31. CI/CD Health Review** [`../reports/ci_cd_health_review.md`](../reports/ci_cd_health_review.md)
- **Purpose**: Pipeline health assessment
- **Use When**: Regular CI/CD health reviews

---

### VI. Additional Operational Resources

**32. Production Readiness Guide** [`PRODUCTION_READINESS_GUIDE.md`](PRODUCTION_READINESS_GUIDE.md)
- **Purpose**: Comprehensive production readiness checklist
- **Use When**: Preparing new features for production

**33. Reliability Documentation** [`reliability.md`](reliability.md)
- **Purpose**: SLOs, error budgets, on-call policies
- **Use When**: Understanding reliability standards

**34. Monitoring Documentation** [`monitoring.md`](monitoring.md)
- **Purpose**: Monitoring architecture and practices
- **Use When**: Setting up or understanding monitoring

**35. Troubleshooting Guide** [`troubleshooting.md`](troubleshooting.md)
- **Purpose**: Common issues and solutions
- **Use When**: Debugging production issues

---

## 🔄 Operational Workflows

### Daily Operations Workflow
```
Pre-Market (08:00 UTC)
  → Review system_lifecycle_operations.md (Pre-Production Phase)
  → Check operational_readiness_runbooks.md (Pre-Launch Checklist)
  → Execute health checks

Market Open (09:30 UTC)
  → Follow system_lifecycle_operations.md (Startup Phase)
  → Monitor Production Operations Dashboard
  → Execute system_lifecycle_operations.md (Active Operations)

Market Close (16:00 UTC)
  → Follow system_lifecycle_operations.md (Shutdown Phase)
  → Generate daily reports
  → Update operational log
```

### Incident Response Workflow
```
Alert Fires
  → Check sla_alert_playbooks.md for specific alert
  → Execute immediate response procedure
  → If not resolved in target time → Declare incident

Incident Declared
  → Follow incident_coordination_procedures.md
  → Assign roles (IC, TL, CL, SO)
  → Execute response using incident_playbooks.md scenarios
  → Reference operational runbooks as needed

Incident Resolved
  → Complete postmortem using template
  → Update action_item_register.md
  → Update relevant playbooks with learnings
```

### Release Workflow
```
Pre-Release
  → Review release_readiness.md
  → Complete prod_cutover_readiness_checklist.md
  → Follow operational_readiness_runbooks.md

Release Execution
  → Follow system_lifecycle_operations.md (Startup Phase)
  → Use runbook_release_validation.md
  → Monitor Production Operations Dashboard

Post-Release
  → Validate metrics against SLOs
  → Document in release notes
  → Update operational documentation if needed
```

---

## 📊 Metrics and KPIs

Track operational excellence using:

### Availability Metrics
- System uptime %
- SLA compliance % (per service)
- Error budget consumption

### Incident Metrics
- MTTD (Mean Time To Detect)
- MTTA (Mean Time To Acknowledge)
- MTTI (Mean Time To Investigate)
- MTTM (Mean Time To Mitigate)
- MTTR (Mean Time To Resolve)
- Incident count (by severity)

### Operational Metrics
- Deployment success rate
- Backup success rate
- Change success rate
- Playbook utilization rate
- Postmortem completion rate

---

## 🔍 Finding What You Need

### By Role

**On-Call Engineer**:
- Start: [`sla_alert_playbooks.md`](sla_alert_playbooks.md)
- Escalate: [`incident_coordination_procedures.md`](incident_coordination_procedures.md)
- Execute: Domain-specific runbooks

**Incident Commander**:
- Primary: [`incident_coordination_procedures.md`](incident_coordination_procedures.md)
- Reference: [`incident_playbooks.md`](incident_playbooks.md)
- Communicate: Templates in sla_alert_playbooks.md

**Operations Engineer**:
- Daily: [`system_lifecycle_operations.md`](system_lifecycle_operations.md)
- Pre-Launch: [`operational_readiness_runbooks.md`](operational_readiness_runbooks.md)
- Monitor: Production Operations Dashboard

**Release Manager**:
- Pre-Release: [`../reports/release_readiness.md`](../reports/release_readiness.md)
- Cutover: [`../reports/prod_cutover_readiness_checklist.md`](../reports/prod_cutover_readiness_checklist.md)
- Execute: [`system_lifecycle_operations.md`](system_lifecycle_operations.md)

### By Situation

**System is Down**: [`incident_coordination_procedures.md`](incident_coordination_procedures.md) → Sev 1 response

**Alert Firing**: [`sla_alert_playbooks.md`](sla_alert_playbooks.md) → Find specific alert

**Data Issue**: [`runbook_data_incident.md`](runbook_data_incident.md)

**Security Issue**: [`runbook_secret_leak.md`](runbook_secret_leak.md)

**Need to Halt Trading**: [`runbook_kill_switch_failover.md`](runbook_kill_switch_failover.md)

**Planning Release**: [`operational_readiness_runbooks.md`](operational_readiness_runbooks.md)

**Daily Operations**: [`system_lifecycle_operations.md`](system_lifecycle_operations.md)

---

## 🔄 Maintenance and Updates

### Update Triggers
Update operational artifacts after:
- Major incidents (Severity 1 or 2)
- New features/services deployed
- Process improvements identified
- Quarterly scheduled reviews
- Escalation path changes
- SLA/SLO modifications

### Review Schedule
- **Weekly**: Incident learnings integration
- **Monthly**: Metrics review and minor updates
- **Quarterly**: Comprehensive artifact review
- **Annually**: Strategic operational assessment

### Update Process
1. Identify gaps or improvements
2. Draft updates with context
3. Review with stakeholders
4. Update related artifacts for consistency
5. Communicate changes to teams
6. Update this index if structure changes

---

## 📞 Getting Help

### Documentation Issues
- Create issue with label: `documentation`
- Tag: `@docs-team`

### Operational Questions
- Ask in: `#operations`
- On-call: PagerDuty "TradePulse-SRE"

### Incident Support
- Critical: Page via PagerDuty
- Guidance: `#incidents` channel
- Postmortem: `@incident-commander`

---

## 📖 Related Documentation

**Architecture**: [`ARCHITECTURE.md`](ARCHITECTURE.md)
**Testing**: [`TESTING.md`](../TESTING.md), [`TEST_ARCHITECTURE.md`](TEST_ARCHITECTURE.md)
**Security**: [`../SECURITY.md`](../SECURITY.md), [`security/`](security/)
**Development**: [`../CONTRIBUTING.md`](../CONTRIBUTING.md)
**API**: [`api.md`](api.md), [`api/`](api/)

---

## ✅ Completeness Checklist

This index represents the complete operational artifact suite for TradePulse:

- ✅ **Production Dashboard**: Comprehensive monitoring with system health, alerts, SLOs
- ✅ **SLA/Alert Playbooks**: Alert-specific response procedures with escalation paths
- ✅ **Incident Procedures**: Coordinated incident management framework
- ✅ **Lifecycle Documentation**: Complete daily/weekly/monthly operational procedures
- ✅ **Integration**: All artifacts cross-referenced and integrated
- ✅ **Templates**: Incident and postmortem templates provided
- ✅ **Communication**: Communication templates and protocols defined
- ✅ **Schedules**: Daily, weekly, monthly, quarterly operational schedules
- ✅ **Monitoring**: Comprehensive dashboard suite with real-time metrics
- ✅ **Runbooks**: Domain-specific operational runbooks
- ✅ **Quality**: SLO policies, error budgets, and tracking

---

**Система готова до повного циклу життєзабезпечення в продакшн-середовищі.**

Last Updated: 2025-11-10
Version: 1.0
Owner: SRE Team + Operations Team
Next Review: 2026-02-10
