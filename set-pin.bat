@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" guardian.py --set-pin
pause
