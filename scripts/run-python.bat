@echo off
setlocal

set "ROOT_DIR=%~dp0.."
cd /d "%ROOT_DIR%"

python polar_hrv_automation.py --process

pause

endlocal
