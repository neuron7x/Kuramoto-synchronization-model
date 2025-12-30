# Citation Map

| Claim ID | Statement | Where in Repo | Code Mapping | Citations |
| --- | --- | --- | --- | --- |
| NC-001 | Dopamine controller applies TD(0) reinforcement learning with phasic/tonic gating for trading decisions. | docs/neuromodulators/dopamine.md (Overview) | src/tradepulse/core/neuro/dopamine/ | [@SuttonBarto2018RL] |
| NC-002 | Serotonin controller models tonic and phasic stress responses with hysteretic hold logic to suspend trading under high stress. | docs/neuromodulators/serotonin.md (Overview) | src/tradepulse/core/neuro/serotonin/ | [@JacobsAzmitia1992Serotonin; @BendaHerz2003Adaptation] |
| NC-003 | Serotonin improvements incorporate receptor desensitization and adaptation kinetics to shape veto thresholds. | docs/SEROTONIN_IMPROVEMENTS_V2.4.0.md (Theoretical Foundation) | src/tradepulse/core/neuro/serotonin/ | [@Ferguson2001GPCR; @BendaHerz2003Adaptation] |
| NC-004 | HPC-AI v4 combines predictive coding, active inference, and SRDRL for adaptive trading in non-stationary markets. | docs/HPC_AI_V4.md (Overview) | neuropro/hpc_active_inference_v4.py | [@Friston2010FreeEnergy] |
| TH-001 | Thermodynamic control validates Helmholtz free energy (F = U − T·S) to keep rollouts within safety envelope. | docs/TACL.md (Introduction) | runtime/thermo_controller.py; runtime/energy_validator.py | [@Callen1985Thermodynamics; @Friston2010FreeEnergy] |
| CM-001 | Crisis predictor flags instability via free-energy deviation and entropy/latency signals in the thermodynamic controller. | docs/ML_CRISIS_PREDICTOR.md (Overview) | runtime/thermo_controller.py; evolution/crisis_ga.py | [@Friston2010FreeEnergy] |
| OBS-001 | Serotonin observability exports Prometheus metrics for neuromodulator state and latency to dashboards. | docs/SEROTONIN_OBSERVABILITY_IMPLEMENTATION.md (Prometheus Metrics) | core/neuro/serotonin/observability.py | [@Prometheus2024Docs] |
| BT-001 | Walk-forward backtesting and transaction cost modeling follow established financial ML validation practices. | docs/backtest.md (Walk-Forward Engine) | backtest/engine.py; backtest/transaction_costs.py | [@LopezDePrado2018AFML] |
| SEC-001 | Security framework aligns controls to NIST incident handling guidance and ISO/IEC 27001 requirements. | docs/security/SECURITY_FRAMEWORK_INDEX.md (Introduction) | docs/security/; .github/workflows/security-guards.yml | [@NIST80061r2; @ISO27001_2022] |
