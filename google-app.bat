@echo off
rem Use your own Google sign-in app. Peek restarts itself after saving.
cd /d "%~dp0"
".venv\Scripts\python.exe" guardian.py --set-google-app
pause
