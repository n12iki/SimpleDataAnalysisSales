# Run once: creates a "Sales Analysis" icon on your Desktop that launches everything.
$root     = Split-Path -Parent $MyInvocation.MyCommand.Path
$target   = Join-Path $root "Launch Sales Analysis.bat"
$icon     = Join-Path $root "assets\sales-analysis.ico"
$desktop  = [Environment]::GetFolderPath("Desktop")   # also works with OneDrive-redirected desktops
$lnkPath  = Join-Path $desktop "Sales Analysis.lnk"

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($lnkPath)
$lnk.TargetPath       = $target
$lnk.WorkingDirectory = $root
$lnk.IconLocation     = "$icon,0"
$lnk.WindowStyle      = 1        # 1 = normal (shows build progress), 7 = minimized
$lnk.Description      = "Launch Sales & Inventory Analysis"
$lnk.Save()

Write-Host "Shortcut created: $lnkPath"
