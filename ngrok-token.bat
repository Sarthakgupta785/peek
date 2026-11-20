@echo off
rem Saves your ngrok authtoken into ngrok's own config (not into Peek).
cd /d "%~dp0"
set "NGROK="
for /f "usebackq delims=" %%P in (`.venv\Scripts\python.exe -c "from pcguardian import tunnel; print(tunnel.find_exe() or '')"`) do set "NGROK=%%P"
if not defined NGROK (
  echo ngrok was not found. Install it first: winget install Ngrok.Ngrok
  pause
  exit /b 1
)
echo Copy your authtoken from https://dashboard.ngrok.com/get-started/your-authtoken
echo Paste just the token, or the whole "ngrok config add-authtoken ..." line - both work.
echo Right-click pastes. Then press Enter:
set /p TOKEN=Token: 
rem Keep only the last word, so a pasted full command still works.
set "LAST="
for %%W in (%TOKEN%) do set "LAST=%%W"
"%NGROK%" config add-authtoken %LAST%
set "TOKEN="
set "LAST="
echo.
echo Peek reconnects by itself within about a minute.
pause
