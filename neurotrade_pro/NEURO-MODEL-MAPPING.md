# Neuroeconomic Controller: EMH + Basal Ganglia + Dopamine RPE

**Mapping**
- H(t): deployable risk units
- M(t): core engine efficiency (alpha health)
- E(t): alternative engine activation
- S(t): global activation signal
- D(t): aggregate stress demand from {dd, liq, reg}
- B(t): belief (volatility-regime probability)

**Biological correspondences**
- EMH triggers: hypoxia/VEGF, infection & IFNγ/STAT1, C/EBPβ emergency granulopoiesis, CXCL12/CXCR4 axis, cytokines (G/GM-CSF, IL-6, EPO), TLR→G-CSF.
- Controller trigger M < ε·D mirrors EMH activation under marrow underperformance.

**Equations**
As in the main spec: Euler updates for H,M,E; S aggregates D, underperformance (1−M/M0), dopamine RPE, and belief error.

**Action selection**
Basal ganglia softmax with Go/No-Go gating by threat modes (GREEN/AMBER/RED).
