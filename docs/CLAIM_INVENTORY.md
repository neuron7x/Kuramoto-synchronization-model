# Claim Inventory (Phase 0)

> **Note (2026-05-05 audit refresh).** The first two rows below quote
> wording that was downgraded in commit `95e22e2` (audit Pass-2). The
> source files (`docs/neuromodulators/dopamine.md`,
> `docs/neuromodulators/serotonin.md`) now scope "production-grade"
> wording to module-level integration-readiness, not live-venue capital
> safety (L-1 still binds). The quotations below remain as the
> historical text the inventory was tracking; the `Subsystem Tag` column
> is the live link to the current source.

| Subsystem | Claim Snippet (historical wording) | File + Heading | Existing Citation | Subsystem Tag |
| --- | --- | --- | --- | --- |
| Neuro-control | "production-grade neuromodulatory controller… based on TD(0) reinforcement learning with phasic/tonic dopamine dynamics" *(downgraded `95e22e2`)* | docs/neuromodulators/dopamine.md (Overview) | [@SuttonBarto2018RL] | dopamine |
| Neuro-control / Risk | "production-grade neuromodulatory controller for risk management… models tonic and phasic serotonin dynamics with hysteretic hold logic" *(downgraded — see `docs/SEROTONIN_PRACTICAL_SUITABILITY_ASSESSMENT.md` provenance block)* | docs/neuromodulators/serotonin.md (Overview) | [@JacobsAzmitia1992Serotonin; @BendaHerz2003Adaptation] | serotonin |
| Neuro-control | “Improvements draw from tonic-phasic dynamics, GPCR desensitization, Hodgkin-Huxley-like thresholds, neuronal adaptation” | docs/SEROTONIN_IMPROVEMENTS_V2.4.0.md (Theoretical Foundation) | [@JacobsAzmitia1992Serotonin; @Ferguson2001GPCR; @BendaHerz2003Adaptation] | serotonin |
| Thermodynamics | “computes the Helmholtz free energy F = U - T·S” | docs/TACL.md (Introduction) | [@Callen1985Thermodynamics; @Friston2010FreeEnergy] | TACL/free-energy |
| Crisis management | “thermodynamic-inspired crisis detection system that monitors system free energy, entropy, and latency” | docs/ML_CRISIS_PREDICTOR.md (Overview) | [@Friston2010FreeEnergy] | crisis-detection |
| Neuro-control (research) | “framework combining Hierarchical Predictive Coding, Active Inference, and SRDRL” | docs/HPC_AI_V4.md (Overview/Theoretical Foundations) | [@Friston2010FreeEnergy]; Anokhin TFS components [heuristic] | HPC/active-inference |
| Backtesting | “Walk-forward backtesting engine with transaction cost modeling and validation hooks” | docs/backtest.md (Overview; Claim BT-001) | [@LopezDePrado2018AFML] | backtesting (BT-001) |
| Backtesting | Regime-switching asset allocation and phase analysis references (Ang & Bekaert 2004; Guidolin & Timmermann 2008; etc.) | docs/FPM-A.md (References) | DOI links present | backtesting/regime |
| Security | “aligned with NIST, ISO 27001, and industry best practices” | docs/security/SECURITY_FRAMEWORK_INDEX.md (Introduction) | [@NIST80061r2; @ISO27001_2022] | security |
| Observability | Prometheus-based serotonin metrics export and dashboards | docs/SEROTONIN_OBSERVABILITY_IMPLEMENTATION.md (Prometheus Metrics) | [@Prometheus2024Docs] | observability |
