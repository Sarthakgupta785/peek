@echo off
rem Stop Peek and ngrok COMPLETELY (e.g. before an online exam). Undo with resume-peek.bat.
schtasks /change /tn "Peek" /disable >nul 2>nul
schtasks /end /tn "Peek" >nul 2>nul
taskkill /f /fi "IMAGENAME eq ngrok.exe" >nul 2>nul
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' OR Name='python.exe'\" | Where-Object { $_.CommandLine -like '*guardian.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo.
echo Peek is PAUSED. Nothing of Peek or ngrok is running, and it will NOT start
echo again at sign-in until you run resume-peek.bat.
echo.
pause
