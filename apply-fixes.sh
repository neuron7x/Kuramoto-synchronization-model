#!/bin/bash
# Скрипт для застосування виправлень GitHub Actions workflows

set -e

echo "🔧 Застосування виправлень GitHub Actions workflows..."

# Кольори для виводу
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Перевірка, чи ми в корені репозиторію
if [ ! -d ".github/workflows" ]; then
    echo -e "${RED}❌ Помилка: .github/workflows директорія не знайдена${NC}"
    echo "Переконайтеся, що ви знаходитесь в корені репозиторію TradePulse"
    exit 1
fi

# Створюємо backup
echo -e "${YELLOW}📦 Створення backup оригінальних файлів...${NC}"
mkdir -p .github/workflows/backup
cp .github/workflows/pin-terraform-version.yml .github/workflows/backup/ 2>/dev/null || true
cp .github/workflows/deploy-environments.yml .github/workflows/backup/ 2>/dev/null || true
echo -e "${GREEN}✅ Backup створено в .github/workflows/backup/${NC}"

# Застосування виправлень до pin-terraform-version.yml
echo -e "${YELLOW}🔄 Виправлення pin-terraform-version.yml...${NC}"
sed -i "s/go-version: '1.20'/go-version: '1.22'/" .github/workflows/pin-terraform-version.yml
sed -i "s/terraform_version: '1.5.7'/terraform_version: '1.6.6'/" .github/workflows/pin-terraform-version.yml

# Додаємо крок завантаження Go модулів
if ! grep -q "Download Go modules" .github/workflows/pin-terraform-version.yml; then
    # Знаходимо рядок після "Verify Terraform version" і додаємо новий крок
    sed -i '/Verify Terraform version/,/run:/ {
        /run:.*terraform version/a\
\
      - name: Download Go modules\
        run: go mod download
    }' .github/workflows/pin-terraform-version.yml
    echo -e "${GREEN}✅ Додано крок завантаження Go модулів${NC}"
fi

# Застосування виправлень до deploy-environments.yml
echo -e "${YELLOW}🔄 Виправлення deploy-environments.yml...${NC}"

# Оновлення Terraform init
sed -i 's|terraform -chdir=infra/terraform/eks init -backend=false|cd infra/terraform/eks\n          terraform init -backend=false -input=false|' .github/workflows/deploy-environments.yml

# Додавання -recursive до fmt
sed -i 's|terraform -chdir=infra/terraform/eks fmt -check$|terraform -chdir=infra/terraform/eks fmt -check -recursive|' .github/workflows/deploy-environments.yml

# Оновлення версії kustomize
sed -i "s/kustomize-version: '5.4.1'/kustomize-version: '5.4.3'/" .github/workflows/deploy-environments.yml

# Додаємо перевірку версії kustomize
if ! grep -q "Verify kustomize installation" .github/workflows/deploy-environments.yml; then
    sed -i '/Install kustomize/,/kustomize-version:/ {
        /kustomize-version:.*/a\
\
      - name: Verify kustomize installation\
        run: kustomize version
    }' .github/workflows/deploy-environments.yml
    echo -e "${GREEN}✅ Додано перевірку встановлення kustomize${NC}"
fi

echo -e "${GREEN}✅ Всі виправлення застосовано успішно!${NC}"
echo ""
echo -e "${YELLOW}📋 Наступні кроки:${NC}"
echo "1. Перегляньте зміни: git diff .github/workflows/"
echo "2. Зробіть commit: git add .github/workflows/ && git commit -m 'fix: update GitHub Actions workflow versions'"
echo "3. Push зміни: git push origin main"
echo "4. Перевірте Actions у GitHub репозиторії"
echo ""
echo -e "${GREEN}🎉 Готово! Ваші workflow тепер мають працювати правильно.${NC}"
