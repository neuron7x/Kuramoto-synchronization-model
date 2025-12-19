# TradePulse Roadmap

The roadmap translates the long-term improvement plan into a time-phased delivery schedule. It highlights the initiatives
required to keep TradePulse production-grade while enabling sustainable growth. Progress should be reviewed monthly and the
roadmap updated after every major milestone. For a gap analysis of what is still missing for live trading, consult the
[Production Readiness Assessment](production-readiness.md) and keep the deliverables in that checklist aligned with the
quarterly milestones captured here.

## 2024 Achievements (Completed)

| Quarter | Focus Areas | Status |
| --- | --- | --- |
| **Q2 2024** | Architecture, Developer Experience, Typing | ✅ **Completed**: C4 system diagram, VS Code dev container, strict mypy enabled, plugin loader prototype. |
| **Q3 2024** | Testing, Observability, Backtesting | ✅ **Completed**: 670+ test files, dockerised E2E scenarios, versioned dashboards, backtester with commission/slippage models. |
| **Q4 2024** | Security, Performance, Culture | ✅ **Completed**: SBOM generation, profiling scripts, Dependabot/Trivy gates, chaos testing playbooks. |

## 2025 Progress

| Quarter | Focus Areas | Status |
| --- | --- | --- |
| **Q1-Q2 2025** | Test Coverage, Documentation, Core Engine | ✅ **Completed**: 351 core tests (100% pass rate), 683 source files with zero type errors, 150+ markdown documents. |
| **Q3 2025** | Live Trading Beta, Security Hardening | ✅ **Completed**: Zero critical vulnerabilities, CodeQL/Semgrep scanning, reliability tests (40+ scenarios). |
| **Q4 2025** | Pre-Production Beta, Dashboard Hardening | 🚧 **In Progress**: Coverage at ~71% (target 98%), dashboard hardening pending, release checklist in preparation. |

## Q1 2026 Roadmap

| Milestone | Status | Target Date |
| --- | --- | --- |
| Achieve 98% test coverage CI gate | ⏳ **Planned** | January 2026 |
| Complete dashboard production hardening | ⏳ **Planned** | January 2026 |
| Sign off release checklist for v1.0 | ⏳ **Planned** | February 2026 |
| External beta testing program (5-10 testers) | ⏳ **Planned** | February 2026 |
| v1.0 Production Release | 🎯 **Target** | Q1 2026 |

## 2025/2026 North Star Themes

- **Extensible Architecture**: Complete the pluggable strategy framework with entry-point discovery, version negotiation, and
  compatibility validation. Pair with API versioning and OpenAPI specs for external partners.
- **Holistic Testing**: Maintain a regression test matrix that ties features to unit, integration, property-based, and
  performance suites. Automate nightly E2E scenarios with mocked exchanges and stress backtest scenarios (flash crashes,
  trading halts).
- **Production Observability**: Define explicit SLOs, implement burn-rate alerts, and expand runbooks with escalation paths and
  troubleshooting dashboards.
- **Secure Supply Chain**: Embed SBOM generation, SAST/DAST gates, and dependency hygiene automation in the release pipeline to
  guarantee <7 day turnaround on critical CVEs.
- **Performance & Scalability**: Establish continuous profiling, benchmarking, and adaptive worker scaling so TradePulse meets
  latency targets under variable load.
- **Engineering Excellence**: Keep documentation current (CHANGELOG, roadmap, architectural diagrams) and maintain contributor
  guidelines that facilitate external collaboration.

## How to Use This Roadmap

1. **Plan sprints**: Reference the current quarter milestones when creating sprint goals and cross-team commitments.
2. **Track progress**: Update milestone status (Not Started → In Progress → Done) in pull requests and release notes.
3. **Align stakeholders**: Share the roadmap during product reviews and incident postmortems to keep expectations realistic.
4. **Revisit quarterly**: Review the improvement plan and adjust target quarters or milestones based on capacity and impact.
5. **Document decisions**: Capture significant scope changes and rationale in `CHANGELOG.md` and link back to the roadmap.

Maintaining this roadmap ensures the "development map" for TradePulse remains actionable, transparent, and aligned with the
platform's strategic objectives.
