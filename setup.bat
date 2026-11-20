@echo off
rem Peek setup for Windows.
rem   setup.bat              normal interactive setup
rem   setup.bat --no-prompt  skip the password question (set it later with set-password.bat)
setlocal
cd /d "%~dp0"
set "NOPROMPT="
if /i "%~1"=="--no-prompt" set "NOPROMPT=1"

echo.
echo === Peek setup ===
echo.

rem ---- 1. Find Python 3.10+
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python was not found. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during install. Then run setup.bat again.
  goto :fail
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
  echo Python 3.10 or newer is needed. Install the latest from https://www.python.org/downloads/
  goto :fail
)

rem ---- 2. Virtual environment + packages
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PY% -m venv .venv || goto :fail
)
echo Installing packages (this can take a minute)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail

rem ---- 3. Dashboard password
".venv\Scripts\python.exe" guardian.py --has-password
if errorlevel 1 (
  if defined NOPROMPT (
    echo.
    echo NOTE: no dashboard password yet. Run set-password.bat to choose one.
  ) else (
    ".venv\Scripts\python.exe" guardian.py --set-password || goto :fail
  )
) else (
  echo A dashboard password is already set. Run set-password.bat to change it.
)

rem ---- 4. Start at log on (Task Scheduler)
echo Registering the "Peek" task to start when you log on...
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\register_task.ps1" || goto :fail

rem ---- 5. Tailscale
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\tailscale_serve.ps1"

echo.
echo === Done ===
echo Local test address (this PC only): http://127.0.0.1:8765
echo Logs: %~dp0guardian.log
echo.
if not defined NOPROMPT pause
exit /b 0

:fail
echo.
echo Setup did not finish. Scroll up to see what went wrong.
if not defined NOPROMPT pause
exit /b 1
