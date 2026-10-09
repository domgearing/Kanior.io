param([switch]$Desktop, [switch]$Backup)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$gitBash = Join-Path $env:ProgramFiles 'Git\bin\bash.exe'
if (-not (Test-Path -LiteralPath $gitBash)) {
    throw 'Git Bash is required for the local release runner.'
}

Set-Location -LiteralPath $projectRoot
$env:VERELO_GIT_BASH = $gitBash

if ($Desktop) {
    & $gitBash 'scripts/local-release-desktop.sh'
    exit $LASTEXITCODE
}

docker info --format '{{.ServerVersion}}' *> $null
if ($LASTEXITCODE -ne 0) {
    $dockerDesktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (-not (Test-Path -LiteralPath $dockerDesktop)) {
        $dockerDesktop = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe'
    }
    if (-not (Test-Path -LiteralPath $dockerDesktop)) {
        throw 'Docker Desktop is not installed at a supported location.'
    }
    Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
}

$dockerReady = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    docker info --format '{{.ServerVersion}}' *> $null
    if ($LASTEXITCODE -eq 0) {
        $dockerReady = $true
        break
    }
    Start-Sleep -Seconds 3
}
if (-not $dockerReady) {
    throw 'Docker Desktop did not become ready within three minutes.'
}

if ($Backup) {
    & $gitBash 'scripts/local-release-backup.sh'
    exit $LASTEXITCODE
}

& $gitBash 'scripts/local-release-run.sh'
exit $LASTEXITCODE
