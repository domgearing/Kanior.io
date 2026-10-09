$ErrorActionPreference = 'Stop'
$taskNames = @('Verelo Local Release', 'Verelo Desktop')
foreach ($taskName in $taskNames) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        throw "Task '$taskName' already exists; inspect it before replacing it."
    }
}

$runner = (Resolve-Path (Join-Path $PSScriptRoot 'start-local-release.ps1')).Path
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
$backendAction = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $runner) `
    -WorkingDirectory $projectRoot
$desktopAction = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -Desktop' -f $runner) `
    -WorkingDirectory $projectRoot
Register-ScheduledTask -TaskName $taskNames[0] -Action $backendAction -Trigger $trigger `
    -Principal $principal -Settings $settings -Description 'Starts the single-user Verelo API and worker at sign-in.' | Out-Null
try {
    Register-ScheduledTask -TaskName $taskNames[1] -Action $desktopAction -Trigger $trigger `
        -Principal $principal -Settings $settings -Description 'Opens Verelo Capture after the API becomes ready.' | Out-Null
} catch {
    Unregister-ScheduledTask -TaskName $taskNames[0] -Confirm:$false
    throw
}
$tunnel = Get-Service -Name 'cloudflared' -ErrorAction SilentlyContinue
if (-not $tunnel -or $tunnel.StartType -ne 'Automatic') {
    Write-Warning 'Set the existing cloudflared service to Automatic; the Verelo tasks do not install a tunnel.'
}
Write-Output "Installed both Verelo sign-in tasks for $userId. They will start at the next sign-in."
