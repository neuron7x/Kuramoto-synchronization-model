# Changelog

Ведемо зміни за правилами [Keep a Changelog](https://keepachangelog.com/) та [SemVer](https://semver.org/).
Цей файл автоматично оновлюється за допомогою [Towncrier](https://towncrier.readthedocs.io/).
Додавайте короткі фрагменти до каталогу `newsfragments/` для кожного Pull Request.

<!-- towncrier release notes start -->

## [Unreleased]
### Added
- DOC PR COPILOT v2: LLM-based documentation agent for automated documentation review and patch generation in Pull Requests.
- Agent configuration system in `.github/agents/` with system prompts, integration guides, and examples.
- 4C Principles documentation (Clarity, Conciseness, Correctness, Consistency) for documentation standards.
- **Principal Architect Improvements:** Added 9 missing `__init__.py` files for proper Python package structure.
- **Principal Architect Improvements:** Comprehensive code quality report documenting 89.5% reduction in violations.

### Changed
- Hardened Release Drafter automation (v6 workflow, semantic version resolver, metrics summary).
- Refactored cache key normalisation to use deterministic ``repr`` tuples, trimming redundant recursion and improving synthetic throughput by ~19%; systems with non-deterministic ``__repr__`` implementations on cache keys should validate behaviour.

### Fixed
- **Principal Architect Improvements:** Fixed 4,410 code quality violations (89.5% reduction from 4,928 to 518)
  - Whitespace and formatting: 3,808 issues (99.3% improvement)
  - Unused imports: 138 removed (95.2% improvement)  
  - Unused variables: 35 removed (72.9% improvement)
  - F-string formatting: 68 fixed (100%)
  - Protocol method definitions: 13 fixed (100%)
- Fixed forward reference type hints in backtesting microservice.
- Fixed missing imports in integration test suite.

### Security
- **Principal Architect Improvements:** Verified zero security vulnerabilities via CodeQL scan
- Confirmed all `eval()` usage is safe (PyTorch model.eval() only)

## [2.1.3] - 2025-10-05
### Added
- Новий конвеєр **CI/CD**: `ci.yml` (матриці лінтів/тестів, concurrency, кеші), `pre-commit.yml`, `auto-merge.yml`, `sbom-scan.yml`, `publish-image.yml` (cosign), `data-sanity.yml`.
- Якість/управління змінами: `benchmarks.yml`, `integration.yml`, `commitlint.yml`, `pr-labeler.yml`, `todo.yml`.
- Контракти: `buf.yml` (lint+breaking), `gen-drift.yml` (+ Makefile `generate`).
### Changed
- Оновлено `.pre-commit-config.yaml` (black, ruff, prettier, buf hooks).
- Адаптовано JS gateway (`domains/platform/gateway`) під lint-джоб.

## [2.1.2] - 2025-10-05
### Added
- Конфіг для pre-commit (`.pre-commit-config.yaml`), pytest (`pytest.ini`).
- Шаблони GitHub: issue/PR, labeler, dependabot, release-drafter.
- Робочі процеси CI: release-drafter, codeql, lint, тест-матриця, docs-build, deploy, infra-check.

### Added
- Розширення скриптів автоматизації (`scripts/*`).
- Шаблони процесів: `.gitattributes`, `CODEOWNERS`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`.

### Changed
- Уточнення документації щодо фрактальної декомпозиції (FPM-A).

## [2.1.1] - 2025-10-05
### Added
- Інтегровано професійні проектні артефакти: `.gitattributes`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`, `CODEOWNERS`.
- Додано Python-пакет `scripts` із уніфікованим CLI (`python -m scripts`).

### Security
- Уніфікація ліній закінчення файлів через `.gitattributes`.

## [2.1.0] - 2025-10-05
### Added
- Інтеграція **FPM-A**: фрактальні юніти, граф залежностей, метрики цикломатичної складності, CI-гейти.

## [2.0.0] - 2025-10-05
### Added
- Початковий каркас TradePulse: protobuf-контракти, Python/Next.js скелети, інфраструктурні файли.

## [0.1.0] - 2025-10-05
### Added
- Повноцінний каркас проєкту з фрактальною архітектурою (FPM-A), індикаторами (Kuramoto/Entropy/Hurst/Ricci), агентною системою, пайплайнами даних, фазовою логікою, бектестом, CLI та Streamlit-панеллю.
- Професійна документація (README, MkDocs), CI/CD, безпека (CodeQL, SBOM), автолінти й тести.
### Fixed
- Заповнено шаблонні місця у CLI/скриптах; узгоджено версування і конфіги.
