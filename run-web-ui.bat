@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
  echo [ERROR] No se encontro el entorno virtual en .venv
  echo Ejecuta una vez:
  echo   python -m venv .venv
  echo   .\.venv\Scripts\Activate.ps1
  echo   pip install -r requirements_web.txt
  exit /b 1
)

call ".venv\Scripts\activate.bat"

if "%PORT%"=="" set "PORT=8080"
if "%POLAR_TOKEN_PATH%"=="" set "POLAR_TOKEN_PATH=%cd%\.polar_tokens.json"

echo Iniciando Polar HRV Web UI...
echo URL: http://localhost:%PORT%
echo.
python web_ui.py

endlocal
