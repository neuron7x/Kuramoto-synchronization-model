# GeoSync Engineering Enablement Program

This playbook defines the structured learning program for GeoSync engineering. It is designed to accelerate mastery of our trading platform while ensuring consistent, safe delivery in production. Each pillar is owned, resourced, and instrumented with measurable outcomes so the program remains accountable and adaptive.

## 1. Role Tracks and Competency Framework

| Track | Purpose | Core Competencies | Reference Resources | Progress Indicators |
| --- | --- | --- | --- | --- |
| Core Platform | Ownership of execution, risk, and data pipelines | Distributed systems, fault tolerance, observability, regulatory controls | `docs/architecture/`, `docs/runbook_live_trading.md`, production-readiness checklist | SLA adherence, on-call maturity level, design review scores |
| Quant & Strategy Tooling | Rapid experimentation and deployment of trading models | Statistical modeling, Python stack, feature stores, evaluation frameworks | `docs/feature_store_sync_and_registry.md`, analytics notebooks | Backtest quality index, model promotion velocity, post-release ROI |
| Reliability & SRE | Platform stability, automation, incident management | SLO management, chaos engineering, release guardrails | `docs/reliability.md`, `docs/operational_handbook.md`, incident playbooks | Error budget consumption, MTTR, runbook coverage |
| Security & Governance | Safeguarding assets and compliance | Secrets management, threat modeling, audit trails | `docs/security/`, `docs/incident_playbooks.md`, security training modules | Vulnerability remediation lead time, policy compliance score |

Competency levels (L1–L4) are defined across technical depth, delivery excellence, and leadership impact. Each role track lead maintains a rubric with observable behaviors and review criteria in the shared skills matrix (see Section 2).

## 2. Skills Matrix and Assessment Cadence

* Skills matrices live in the PeopleOps data warehouse (`skills_matrix` table) with exports to Confluence for transparency.
* Rubrics cover foundational knowledge, advanced expertise, operational excellence, and cross-functional collaboration.
* Quarterly calibration sessions ensure inter-team alignment; bias mitigation uses anonymized scenario scoring before discussions.
* Engineers self-assess monthly; managers perform observational assessments quarterly; peers provide 360° feedback biannually.
* Radar charts from the analytics team visualize growth trajectories per competency area.

## 3. Growth Plans and Career Architecture

* Each engineer maintains a rolling 12-month Individual Growth Plan (IGP) co-authored with their manager.
* Plans map required competencies, targeted milestones, mentorship engagements, and practice opportunities (projects, on-call rotations, code stewardship).
* Growth objectives must align with company OKRs and risk posture, with explicit KPIs (e.g., reduction in change failure rate, throughput of successful experiments).
* Progress is reviewed monthly in skip-level sessions to ensure accountability and unblock support needs.

## 4. Mentorship Guild

* Every engineer participates in a mentor/mentee pairing lasting at least six months.
* Mentors receive enablement training covering psychological safety, coaching frameworks, and inclusive feedback.
* Office hours are logged in the guild calendar; attendance metrics feed into the enablement dashboard.
* Mentor retrospectives occur quarterly to refine the program and share best practices across tracks.

## 5. Internal Seminars and Learning Rituals

| Ritual | Cadence | Owner | Description | Expected Output |
| --- | --- | --- | --- | --- |
| Architecture Deep Dives | Bi-weekly | Principal engineers | Rotating presentations on system internals, ADR reviews, resilience learnings | Recorded sessions, updated ADRs |
| Trading Domain Masterclasses | Monthly | Quant leads | Strategy theory, risk modeling, compliance updates | Annotated decks, updated domain glossary |
| Tooling Clinics | Bi-monthly | Developer productivity team | Hands-on labs for CLI, CI/CD, feature flag management | Step-by-step guides, updated runbooks |
| Guest Lectures | Quarterly | Enablement PM | External experts (market structure, security) | Summaries, actionable recommendations |

## 6. Reading Groups and Knowledge Libraries

* The reading guild curates quarterly themes (e.g., market microstructure, distributed consensus, ML observability).
* Reading sessions follow the "Prepare, Summarize, Challenge" format; facilitators document takeaways and next steps in the knowledge base.
* The `docs/library/` directory hosts whitepapers, annotated book summaries, and example code references.

## 7. Technical Battles, Pairing, and Rotations

* **Technical Battles:** Structured debates on design decisions. Artifacts include pros/cons matrices, risk analysis, and consensus ADR updates.
* **Mob/Pair Programming:** Scheduled pairing rotations twice per sprint; pairings tracked to ensure cross-track exposure.
* **Rotations:** 6-week immersions across SRE, platform, and quant tooling; includes shadowing, runbook creation, and retro documentation.
* **Shadowing:** New hires shadow on-call incidents, change advisory boards, and code reviews with structured reflection forms.

## 8. Incident Lessons Journal

* Maintained in the Incident Knowledge Base (`incident_lessons` Notion database) synchronized with `docs/stress_playbooks.md`.
* Each entry includes context, contributing factors, mitigations, and links to updated runbooks or code commits.
* Quarterly post-incident summits identify systemic themes and feed backlog prioritization.

## 9. Library of Exemplars

* Repository directory `examples/` stores vetted reference implementations with commentary.
* Each exemplar includes annotated design trade-offs, benchmark data, and security considerations.
* Versioning ensures traceability between exemplar updates and production incidents or feature launches.

## 10. Progress Measurement and Reviews

* **Monthly check-ins:** review growth plan progress, update skill matrix deltas, confirm mentorship outcomes.
* **Quarterly enablement review:** aggregated metrics (competency deltas, training attendance, production KPIs) shared with leadership.
* **Annual certification:** role-track leads run scenario-based evaluations; passing is required for senior promotion or on-call certification renewal.
* Analytics dashboards track correlation between enablement participation and production reliability metrics to ensure business value.

## 11. Governance and Continuous Improvement

* Enablement PMO maintains the roadmap, budget, and risk register.
* Feedback loop includes anonymous surveys, office hours, and integration with the retrospectives board.
* Program health metrics (NPS, completion rates, regression of incidents) feed into quarterly OKR reviews.

Ownership matrix, KPIs, and schedule templates are version-controlled in this repository under `docs/enablement/`. Updates follow the documentation governance process.
