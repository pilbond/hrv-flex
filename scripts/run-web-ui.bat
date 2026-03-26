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

"%PYTHON_CMD%" -c "import flask, flask_cors, requests, werkzeug" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Faltan dependencias para arrancar la Web UI.
  echo Instala requirements_web.txt en .venv o en el Python actual.
  echo Ejemplo:
  echo   python -m venv .venv
  echo   .\.venv\Scripts\Activate.ps1
  echo   pip install -r requirements_web.txt
  exit /b 1
)

if "%PORT%"=="" set "PORT=8080"
if "%POLAR_TOKEN_PATH%"=="" set "POLAR_TOKEN_PATH=%cd%\.polar_tokens.json"

echo Iniciando Polar HRV Web UI...
echo URL: http://localhost:%PORT%
echo.
"%PYTHON_CMD%" web_ui.py

pause

endlocal
