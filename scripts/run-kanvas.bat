@echo off
setlocal

rem Abre el tablero Kanvas (kanvas.json) en el navegador, con el parche local
rem que abre los .md enlazados de docs/ y research/reports/.
rem Argumentos extra se pasan a "kanvas.py serve" (p.ej. --port 8790 o --no-open).

set "ROOT_DIR=%~dp0.."
cd /d "%ROOT_DIR%"

set "PYTHON_CMD=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_CMD=.venv\Scripts\python.exe"

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if not exist ".agents\skills\kanvas\kanvas.py" (
  echo [ERROR] No se encontro .agents\skills\kanvas\kanvas.py
  echo Instala Kanvas con:  uvx kanvas-board init
  pause
  exit /b 1
)

rem Reaplica el parche (idempotente): repara la copia si un init o update la sobrescribio.
"%PYTHON_CMD%" scripts\kanvas_docs_patch.py
if errorlevel 1 (
  echo [WARN] No se pudo aplicar el parche de documentos; el tablero abrira sin enlaces a .md.
)

echo.
echo Iniciando Kanvas...
echo Si ya habia un Kanvas abierto, el tablero se abre en ese y esta ventana termina.
echo Para cargar cambios del parche en el servidor, cierra primero el Kanvas anterior.
echo.
"%PYTHON_CMD%" .agents\skills\kanvas\kanvas.py serve %*

pause
endlocal
