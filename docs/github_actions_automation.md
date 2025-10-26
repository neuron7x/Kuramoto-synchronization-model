# Автоматизація CI/CD у GitHub Actions

## Огляд
GitHub Actions забезпечує нативний механізм автоматизації життєвого циклу програмного забезпечення без необхідності сторонніх сервісів. Використовуючи YAML-конфігурації, команда може запускати тести, збірки, лінтери, аналіз безпеки та деплой у відповідь на будь-які події в репозиторії (push, pull request, release, schedule тощо). Це робить платформа ідеальним інструментом для DevOps-команд, які прагнуть повторюваності процесів, передбачуваності результатів і безперервного зворотного зв'язку.

## Архітектура workflow
- **Тригери подій** визначають, коли запускається автоматизація. Наприклад, `push` у гілку `main` для продакшену, `pull_request` для валідації змін, `schedule` для нічних регресій чи сканів безпеки.
- **Матриця середовищ** дає можливість паралельно перевіряти різні версії Python, Node.js чи інші платформи, гарантує сумісність і скорочує час зворотного зв'язку.
- **Jobs і steps** описують впорядковану послідовність дій: checkout коду, встановлення залежностей, виконання тестів, збірка артефактів, публікація звітів.
- **Кешування** (`actions/cache`) пришвидшує роботу, зберігаючи залежності між запусками. Ключ варто прив'язувати до файлових хешів (`pyproject.toml`, `package-lock.json`), щоб уникнути конфліктів.
- **Артефакти** (`actions/upload-artifact`) дозволяють ділитися результатами (наприклад, coverage, звітами безпеки) між job-ами або з рецензентами.

## Базовий приклад workflow
```yaml
name: CI Quality Gate

on:
  pull_request:
    branches: ["**"]
  push:
    branches: ["main"]

permissions:
  contents: read
  pull-requests: read
  security-events: write

jobs:
  quality:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11"]
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v6
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      - name: Run linters
        run: |
          ruff check .
          black --check .
          mypy src/
      - name: Execute unit tests
        run: pytest --maxfail=1 --disable-warnings --junitxml=reports/junit.xml
      - name: Security scan
        uses: github/codeql-action/analyze@v3
      - name: Upload reports
        uses: actions/upload-artifact@v4
        with:
          name: qa-reports
          path: reports/
```

> **Порада:** для великих проєктів варто розбивати перевірки на декілька job-ів (наприклад, `lint`, `test`, `build`, `deploy`) та використовувати `needs`, щоб формувати чіткий конвеєр і підвищувати спостережуваність.

## Інтеграція з Docker та середовищами
- **Docker Build:** використовуйте `docker/setup-buildx-action` для мультиархітектурних збірок та `docker/build-push-action` для публікації образів у реєстри (GitHub Container Registry, AWS ECR, GCR).
- **Інфраструктура як код:** підключайте Terraform або Pulumi через офіційні GitHub Actions для перевірки та деплою середовищ. Для продуктивних розгортань обов'язково застосовуйте `environment` з правилами затвердження.
- **Хмарні платформи:** workflows легко інтегруються з AWS, Azure, GCP завдяки OIDC (безпечний обмін токенами без довгоживучих секретів).

## Практики безпеки
- Використовуйте [залежності з lock-файлів](../requirements-dev.lock) і контрольні списки безпеки (наприклад, SLSA).
- Залучайте `codeql` та `trivy` для сканування вихідного коду, контейнерів і залежностей.
- Мінімізуйте `permissions` у workflows, увімкніть `actions: read` за замовчуванням у `organization settings`.
- Застосовуйте `secret-scanning` та `push-protection` для попередження витоків секретів.

## Спостережуваність та аналітика
- Вмикайте [GitHub Actions Insights](https://docs.github.com/actions/monitoring-and-troubleshooting-workflows/using-github-actions-insights) для відстеження тривалості, частоти відмов та оптимізації ресурсів.
- Надсилайте метрики в сторонні сервіси (Datadog, New Relic, Grafana Cloud) через офіційні інтеграції або власні клієнти.
- Логування можна збагачувати маркерами (`::group::`, `::notice::`) для кращої читабельності журналів.

## Подальші кроки для команди TradePulse
1. Стандартизувати реюзабельні workflows у каталозі `.github/workflows/` з підтримкою `workflow_call`.
2. Інтегрувати автоматичні перевірки інфраструктурних змін (Terraform Plan, Kubernetes manifests) перед деплоєм у production.
3. Налаштувати policy-as-code (OPA, Conftest) для контролю конфігурацій безпеки.
4. Оновити документацію онбордингу, щоб нові учасники мали єдиний довідник з GitHub Actions.

Завдяки цим підходам GitHub Actions стає центральною платформою для CI/CD, що поєднує якість, безпеку й швидкість постачання змін.
