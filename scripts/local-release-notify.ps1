param([Parameter(Mandatory = $true)][string]$Message)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$notification = New-Object System.Windows.Forms.NotifyIcon
try {
    $notification.Icon = [System.Drawing.SystemIcons]::Warning
    $notification.Visible = $true
    $notification.BalloonTipTitle = 'Verelo needs attention'
    $notification.BalloonTipText = $Message
    $notification.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Warning
    $notification.ShowBalloonTip(8000)
    Start-Sleep -Seconds 9
} finally {
    $notification.Dispose()
}
