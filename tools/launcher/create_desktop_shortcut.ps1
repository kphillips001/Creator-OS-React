[CmdletBinding()]
param(
    [string]$ProjectRoot
)

$ErrorActionPreference = "Stop"
if (-not $ProjectRoot) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}
$ApplicationName = "Creator_OS"
$LauncherPath = Join-Path $ProjectRoot "Creator_OS.exe"
$DesktopPath = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
$ShortcutPath = Join-Path $DesktopPath "$ApplicationName.lnk"

if (Test-Path -LiteralPath $ShortcutPath -PathType Leaf) {
    Write-Host "Existing Creator_OS Desktop shortcut reused." -ForegroundColor Green
    return
}

if (-not (Test-Path -LiteralPath $LauncherPath -PathType Leaf)) {
    throw "Creator_OS launcher was not found at '$LauncherPath'."
}

if (-not $DesktopPath -or -not (Test-Path -LiteralPath $DesktopPath -PathType Container)) {
    throw "The current user's Desktop folder could not be resolved."
}

$iconPath = Join-Path $ProjectRoot "assets\icons\Creator_OS.ico"
if (-not (Test-Path -LiteralPath $iconPath -PathType Leaf)) {
    $iconPath = $null
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = $LauncherPath
$shortcut.WorkingDirectory = $ProjectRoot
$shortcut.Description = $ApplicationName
if ($iconPath) {
    $shortcut.IconLocation = "$iconPath,0"
}
$shortcut.Save()

Write-Host "New Creator_OS Desktop shortcut created." -ForegroundColor Green
