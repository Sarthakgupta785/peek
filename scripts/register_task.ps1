# Registers the "Peek" scheduled task: starts at log on, no console window,
# restarts on failure, no time limit. Runs as the logged-on user (not a service:
# services run in session 0 and can't take screenshots or see your apps).

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
$script = Join-Path $root "guardian.py"
$taskName = "Peek"
$user = "$env:USERDOMAIN\$env:USERNAME"

if (-not (Test-Path $pythonw)) { throw "pythonw.exe not found at $pythonw - run setup.bat first." }

$action = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$script`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

try {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
        -Principal $principal -Description "Peek - see what this PC is doing from your phone." -Force | Out-Null
} catch {
    Write-Host "Could not register the task: $($_.Exception.Message)"
    Write-Host "Right-click setup.bat and choose 'Run as administrator', then try again."
    exit 1
}

# Remove the task from before the rename to Peek, if present.
if (Get-ScheduledTask -TaskName "PC Guardian" -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName "PC Guardian" -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName "PC Guardian" -Confirm:$false
}

# Start it now (the single-instance mutex makes a second copy exit by itself).
Start-ScheduledTask -TaskName $taskName
Write-Host "Task '$taskName' registered and started."
