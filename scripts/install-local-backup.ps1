$ErrorActionPreference = 'Stop'
$taskName = 'Verelo Local Backup'
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Write-Output "Task '$taskName' already exists; no changes made."
    exit 0
}

$runner = (Resolve-Path (Join-Path $PSScriptRoot 'start-local-release.ps1')).Path
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$trigger = New-ScheduledTaskTrigger -Daily -At '03:00'
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 12) `
    -MultipleInstances IgnoreNew
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -Backup' -f $runner) `
    -WorkingDirectory $projectRoot
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings `
    -Description 'Creates and verifies the single-user Verelo database and object backup.' | Out-Null
Write-Output "Installed '$taskName' for $userId. It runs daily at 03:00 when the user session is available."
