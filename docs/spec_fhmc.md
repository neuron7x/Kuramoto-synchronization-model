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

---

## Онлайн моніторинг біомаркерів (2025)

**Sliding Window DFA-α**

Реал-тайм моніторинг з ковзним вікном (window=2000):

\[
\alpha_{\text{agent}}(t) = \text{DFA}(\text{buffer}[t-w:t], \text{min\_win}=50, \text{max\_win}=500)
\]

Цільовий діапазон: \(\alpha \in [0.8, 1.0]\) для стійкості до non-stationarity.

**Hölder-експонента для фракційної дифузії**

\[
H(x) = \lim_{\epsilon \to 0} \frac{\log |x(t+\epsilon) - x(t)|}{\log \epsilon}
\]

Адаптація для EoS-стабільності в енергетичних ринках з fractional derivatives.

**Детекція білого шуму (fallback)**

\[
\text{is\_white\_noise} = |\alpha - 0.5| < 0.05
\]

При детекції нефрактального режиму → перехід на OU-noise.

---

## A/B Testing Protocols (2025)

**Гіпотеза валідації**

- **H₀**: Treatment покращує Sharpe ≥5-10% vs. baseline
- **H₁**: MaxDD знижується ≥15%
- **H₂**: \(\alpha_{\text{agent}} \approx 0.9\) у WAKE

**Симуляція regime-shift**

Генерація vol\_shock > 1.5:

\[
\sigma_{\text{shock}}(t) = \sigma_{\text{base}} \times 1.5 \quad \text{для } t \in [0.4T, 0.6T]
\]

**Метрики успішності**

- Sharpe ratio: \(\frac{\mathbb{E}[r]}{\sigma(r)} \sqrt{252} \uparrow 5-10\%\)
- Max drawdown: \(\max_t(\text{peak}_t - \text{value}_t) \downarrow 15\%\)
- Statistical significance: \(p < 0.05\)

---

## Continual Learning Metrics (2025)

**FID Score (Fréchet Inception Distance)**

Для generative replay якості:

\[
\text{FID} = \|\mu_{\text{real}} - \mu_{\text{gen}}\|^2 + \text{Tr}(\Sigma_{\text{real}} + \Sigma_{\text{gen}} - 2\sqrt{\Sigma_{\text{real}}\Sigma_{\text{gen}}})
\]

Target: FID < 50 для стійкості replay.

**Retention Rate**

\[
\text{retention}(T_i) = \frac{\text{perf}(T_i, t_{\text{final}})}{\text{perf}(T_i, t_{\text{initial}})}
\]

Target: retention ≥ 0.9 (збереження 90% знань).

**Backward Transfer**

\[
\text{BT}(T_i) = \text{perf}(T_i, \text{after new tasks}) - \text{perf}(T_i, \text{before})
\]

Positive BT → позитивний трансфер знань.

**Catastrophic Forgetting Index**

\[
\text{CFI} = \frac{1}{N}\sum_{i=1}^N \max\left(0, \frac{\max_t \text{perf}(T_i, t) - \text{perf}(T_i, t_{\text{final}})}{\max_t \text{perf}(T_i, t)}\right)
\]

Target: CFI < 0.2 (мінімальне забування).

---

## Self-Rewarding RL для динамічного η-tuning (2025)

**Adaptive Learning Rate**

\[
\eta_{t+1} = \begin{cases}
\min(\eta_t \times 1.1, \eta_{\max}), & \text{якщо } \nabla r_t > 0 \land \text{conv\_rate} < 0 \\
\max(\eta_t \times 0.9, \eta_{\min}), & \text{якщо } \nabla r_t < 0 \\
\eta_t, & \text{інакше}
\end{cases}
\]

Де \(\nabla r_t\) — тренд винагороди, conv\_rate — швидкість збіжності.

**Convergence Rate в кризах**

\[
\text{conv\_rate} = \frac{d}{dt}\left(\alpha_t - \alpha_{\text{target}}\right)
\]

Negative rate → наближення до цільового α.

---

## Verification Hypotheses (2025)

| Гіпотеза | Метрика | Target | Метод валідації |
|----------|---------|--------|-----------------|
| **H1**: α-стабільність покращує Sharpe | Sharpe ratio | ↑5-10% | A/B test з regime-shift |
| **H2**: MaxDD знижується з \(\alpha \in [0.8,1.0]\) | Max drawdown | ↓15% | Backtest на історичних кризах |
| **H3**: Retention > 0.9 у continual learning | Retention rate | ≥0.9 | Multi-task sequential training |
| **H4**: FID < 50 для generative replay | FID score | <50 | Sleep engine validation |
| **H5**: CFI < 0.2 (low forgetting) | CFI | <0.2 | Task interference experiments |

**Протокол виконання**

1. Симулювати vol\_shock > 1.5 (20% тривалості)
2. Запустити baseline vs. treatment (1000 епізодів кожен)
3. Виміряти: Sharpe, MaxDD, α\_stability, retention, FID, CFI
4. Statistical test: Welch's t-test, p < 0.05
5. Логувати convergence\_rate, backward\_transfer

**Expected Results**

- Sharpe: 0.8 → 0.88 (+10%)
- MaxDD: 0.25 → 0.21 (-16%)
- α\_agent: 0.89 ± 0.05 (in target [0.8, 1.0])
- Retention: 0.92
- FID: 42
- CFI: 0.18

---

## References (2025)

- **Fractional derivatives for energy trading**: ResearchGate 2024/2025
- **Self-rewarding RL (SRDRL)**: MDPI 2024/2025
- **DFA-α in human activity**: PNAS 2007/2025
- **1/f-slope arousal markers**: eLife 2020/2025
- **Fractal Market Hypothesis**: AIMS Press 2025
- **Language-guided RL**: arXiv 2025
- **Hölder exponents for EoS-stability**: Nature Comm. 2025
