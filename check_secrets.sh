#!/bin/bash
# pre-commit hook para evitar subir credenciales
# Instalar: cp check_secrets.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

set -e

echo "🔍 Verificando seguridad antes de commit..."

# Colores
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

# 1. Verificar que .env no está en staging
if git diff --cached --name-only | grep -E "^\.env$"; then
    echo -e "${RED}❌ ERROR CRÍTICO: Intentas subir .env${NC}"
    echo "   Archivo: .env"
    echo "   Esto expone tus credenciales Polar"
    echo ""
    echo "   Solución:"
    echo "   git restore --staged .env"
    echo ""
    ERRORS=$((ERRORS + 1))
fi

# 2. Verificar otros archivos de credenciales
CREDENTIAL_FILES=(
    "\.polar_tokens\.json"
    "\.oauth_code\.txt"
    "tokens\.json"
    "credentials\.json"
    "secrets\.json"
)

for pattern in "${CREDENTIAL_FILES[@]}"; do
    if git diff --cached --name-only | grep -E "$pattern"; then
        echo -e "${RED}❌ ERROR: Intentas subir archivo de credenciales${NC}"
        echo "   Patrón: $pattern"
        ERRORS=$((ERRORS + 1))
    fi
done

# 3. Buscar secrets hardcodeados en código
SECRETS_PATTERNS=(
    "POLAR_CLIENT_SECRET\s*=\s*['\"][a-f0-9-]{30,}['\"]"
    "client_secret\s*=\s*['\"][a-f0-9-]{30,}['\"]"
    "api_key\s*=\s*['\"][a-zA-Z0-9]{32,}['\"]"
    "password\s*=\s*['\"][^'\"]{8,}['\"]"
    "sk_live_[a-zA-Z0-9]{32,}"
    "pk_live_[a-zA-Z0-9]{32,}"
)

for pattern in "${SECRETS_PATTERNS[@]}"; do
    if git diff --cached | grep -iE "$pattern" > /dev/null; then
        echo -e "${YELLOW}⚠️  ADVERTENCIA: Posible secret hardcodeado en código${NC}"
        echo "   Patrón: $pattern"
        echo "   Revisa que no sea una credencial real"
        WARNINGS=$((WARNINGS + 1))
    fi
done

# 4. Verificar que .gitignore existe y tiene .env
if [ ! -f .gitignore ]; then
    echo -e "${RED}❌ ERROR: No existe .gitignore${NC}"
    echo "   Crea .gitignore con .env dentro"
    ERRORS=$((ERRORS + 1))
elif ! grep -q "^\.env$" .gitignore; then
    echo -e "${YELLOW}⚠️  ADVERTENCIA: .env no está en .gitignore${NC}"
    echo "   Agrégalo para evitar subirlo por error"
    WARNINGS=$((WARNINGS + 1))
fi

# 5. Verificar archivos grandes (podría ser CSV con datos sensibles)
LARGE_FILES=$(git diff --cached --name-only | while read file; do
    if [ -f "$file" ]; then
        size=$(wc -c < "$file")
        if [ $size -gt 1048576 ]; then  # 1 MB
            echo "$file"
        fi
    fi
done)

if [ ! -z "$LARGE_FILES" ]; then
    echo -e "${YELLOW}⚠️  ADVERTENCIA: Archivos grandes detectados${NC}"
    echo "$LARGE_FILES"
    echo "   Verifica que no contengan datos sensibles"
    WARNINGS=$((WARNINGS + 1))
fi

# Resumen
echo ""
if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}❌ COMMIT BLOQUEADO${NC}"
    echo -e "${RED}========================================${NC}"
    echo ""
    echo "Encontrados $ERRORS errores críticos"
    echo "Corrige los problemas antes de commit"
    echo ""
    exit 1
elif [ $WARNINGS -gt 0 ]; then
    echo -e "${YELLOW}========================================${NC}"
    echo -e "${YELLOW}⚠️  $WARNINGS ADVERTENCIAS${NC}"
    echo -e "${YELLOW}========================================${NC}"
    echo ""
    echo "Revisa las advertencias antes de continuar"
    echo ""
    read -p "¿Continuar con commit? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Commit cancelado"
        exit 1
    fi
else
    echo -e "${GREEN}✅ Verificación de seguridad OK${NC}"
fi

exit 0
