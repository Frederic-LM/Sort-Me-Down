# create_shortcut.ps1
param(
    [string]$Action,      # "Create" or "Delete"
    [string]$ShortcutName,
    [string]$AppPath,
    [string]$AppArgs
)

$Shell = New-Object -ComObject WScript.Shell
$StartupFolderPath = $Shell.SpecialFolders.Item("Startup")
$ShortcutPath = Join-Path -Path $StartupFolderPath -ChildPath "$ShortcutName.lnk"

if ($Action -eq "Create") {
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $AppPath
    $Shortcut.Arguments = $AppArgs
    $Shortcut.WorkingDirectory = Split-Path -Parent $AppPath
    $Shortcut.IconLocation = $AppPath
    $Shortcut.Save()
}
elseif ($Action -eq "Delete") {
    if (Test-Path $ShortcutPath) {
        Remove-Item $ShortcutPath -Force
    }
}