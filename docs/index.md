# TradePulse Documentation Portal

<div class="hero" data-animate="fade-up">
  <p class="hero__eyebrow">Документація • Strategy • Operations</p>
  <h1>Опануйте TradePulse з повною впевненістю</h1>
  <p class="hero__lead">
    Цей портал поєднує концепції, формальні стандарти та практичні процедури,
    необхідні для проєктування, запуску та масштабування торгових агентів.
    Сформуйте мислення системного архітектора, інженера продуктивності та
    операційної команди — в одному місці.
  </p>
  <div class="hero__actions">
    <a class="hero-action hero-action--primary" href="quickstart/">Розпочати за 15 хвилин →</a>
    <a class="hero-action hero-action--ghost" href="ARCHITECTURE/">Дослідити архітектуру</a>
    <a class="hero-action hero-action--ghost" href="operational_handbook/">Перейти до операцій</a>
  </div>
  <img class="hero__illustration" src="assets/banner.png" alt="Візуалізація потоків TradePulse" loading="lazy">
  <span class="hero__badge-ring" aria-hidden="true"></span>
</div>

<div class="section-header" data-animate="fade-up">
  <span class="section-header__eyebrow">Conceptual Foundation</span>
  <h2>Концептуальні опори платформи</h2>
</div>

<div class="feature-grid">
  <article class="card" data-animate="pop">
    <h3 class="card__title">Системна архітектура</h3>
    <p class="card__meta">Від макро-компонентів до контрольних площин</p>
    <p>Отримайте повну картину сервісів, потоків даних, схем розгортання та SLO.
      Узгодьте вимоги до пропускної здатності та стійкості з дорожньою картою.</p>
    <div class="card__links">
      <a class="card__link" href="ARCHITECTURE/">Architecture Overview</a>
      <a class="card__link" href="architecture/system_overview/">System Diagrams</a>
      <a class="card__link" href="architecture/system_modules_reference/">System Modules Reference</a>
      <a class="card__link" href="architecture/serving_resilience/">Serving Resilience</a>
    </div>
  </article>
  <article class="card" data-animate="pop">
    <h3 class="card__title">Методологія FPM-A</h3>
    <p class="card__meta">Фази, режими та гарантії валідації</p>
    <p>Опануйте фазові каталоги, контракти керування агентами та контрольні
      точки відповідності. Узгодьте адаптивні алгоритми з вимірюваними SLO.</p>
    <div class="card__links">
      <a class="card__link" href="FPM-A/">FPM-A Framework</a>
      <a class="card__link" href="indicators/">Indicators Library</a>
      <a class="card__link" href="metrics_discipline/">Metrics Discipline</a>
    </div>
  </article>
  <article class="card" data-animate="pop">
    <h3 class="card__title">Risk &amp; Observability Fabric</h3>
    <p class="card__meta">Комплаєнс, експозиція та нагляд в реальному часі</p>
    <p>Забезпечте безперервний аудит моделей, контролю ризиків і сигналів.
      Мапа контролів охоплює Prometheus, журналювання, політики витоку даних.</p>
    <div class="card__links">
      <a class="card__link" href="risk_ml_observability/">Risk Controls</a>
      <a class="card__link" href="security/architecture/">Security Architecture</a>
      <a class="card__link" href="security/dlp_and_retention/">DLP &amp; Retention</a>
    </div>
  </article>
  <article class="card" data-animate="pop">
    <h3 class="card__title">Нейроекономічна модель</h3>
    <p class="card__meta">Дивергенція, конвергенція та квантові оновлення стану</p>
    <p>Формалізуйте адаптивний когнітивний процес ринку з перевіреними
      методами: Rescorla–Wagner, quantum active inference та геометрією
      індикаторів. Отримайте повну документацію пакету <code>neuroecon</code>
      разом із валідацією та прикладами.</p>
    <div class="card__links">
      <a class="card__link" href="neuroecon/">NeuroEcon Documentation</a>
    </div>
  </article>
</div>

<div class="section-header" data-animate="fade-up">
  <span class="section-header__eyebrow">Practical Execution</span>
  <h2>Практичні акселератори та сценарії</h2>
</div>

<div class="feature-grid">
  <article class="card" data-animate="fade-up">
    <h3 class="card__title">Фреймворк дій дослідника</h3>
    <p class="card__meta">Індикатори → Бектест → Стратегія → Лайв</p>
    <p>Використовуйте покрокові сценарії для розробки, налаштування та запуску
      агентів. У кожному кроці — контрольні списки якості, артефакти та приклади.</p>
    <div class="card__links">
      <a class="card__link" href="scenarios/">Developer Scenarios</a>
      <a class="card__link" href="cookbook_backtest_live/">Backtest → Live Guide</a>
      <a class="card__link" href="extending/">Extending TradePulse</a>
    </div>
  </article>
  <article class="card" data-animate="fade-up">
    <h3 class="card__title">Execution &amp; Risk Toolchain</h3>
    <p class="card__meta">Реалізація, черги та backpressure</p>
    <p>Розгортайте маршрути execution API, симулюйте глибину ринку, керуйте
      чергами та SLA для live-трейдингу з перевіреними параметрами.</p>
    <div class="card__links">
      <a class="card__link" href="execution/">Execution Guide</a>
      <a class="card__link" href="backtest_execution_simulation/">Simulation Engine</a>
      <a class="card__link" href="queue_and_backpressure/">Queue Controls</a>
    </div>
  </article>
  <article class="card" data-animate="fade-up">
    <h3 class="card__title">Observability Runway</h3>
    <p class="card__meta">Моніторинг, алертинг, резилієнс</p>
    <p>Побудуйте метрики, алерти та дашборди з прикладами для Grafana,
      визначте сигнали катастроф та проведення chaos-днів.</p>
    <div class="card__links">
      <a class="card__link" href="monitoring/">Monitoring Playbook</a>
      <a class="card__link" href="resilience/">Chaos &amp; Resilience</a>
      <a class="card__link" href="reliability/">Reliability Targets</a>
    </div>
  </article>
