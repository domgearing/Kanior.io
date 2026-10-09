param([Parameter(Mandatory = $true)][string]$Uri)

$ErrorActionPreference = 'Stop'
if ($Uri -ne 'verelo-recorder://open' -and $Uri -ne 'verelo-recorder://open/') {
    throw 'Unsupported Verelo desktop link.'
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$gitBash = Join-Path $env:ProgramFiles 'Git\bin\bash.exe'
if (-not (Test-Path -LiteralPath $gitBash)) {
    throw 'Git Bash is required to launch the Verelo desktop recorder.'
}

Set-Location -LiteralPath $projectRoot
& $gitBash 'scripts/local-release-desktop.sh'
exit $LASTEXITCODE
