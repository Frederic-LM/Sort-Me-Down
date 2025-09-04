# PowerShell Build Script for SortMeDown (Final Lean Edition)
# Run with: powershell -ExecutionPolicy Bypass -File build.ps1

Clear-Host
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host " Sort-Me-Down PyInstaller Build Script (Lean Edition) " -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

# --- Configuration ---
$VenvName = "venv"
$PythonCmd = "python"
$AppName = "SortMeDown"
# --- IMPORTANT: UPDATE THIS PATH TO WHERE YOU UNZIPPED UPX ---
$UpxPath = "C:\Tools\upx-4.2.4-win64"

# --- Script Start ---
$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptPath
Write-Host "Working directory: $(Get-Location)" -ForegroundColor Green
Write-Host ""

# 1. Clean up old build artifacts
Write-Host "[1/5] Cleaning up old build artifacts..." -ForegroundColor Yellow
if (Test-Path "dist") { Remove-Item "dist" -Recurse -Force }
if (Test-Path "build") { Remove-Item "build" -Recurse -Force }
if (Test-Path $VenvName) { Remove-Item $VenvName -Recurse -Force }
Get-ChildItem "*.spec" | Remove-Item -Force -ErrorAction SilentlyContinue
Write-Host "   > Done." -ForegroundColor Green
Write-Host ""

# 2. Create and activate virtual environment
Write-Host "[2/5] Creating and activating virtual environment..." -ForegroundColor Yellow
try {
    & $PythonCmd -m venv $VenvName
    $ActivateScript = Join-Path $VenvName "Scripts\Activate.ps1"
    & $ActivateScript
    Write-Host "   > Virtual environment created and activated." -ForegroundColor Green
} catch {
    Write-Host "ERROR: Failed to create or activate virtual environment." -ForegroundColor Red
    Read-Host "Press Enter to exit"; exit 1
}
Write-Host ""

# 3. Install packages from requirements.txt
Write-Host "[3/5] Installing required packages..." -ForegroundColor Yellow
try {
    & python -m pip install --upgrade pip
    & python -m pip install -r requirements.txt
    Write-Host "   > Packages installed successfully." -ForegroundColor Green
} catch {
    Write-Host "ERROR: Failed to install packages. Check your internet connection." -ForegroundColor Red
    Read-Host "Press Enter to exit"; exit 1
}
Write-Host ""

# 4. Run PyInstaller with all optimizations
Write-Host "[4/5] Running PyInstaller to build executable..." -ForegroundColor Yellow
$PyInstallerArgs = @(
    "--onefile",
    "--windowed",
    "--name=$AppName",
    "--icon=icon.ico",
    "--upx-dir=$UpxPath", # Compress the EXE
    
    # Hidden imports for libraries PyInstaller might miss
    "--hidden-import=pystray._win32",
    "--hidden-import=PIL._tkinter_finder",
    
    # Bundle helper scripts and icons
    "--add-data=create_shortcut.ps1;.",
    "--add-data=send_notification.ps1;.",
    "--add-data=icon.ico;.",
    "--add-data=icon.png;.",

    # Exclude large, unneeded libraries to reduce file size
    "--exclude-module=tkinter",
    "--exclude-module=sqlite3",
    "--exclude-module=unittest",

    "--clean",
    "--noconfirm",
    "gui.py"
)

try {
    & pyinstaller $PyInstallerArgs
    Write-Host "   > Build process completed." -ForegroundColor Green
} catch {
    Write-Host "ERROR: PyInstaller failed." -ForegroundColor Red
    Read-Host "Press Enter to exit"; exit 1
}
Write-Host ""

# 5. Cleanup temporary files
Write-Host "[5/5] Cleaning up temporary build files..." -ForegroundColor Yellow
if (Test-Path "build") { Remove-Item "build" -Recurse -Force }
Get-ChildItem "*.spec" | Remove-Item -Force -ErrorAction SilentlyContinue
Write-Host "   > Done." -ForegroundColor Green
Write-Host ""

# Verify build success
if (Test-Path "dist\$AppName.exe") {
    $FileSizeMB = [math]::Round((Get-Item "dist\$AppName.exe").Length / 1MB, 2)
    Write-Host "=========================================" -ForegroundColor Green
    Write-Host " BUILD SUCCESSFUL! " -ForegroundColor Green
    Write-Host " Executable: dist\$AppName.exe" -ForegroundColor Green
    Write-Host " Size: $FileSizeMB MB" -ForegroundColor Green
    Write-Host "=========================================" -ForegroundColor Green
} else {
    Write-Host "=========================================" -ForegroundColor Red
    Write-Host " BUILD FAILED! " -ForegroundColor Red
    Write-Host " No executable found in 'dist' folder." -ForegroundColor Red
    Write-Host "=========================================" -ForegroundColor Red
}

Write-Host ""
Write-Host "You can find your executable in the 'dist' folder." -ForegroundColor Cyan
Write-Host ""
Read-Host "Press Enter to exit"