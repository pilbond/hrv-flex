#!/bin/bash
# -*- coding: utf-8 -*-
#
# QUICK SETUP - Polar HRV Automation
# ===================================
# Instala y configura todo automáticamente
#
# Uso:
#   chmod +x setup_polar_hrv.sh
#   ./setup_polar_hrv.sh

set -e  # Exit on error

echo ""
echo "========================================"
echo "  POLAR HRV AUTOMATION - QUICK SETUP"
echo "========================================"
echo ""

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Verificar Python
echo "1️⃣  Verificando Python..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 no encontrado${NC}"
    echo "   Instala Python 3.10+ desde: https://www.python.org/"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo -e "${GREEN}✅ Python $PYTHON_VERSION instalado${NC}"

# 2. Verificar pip
echo ""
echo "2️⃣  Verificando pip..."
if ! command -v pip3 &> /dev/null; then
    echo -e "${RED}❌ pip no encontrado${NC}"
    exit 1
fi
echo -e "${GREEN}✅ pip instalado${NC}"

# 3. Crear entorno virtual (opcional pero recomendado)
echo ""
echo "3️⃣  Configurando entorno virtual..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✅ Entorno virtual creado${NC}"
else
    echo -e "${YELLOW}⚠️  Entorno virtual ya existe${NC}"
fi

# Activar entorno
source venv/bin/activate

# 4. Instalar dependencias
echo ""
echo "4️⃣  Instalando dependencias..."
pip install --quiet --upgrade pip
pip install --quiet requests pandas numpy python-dotenv

echo -e "${GREEN}✅ Dependencias instaladas:${NC}"
pip list | grep -E "requests|pandas|numpy|python-dotenv"

# 5. Configurar .env
echo ""
echo "5️⃣  Configurando credenciales..."

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "✅ Archivo .env creado desde .env.example"
        echo "⚠️  EDITA .env con tus credenciales reales"
    fi
fi

# 6. Verificar archivos necesarios
echo ""
echo "6️⃣  Verificando archivos..."

if [ ! -f "endurance_hrv.py" ]; then
    echo -e "${RED}❌ No se encuentra endurance_hrv.py${NC}"
    echo "   Copia tu script Python de procesamiento HRV aquí"
    exit 1
fi
echo -e "${GREEN}✅ endurance_hrv.py encontrado${NC}"

if [ ! -f "polar_hrv_automation.py" ]; then
    echo -e "${RED}❌ No se encuentra polar_hrv_automation.py${NC}"
    exit 1
fi
echo -e "${GREEN}✅ polar_hrv_automation.py encontrado${NC}"

# 7. Crear directorios necesarios
echo ""
echo "7️⃣  Creando directorios..."
mkdir -p rr_downloads
mkdir -p logs
echo -e "${GREEN}✅ Directorios creados${NC}"

# 8. Verificar master CSV
echo ""
echo "8️⃣  Verificando archivos Master CSV..."

if [ ! -f "ENDURANCE_HRV_master_ALL.csv" ]; then
    echo -e "${YELLOW}⚠️  ENDURANCE_HRV_master_ALL.csv no encontrado${NC}"
    echo "   Se creará automáticamente en la primera ejecución"
fi

if [ ! -f "ENDURANCE_HRV_eval_P1P2_ALL.csv" ]; then
    echo -e "${YELLOW}⚠️  ENDURANCE_HRV_eval_P1P2_ALL.csv no encontrado${NC}"
    echo "   Se creará automáticamente en la primera ejecución"
fi

# 9. Test rápido de API
echo ""
echo "9️⃣  Testeando conexión con Polar..."
echo ""
echo -e "${YELLOW}Se abrirá tu navegador para autorizar la aplicación.${NC}"
echo "Presiona ENTER para continuar o Ctrl+C para cancelar..."
read

python3 polar_hrv_automation.py --auth

# 10. Finalizar
echo ""
echo "========================================"
echo "  ✅ SETUP COMPLETADO"
echo "========================================"
echo ""
echo "📋 Próximos pasos:"
echo ""
echo "1. Activar entorno virtual:"
echo "   source venv/bin/activate"
echo ""
echo "2. Procesar últimos 7 días:"
echo "   python3 polar_hrv_automation.py"
echo ""
echo "3. Ver ayuda:"
echo "   python3 polar_hrv_automation.py --help"
echo ""
echo "4. Testear API:"
echo "   python3 polar_api_tester.py"
echo ""
echo "🔗 Para más info: GUIA_AUTOMATIZACION_POLAR.md"
echo ""
