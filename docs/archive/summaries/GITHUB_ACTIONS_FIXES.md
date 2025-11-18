# Виправлення GitHub Actions тестів для TradePulse

## Огляд проблем

Було виявлено дві основні проблеми з GitHub Actions workflows:

### 1. CI — Pin Terraform version / Terraform validation tests (FAILING)

**Файл:** `.github/workflows/pin-terraform-version.yml`

**Проблеми:**
- ❌ Версія Go 1.20 застаріла (go.mod вимагає 1.22)
- ❌ Версія Terraform 1.5.7 не відповідає вимогам (versions.tf вимагає >= 1.6.0)
- ❌ Відсутній крок завантаження Go модулів перед тестами

**Виправлення:**
```yaml
# Було:
- name: Set up Go
  uses: actions/setup-go@v4
  with:
    go-version: '1.20'

- name: Set up Terraform
  uses: hashicorp/setup-terraform@v2
  with:
    terraform_version: '1.5.7'

# Стало:
- name: Set up Go
  uses: actions/setup-go@v4
  with:
    go-version: '1.22'  # ✅ Відповідає go.mod

- name: Set up Terraform
  uses: hashicorp/setup-terraform@v2
  with:
    terraform_version: '1.6.6'  # ✅ Відповідає >= 1.6.0
```

**Додано крок:**
```yaml
- name: Download Go modules
  run: go mod download
```

### 2. Deployment & Infrastructure Validation / Validate deployment assets (FAILING)

**Файл:** `.github/workflows/deploy-environments.yml`

**Проблеми:**
- ⚠️ Terraform init може не завантажувати провайдери належним чином
- ⚠️ Terraform fmt не перевіряє рекурсивно
- ⚠️ Відсутня перевірка успішності встановлення kustomize
- ⚠️ Версія kustomize може бути застарілою

**Виправлення:**

#### Terraform валідація
```yaml
# Було:
- name: Terraform init (backend disabled)
  run: terraform -chdir=infra/terraform/eks init -backend=false

- name: Terraform fmt
  run: terraform -chdir=infra/terraform/eks fmt -check

# Стало:
- name: Terraform init (backend disabled)
  run: |
    cd infra/terraform/eks
    terraform init -backend=false -input=false  # ✅ Додано -input=false

- name: Terraform fmt
  run: terraform -chdir=infra/terraform/eks fmt -check -recursive  # ✅ Додано -recursive
```

#### Kustomize валідація
```yaml
# Було:
- name: Install kustomize
  uses: imranismail/setup-kustomize@v2
  with:
    kustomize-version: '5.4.1'

- name: Validate staging manifest build
  run: kustomize build deploy/kustomize/overlays/staging >/tmp/staging.yaml

# Стало:
- name: Install kustomize
  uses: imranismail/setup-kustomize@v2
  with:
    kustomize-version: '5.4.3'  # ✅ Оновлена версія

- name: Verify kustomize installation
  run: kustomize version  # ✅ Додано перевірку

- name: Validate staging manifest build
  run: kustomize build deploy/kustomize/overlays/staging >/tmp/staging.yaml
```

## Інструкції для застосування виправлень

### Варіант 1: Застосувати виправлення вручну

1. Відкрийте файл `.github/workflows/pin-terraform-version.yml`
2. Змініть версію Go з `1.20` на `1.22`
3. Змініть версію Terraform з `1.5.7` на `1.6.6`
4. Додайте крок `go mod download` перед запуском тестів

5. Відкрийте файл `.github/workflows/deploy-environments.yml`
6. Оновіть команду `terraform init` з додаванням `-input=false`
7. Додайте `-recursive` до команди `terraform fmt`
8. Оновіть версію kustomize з `5.4.1` на `5.4.3`
9. Додайте крок перевірки версії kustomize

### Варіант 2: Використати виправлені файли

Виправлені файли знаходяться в директорії outputs:
- `pin-terraform-version.yml`
- `deploy-environments.yml`

Скопіюйте їх в директорію `.github/workflows/` вашого репозиторію.

## Перевірка

Після застосування виправлень:

1. Зробіть commit і push змін:
```bash
git add .github/workflows/pin-terraform-version.yml
git add .github/workflows/deploy-environments.yml
git commit -m "fix: update GitHub Actions workflow versions and validation"
git push origin main
```

2. Перевірте GitHub Actions:
   - Перейдіть до вкладки "Actions" у вашому репозиторії
   - Перегляньте результати workflow
   - Переконайтеся, що тести проходять успішно ✅

## Додаткові рекомендації

### Для pin-terraform-version.yml
- Розгляньте можливість кешування Go модулів для пришвидшення CI:
```yaml
- name: Cache Go modules
  uses: actions/cache@v4
  with:
    path: ~/go/pkg/mod
    key: ${{ runner.os }}-go-${{ hashFiles('**/go.sum') }}
    restore-keys: |
      ${{ runner.os }}-go-
```

### Для deploy-environments.yml
- Розгляньте можливість кешування Terraform провайдерів:
```yaml
- name: Cache Terraform providers
  uses: actions/cache@v4
  with:
    path: ~/.terraform.d/plugin-cache
    key: ${{ runner.os }}-terraform-${{ hashFiles('**/.terraform.lock.hcl') }}
    restore-keys: |
      ${{ runner.os }}-terraform-
```

## Очікувані результати

Після застосування всіх виправлень:
- ✅ Terraform validation tests будуть проходити успішно
- ✅ Deployment assets validation буде проходити успішно
- ✅ Всі 9 перевірок мають бути успішними

## Технічні деталі

### Чому Go 1.22?
Файл `go.mod` в корені проєкту містить:
```go
module github.com/TradePulse/TradePulse

go 1.22
```

### Чому Terraform >= 1.6.0?
Файл `infra/terraform/eks/versions.tf` містить:
```hcl
terraform {
  required_version = ">= 1.6.0"
  ...
}
```

### Структура тестів
Go тести знаходяться в:
- `infra/terraform/tests/eks_validation_test.go`
- `infra/terraform/tests/eks_validation_connectivity_test.go`

Вони використовують:
- `github.com/gruntwork-io/terratest` для Terraform тестування
- `github.com/stretchr/testify` для assertion
