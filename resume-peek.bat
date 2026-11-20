@echo off
rem Start Peek again after pause-peek.bat.
schtasks /change /tn "Peek" /enable >nul
schtasks /run /tn "Peek" >nul
echo.
echo Peek is RUNNING again. Remote access is back within about a minute.
echo.
pause
