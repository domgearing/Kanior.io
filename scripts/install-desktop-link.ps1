$ErrorActionPreference = 'Stop'

$scheme = 'HKCU:\Software\Classes\verelo-recorder'
$commandKey = Join-Path $scheme 'shell\open\command'
$handler = (Resolve-Path (Join-Path $PSScriptRoot 'open-desktop-link.ps1')).Path
$powershellExe = Join-Path $PSHOME 'powershell.exe'
$command = '"{0}" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{1}" "%1"' -f $powershellExe, $handler

if (Test-Path -LiteralPath $commandKey) {
    $existing = (Get-Item -LiteralPath $commandKey).GetValue('')
    if ($existing -and $existing -ne $command) {
        throw 'verelo-recorder is already registered to a different command; inspect the per-user protocol handler before replacing it.'
    }
}

New-Item -Path $scheme -Force | Out-Null
Set-Item -Path $scheme -Value 'URL:Verelo Desktop Recorder'
New-ItemProperty -Path $scheme -Name 'URL Protocol' -PropertyType String -Value '' -Force | Out-Null
New-Item -Path $commandKey -Force | Out-Null
Set-Item -Path $commandKey -Value $command
Write-Output 'Registered verelo-recorder://open for this Windows user.'
