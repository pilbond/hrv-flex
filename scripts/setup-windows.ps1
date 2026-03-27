$ErrorActionPreference = 'Stop'

function Write-Step {
  param(
    [int]$Number,
    [string]$Title
  )

  Write-Host ""
  Write-Host ("[{0}/5] {1}" -f $Number, $Title)
}

function Resolve-Python {
  if (Test-Path -LiteralPath ".venv\Scripts\python.exe") {
    Write-Host "[INFO] Usando entorno virtual local: .venv"
    return [pscustomobject]@{
      Exe  = ".venv\Scripts\python.exe"
      Args = @()
    }
  }

  $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
  if ($null -ne $pythonCmd) {
    return [pscustomobject]@{
      Exe  = "python"
      Args = @()
    }
  }

  $pyCmd = Get-Command py -ErrorAction SilentlyContinue
  if ($null -ne $pyCmd) {
    return [pscustomobject]@{
      Exe  = "py"
      Args = @("-3")
    }
  }

  throw "No se encontro Python en el sistema. Instala Python 3.11 desde https://www.python.org/downloads/ y vuelve a ejecutar este script."
}

function Invoke-Python {
  param(
    [Parameter(Mandatory = $true)]
    [pscustomobject]$Python,
    [Parameter(Mandatory = $true)]
    [string[]]$Arguments
  )

  $invokeArgs = @()
  if ($Python.Args) {
    $invokeArgs += $Python.Args
  }
  if ($Arguments) {
    $invokeArgs += $Arguments
  }

  & $Python.Exe @invokeArgs
  if ($LASTEXITCODE -ne 0) {
    throw "El comando Python fallo: $($Python.Exe) $((@($Python.Args) + @($Arguments)) -join ' ')"
  }
}

$rootDir = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location $rootDir

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

try {
  $python = Resolve-Python

  Write-Step 1 "Verificando Python"
  Invoke-Python -Python $python -Arguments @("--version")

  Write-Step 2 "Creando entorno virtual si no existe"
  if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    Invoke-Python -Python $python -Arguments @("-m", "venv", ".venv")
    $python = [pscustomobject]@{
      Exe  = ".venv\Scripts\python.exe"
      Args = @()
    }
  }

  Write-Step 3 "Actualizando pip e instalando dependencias"
  Invoke-Python -Python $python -Arguments @("-m", "pip", "install", "--upgrade", "pip")
  Invoke-Python -Python $python -Arguments @("-m", "pip", "install", "-r", "requirements_web.txt")

  Write-Step 4 "Preparando configuracion y carpetas"
  if (-not (Test-Path -LiteralPath "data")) {
    New-Item -ItemType Directory -Path "data" | Out-Null
  }
  if (-not (Test-Path -LiteralPath "data\rr_downloads")) {
    New-Item -ItemType Directory -Path "data\rr_downloads" | Out-Null
  }

  if (-not (Test-Path -LiteralPath ".env")) {
    if (Test-Path -LiteralPath ".env.example") {
      Copy-Item -LiteralPath ".env.example" -Destination ".env" -Force
      Write-Host "[INFO] Se ha creado .env desde .env.example"
    }
    else {
      Write-Host "[WARN] No existe .env ni .env.example"
    }
  }
  else {
    Write-Host "[INFO] .env ya existe"
  }

  Write-Step 5 "Comprobando instalacion minima"
  Invoke-Python -Python $python -Arguments @(
    "-c",
    "import flask, flask_cors, requests, pandas, numpy, scipy, dotenv; print('OK')"
  )

  Write-Host ""
  Write-Host "========================================"
  Write-Host " Setup completado"
  Write-Host "========================================"
  Write-Host ""
  Write-Host "Proximos pasos:"
  Write-Host "  1. Edita .env con tus credenciales reales de Polar"
  Write-Host "  2. Ejecuta scripts\run-web-ui.bat para abrir la UI"
  Write-Host "  3. O ejecuta scripts\run-python.bat para lanzar el proceso HRV"
  Write-Host ""
}
catch {
  Write-Host ""
  Write-Host "[ERROR] $($_.Exception.Message)"
  exit 1
}
