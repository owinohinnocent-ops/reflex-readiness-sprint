@echo off
setlocal
cd /d "%~dp0"
echo Starting Reflex frontend...
node frontend\server.mjs
if errorlevel 1 (
  echo.
  echo Reflex could not start. Confirm that Node.js is installed and try again.
)
pause
