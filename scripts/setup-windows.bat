@echo off
setlocal EnableExtensions

rem Bootstrap de Windows para Polar HRV Automation V4
rem - crea o reutiliza .venv
rem - instala dependencias
rem - prepara .env y carpetas de trabajo
rem - deja el proyecto listo para arrancar

set "ROOT_DIR=%~dp0.."
cd /d "%ROOT_DIR%"

set "PYTHON_EXE="
set "PYTHON_ARGS="

if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=.venv\Scripts\python.exe"
  echo [INFO] Usando entorno virtual local: .venv
) else (
  where python >nul 2>&1
  if not errorlevel 1 (
    set "PYTHON_EXE=python"
  ) else (
    where py >nul 2>&1
    if not errorlevel 1 (
      set "PYTHON_EXE=py"
      set "PYTHON_ARGS=-3"
    )
  )
)

if not defined PYTHON_EXE (
  echo [ERROR] No se encontro Python en el sistema.
  echo Instala Python 3.11 desde https://www.python.org/downloads/ y vuelve a ejecutar este script.
  pause
  exit /b 1
)

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo.
echo [1/5] Verificando Python...
"%PYTHON_EXE%" %PYTHON_ARGS% --version
if errorlevel 1 (
  echo [ERROR] Python no responde correctamente.
  pause
  exit /b 1
)

echo.
echo [2/5] Creando entorno virtual si no existe...
if not exist ".venv\Scripts\python.exe" (
  "%PYTHON_EXE%" %PYTHON_ARGS% -m venv .venv
  if errorlevel 1 (
    echo [ERROR] No se pudo crear el entorno virtual .venv.
    pause
    exit /b 1
  )
  set "PYTHON_EXE=.venv\Scripts\python.exe"
  set "PYTHON_ARGS="
)

echo.
echo [3/5] Actualizando pip e instalando dependencias...
"%PYTHON_EXE%" %PYTHON_ARGS% -m pip install --upgrade pip
if errorlevel 1 (
  echo [ERROR] No se pudo actualizar pip.
  pause
  exit /b 1
)

"%PYTHON_EXE%" %PYTHON_ARGS% -m pip install -r requirements_web.txt
if errorlevel 1 (
  echo [ERROR] No se pudieron instalar las dependencias.
  pause
  exit /b 1
)

echo.
echo [4/5] Preparando configuracion y carpetas...
if not exist "data" mkdir data
if not exist "data\rr_downloads" mkdir data\rr_downloads

if not exist ".env" (
  if exist ".env.example" (
    copy /Y ".env.example" ".env" >nul
    echo [INFO] Se ha creado .env desde .env.example
  ) else (
    echo [WARN] No existe .env ni .env.example
  )
) else (
  echo [INFO] .env ya existe
)

echo.
echo [5/5] Comprobando instalacion minima...
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import flask, flask_cors, requests, pandas, numpy, scipy, dotenv; print('OK')"
if errorlevel 1 (
  echo [ERROR] La validacion de dependencias fallo.
  pause
  exit /b 1
)

echo.
echo ========================================
echo  Setup completado
echo ========================================
echo.
echo Proximos pasos:
echo   1. Edita .env con tus credenciales reales de Polar
echo   2. Ejecuta scripts\run-web-ui.bat para abrir la UI
echo   3. O ejecuta scripts\run-python.bat para lanzar el proceso HRV
echo.
pause

endlocal
