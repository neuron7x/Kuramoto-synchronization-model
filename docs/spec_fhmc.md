# FHMC (Fracto-Hypothalamic Meta-Controller) Specification

## Формальні рівняння

**Flip-flop (гістерезис)**

\[
\text{State}_{t+1}=\begin{cases}
\text{SLEEP}, & \text{якщо } \mathrm{TH}(t)>\theta_{\mathrm{hi}} \ \lor\ \mathrm{OX}(t)<\omega_{\mathrm{lo}} \\
\text{WAKE}, & \text{якщо } \mathrm{TH}(t)<\theta_{\mathrm{lo}} \ \land\ \mathrm{OX}(t)>\omega_{\mathrm{hi}} \\
\text{State}_{t}, & \text{інакше}
\end{cases}
\]

**Orexin-arousal**

\[
\mathrm{OX}(t)=\sigma\big(k_1\,\mathbb E[r\mid\pi_t]+k_2\,\mathrm{novelty}(t)+k_3\,\mathrm{load}(t)\big),\quad
\beta(t)=\beta_0+a_1\,\mathrm{OX}(t)-a_2\,\mathrm{TH}(t)
\]

**Threat-imminence**

\[
\mathrm{TH}(t)=w_1\,z(\mathrm{MaxDD})+w_2\,z(\mathrm{VolShock})+w_3\,\mathrm{CPScore}(t)
\]

**OU-noise (безперервні дії)**

\[
\mathrm{d}x_t=\theta(\mu-x_t)\,\mathrm{d}t+\sigma\,\mathrm{d}W_t
\]

**Colored-noise (1/f^{\beta})**

Спектральне формування амплітуди \(A(f)\propto f^{-\beta/2}\).

**DFA (α-експонента)**

Лінійна регресія у log-log між масштабом вікна та середнім флуктуаційним відхиленням.

**Aperiodic 1/f slope**

Регресія \(\log P(f)=b+m\log f\) для частот без піків осциляцій.

**RPE/APE**

\[
\delta_r=r+\gamma V(s')-V(s),\quad
\delta_a=\mathbb{1}_{a=a_t}-\pi_{\text{habit}}(a\mid s)
\]

\[
\nabla \theta_{\text{actor}}\propto \delta_r \nabla \log \pi(a\mid s;\beta(t))+\lambda_h\,\delta_a\,g(s,a)
\]

**Фракційна (Леві) дифузія оновлення**

\[
\theta \leftarrow \theta + \eta\,g + \eta_f\,\xi_{\alpha},\quad \xi_{\alpha}\sim \mathrm{Levy}(\alpha,0)
\]

**Мультифрактальний каскад (p-model, діадичний)**

На кожному кроці масив ваг множиться на \((p, 1-p)\) у підвідрізках; Hӧlder-поля оцінюються з вейвлет-коефіцієнтів.

## Реалізація

Усі формальні рівняння реалізовані в наступних модулях:

| Формула | Модуль | Функція/Клас |
|---------|--------|--------------|
| Flip-flop | `runtime/thermo_controller.py` | `FHMC.flipflop_step()` |
| Orexin-arousal | `runtime/thermo_controller.py` | `FHMC.compute_orexin()` |
| Threat-imminence | `runtime/thermo_controller.py` | `FHMC.compute_threat()` |
| OU-noise | `rl/explore/noise.py` | `OUProcess` |
| Colored-noise | `utils/fractal_cascade.py` | `pink_noise()` |
| DFA | `core/metrics/dfa.py` | `dfa_alpha()` |
| Aperiodic slope | `core/metrics/aperiodic.py` | `aperiodic_slope()` |
| RPE/APE | `rl/core/habit_head.py` | `ape_update()` |
| Lévy diffusion | `neuropro/multifractal_opt.py` | `fractional_update()` |
| p-model cascade | `utils/fractal_cascade.py` | `DyadicPMCascade` |
| Hölder fields | `core/metrics/holder.py` | `holder_exponent_wavelet()`, `local_holder_spectrum()` |
| Singularity spectrum | `core/metrics/holder.py` | `singularity_spectrum()`, `multifractal_width()` |
