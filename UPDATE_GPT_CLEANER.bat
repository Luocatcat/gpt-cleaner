@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1"
if errorlevel 1 echo Update stopped. Read the error above; runtime and local config were preserved.
pause
