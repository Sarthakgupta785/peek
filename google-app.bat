@echo off
rem Use your own Google sign-in app (shows "Peek" instead of "ngrok.com").
cd /d "%~dp0"
".venv\Scripts\python.exe" guardian.py --set-google-app
if errorlevel 1 goto :done
schtasks /end /tn "Peek" >/dev/null 2>nul
timeout /t 3 /nobreak >nul
schtasks /run /tn "Peek" >nul
echo Peek restarted. Remote access is back within about a minute.
:done
pause
