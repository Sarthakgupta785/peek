# Removes the Peek scheduled task and stops it. Your data folder is kept.
#   powershell -ExecutionPolicy Bypass -File uninstall.ps1

foreach ($taskName in @("Peek", "PC Guardian")) {   # "PC Guardian" = name before the rename
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Removed scheduled task '$taskName'."
    }
}

# Remove Peek's notification identity.
Remove-Item -Path "HKCU:\Software\Classes\AppUserModelId\Peek.Monitor" -Recurse -ErrorAction SilentlyContinue

# Stop a copy that is still running.
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { $_.CommandLine -like "*guardian.py*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host "Stopped Peek (pid $($_.ProcessId))." }
Write-Host "Done. Delete this folder to remove everything (the 'data' folder holds your history)."
