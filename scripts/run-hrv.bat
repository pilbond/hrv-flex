@echo off
setlocal

set "ROOT_DIR=%~dp0.."
cd /d "%ROOT_DIR%"

set "PYTHON_CMD=python"

if exist ".venv\Scripts\python.exe" (
  set "PYTHON_CMD=.venv\Scripts\python.exe"
  echo [INFO] Usando entorno virtual local: .venv
) else (
  echo [WARN] No se encontro .venv. Se usara el Python disponible en PATH.
)

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

"%PYTHON_CMD%" -c "import requests, pandas, numpy, scipy" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Faltan dependencias para ejecutar el pipeline HRV.
  echo Instala requirements_web.txt en .venv o en el Python actual.
  echo Ejemplo:
  echo   python -m venv .venv
  echo   .\.venv\Scripts\Activate.ps1
  echo   pip install -r requirements_web.txt
  exit /b 1
)

echo Iniciando Polar HRV Automation...
"%PYTHON_CMD%" polar_hrv_automation.py --process

pause

endlocal
