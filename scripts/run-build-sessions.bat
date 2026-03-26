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

if "%~1"=="" (
  echo Ejecutando build_sessions.py --update
  "%PYTHON_CMD%" build_sessions.py --update
) else (
  echo Ejecutando build_sessions.py %*
  "%PYTHON_CMD%" build_sessions.py %*
)

pause

endlocal