</div>

<div class="section-header" data-animate="fade-up">
  <span class="section-header__eyebrow">First 30 Minutes</span>
  <h2>Маршрут швидкого старту</h2>
</div>

<div class="timeline" data-animate="wave">
  <div class="timeline__step">
    <strong>0–10 хвилин — налаштування середовища</strong>
    <p>Виконайте <a href="quickstart/">Quick Start</a>, застосуйте docker або local setup,
      перевірте CLI: <code>tradepulse --help</code>.</p>
  </div>
  <div class="timeline__step">
    <strong>10–20 хвилин — перший експеримент</strong>
    <p>Запустіть сценарій з <a href="scenarios/">Developer Scenarios</a>, оберіть шаблон
      backtest і згенеруйте базові метрики продуктивності.</p>
  </div>
  <div class="timeline__step">
    <strong>20–30 хвилин — операційна підготовка</strong>
    <p>Зіставте результати з <a href="quality_gates/">Quality Gates</a>, оберіть релевантні
      runbook'и та задокументуйте в <a href="documentation_standardisation_playbook/">Documentation Playbook</a>.</p>
  </div>
</div>

<div class="section-header" data-animate="fade-up">
  <span class="section-header__eyebrow">Operational Mastery</span>
  <h2>Runbook-и та програми нагляду</h2>
</div>

<ul class="rich-list">
  <li data-animate="fade-up">
    <strong>Operational Handbook</strong>
    Консолідований довідник процедур, бюджетів продуктивності та моделей
    управління даними. <a href="operational_handbook/">Відкрити</a>
  </li>
  <li data-animate="fade-up">
    <strong>Performance &amp; Reliability</strong>
    Контрольні списки тестів, симуляцій та енергетичні бюджети.
    <a href="performance_testing_program/">Performance Testing</a>,
    <a href="runbook_disaster_recovery/">Disaster Recovery</a>
  </li>
  <li data-animate="fade-up">
    <strong>Інцидентна готовність</strong>
    Розширені playbook-и для live-трейдингу, витоків секретів і синхронізації часу.
    <a href="incident_playbooks/">Incident Playbooks</a>,
    <a href="runbook_secret_rotation/">Secret Rotation</a>
  </li>
</ul>

<div class="section-header" data-animate="fade-up">
  <span class="section-header__eyebrow">Formal Governance</span>
  <h2>Формальні стандарти та контроль якості</h2>
</div>

<div class="feature-grid">
  <article class="card" data-animate="fade-up">
    <h3 class="card__title">Quality Gates &amp; Readiness</h3>
    <p>Підтримуйте аудити, DoR/DoD і релізні віхи за допомогою стандартизованих чек-листів.</p>
    <div class="card__links">
      <a class="card__link" href="quality_gates/">Quality Automation</a>
      <a class="card__link" href="quality-dor-dod/">DoR/DoD Checklist</a>
      <a class="card__link" href="reports/prod_cutover_readiness_checklist/">Cutover Checklist</a>
    </div>
  </article>
  <article class="card" data-animate="fade-up">
    <h3 class="card__title">Documentation Lifecycle</h3>
    <p>Забезпечте формальну відповідність знань: стандарти, шаблони, ADR та аудити.</p>
    <div class="card__links">
      <a class="card__link" href="documentation_governance/">Governance Model</a>
      <a class="card__link" href="documentation_standardisation_playbook/">Standardisation</a>
      <a class="card__link" href="documentation_information_architecture/">Information Architecture</a>
      <a class="card__link" href="adr/">Architecture Decisions</a>
    </div>
  </article>
  <article class="card" data-animate="fade-up">
    <h3 class="card__title">Безпека та відповідність</h3>
    <p>Формалізуйте IAM, контроль витоку даних, політики зберігання та відповідність регуляторам.</p>
    <div class="card__links">
      <a class="card__link" href="security/iam/">IAM Playbook</a>
      <a class="card__link" href="security/hardening/">Hardening Program</a>
      <a class="card__link" href="security/dlp_and_retention/">Retention Policy</a>
    </div>
  </article>
</div>

<div class="section-header" data-animate="fade-up">
  <span class="section-header__eyebrow">Continuous Evolution</span>
  <h2>Стратегічний напрям і розвиток команди</h2>
</div>

<ul class="rich-list">
  <li data-animate="fade-up">
    <strong>Roadmap Alignment</strong>
    Поєднайте квартальні ініціативи з ключовими віхами розвитку платформи.
    <a href="roadmap/">Дорожня карта</a>, <a href="improvement_plan/">Improvement Plan</a>
  </li>
  <li data-animate="fade-up">
    <strong>Enablement &amp; Training</strong>
    Створюйте програми наставництва, траєкторії росту та рев'ю компетенцій.
    <a href="training_enablement_program/">Enablement Program</a>,
    <a href="developer_productivity_program/">Productivity Program</a>
  </li>
  <li data-animate="fade-up">
    <strong>Responsible AI &amp; Compliance</strong>
    Застосовуйте рамку Responsible AI для оцінки ризиків та прозорості моделей.
    <a href="responsible_ai_program/">Responsible AI</a>,
    <a href="governance/">Governance &amp; Data Controls</a>
  </li>
</ul>

---

**Last updated:** 2025-07-11
