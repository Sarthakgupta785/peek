@echo off
rem Lets Peek notice wrong Windows passwords/PINs typed at this PC (Security log, event 4625).
rem It adds your account to Windows' built-in "Event Log Readers" group (read-only access to logs).
rem Run it with right-click > "Run as administrator". Undo: net localgroup "Event Log Readers" %USERNAME% /delete

net session >nul 2>&1
if errorlevel 1 (
  echo This needs administrator rights.
  echo Close this window, right-click enable-intruder-photos.bat and choose "Run as administrator".
  pause
  exit /b 1
)

net localgroup "Event Log Readers" "%USERNAME%" /add
echo.
echo Done. Now SIGN OUT of Windows and sign back in (or restart) so it takes effect.
echo After that, Peek takes a webcam photo when someone types a wrong password on the lock screen.
pause
