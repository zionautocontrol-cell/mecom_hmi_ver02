<#
.SYNOPSIS
    MECOM HMI -- One-click installer
.DESCRIPTION
    Installs Python if missing, pip packages, creates startup files and desktop shortcut
.NOTES
    Run as Administrator for best results
#>

$ErrorActionPreference = "Stop"

function Write-Color($Color, $Text) {
    Write-Host $Text -ForegroundColor $Color
}

Write-Color Cyan "============================================"
Write-Color Cyan "  MECOM HMI - Installer"
Write-Color Cyan "============================================"
Write-Host ""

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PROJECT_DIR = $SCRIPT_DIR

# ---- 1. Check Python ----
Write-Color Yellow "[1/5] Checking Python..."

$python = $null
try { $python = python --version 2>&1 } catch {}
if (-not $python) { try { $python = py --version 2>&1 } catch {} }

if ($python -and $python -match "Python 3\.(\d+)") {
    $ver = [int]$Matches[1]
    if ($ver -lt 8) {
        Write-Color Yellow "  Python 3.8+ required (found: $python), installing..."
        $need_python = $true
    } else {
        Write-Color Green "  Found $python"
        $need_python = $false
    }
} else {
    Write-Color Yellow "  Python not found, installing Python 3.12..."
    $need_python = $true
}

if ($need_python) {
    $url = "https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe"
    $installer = "$env:TEMP\python-installer.exe"
    Write-Color Yellow "  Downloading Python..."
    try {
        Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
    } catch {
        Write-Color Red "  Download failed. Install Python manually from python.org"
        Write-Color Red "  (check 'Add Python to PATH')"
        Read-Host "  Press Enter after installing Python"
    }
    if (Test-Path $installer) {
        Write-Color Yellow "  Installing Python (this may take a minute)..."
        Start-Process -FilePath $installer -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1" -Wait
        Remove-Item $installer -Force
        $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
        $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
        $env:Path = "$machinePath;$userPath"
        Write-Color Green "  Python installed"
    }
}

# ---- 2. Install libraries ----
Write-Color Yellow "[2/5] Installing Python libraries..."
$pip_cmd = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "py" }
try {
    & $pip_cmd -m pip install --upgrade pip -q
    & $pip_cmd -m pip install -r "$PROJECT_DIR\requirements.txt" -q
    Write-Color Green "  Libraries installed"
} catch {
    Write-Color Red "  Error: $_"
    Write-Color Yellow "  Manual: pip install -r requirements.txt"
}

# ---- 3. COM port config ----
Write-Color Yellow "[3/5] COM port setup"
$current_port = "COM6"
$config_path = "$PROJECT_DIR\config.py"
if (Test-Path $config_path) {
    $config = Get-Content $config_path -Raw
    if ($config -match 'MODBUS_PORT\s*=\s*"(COM\d+)"') {
        $current_port = $Matches[1]
    }
}
Write-Host "  Current port: $current_port"
$new_port = Read-Host "  Enter COM port (Enter=keep)"
if ($new_port -match "^(COM\d+)$") {
    $config = $config -replace 'MODBUS_PORT\s*=\s*"COM\d+"', "MODBUS_PORT = `"$($Matches[1])`""
    Set-Content -Path $config_path -Value $config -Encoding UTF8
    Write-Color Green "  Port changed to $($Matches[1])"
}

# ---- 4. Create startup batch file ----
Write-Color Yellow "[4/5] Creating startup batch file..."

$batContent = @"
@echo off
title MECOM HMI System
color 0A
echo ==========================================
echo Starting MECOM HMI System...
echo ==========================================
echo.
cd /d "%~dp0"
echo [Modbus Worker] starting...
start /b python modbus_worker.py
echo [API Server] starting...
start /b python api_server.py
timeout /t 3 /nobreak > NUL
echo [Dashboard] opening browser...
echo.
echo http://localhost:8501
echo.
streamlit run app.py
pause
"@

$batPath = "$PROJECT_DIR\start_hmi.bat"
Set-Content -Path $batPath -Value $batContent -Encoding Default
Write-Color Green "  Created: $batPath"

# ---- 5. Desktop shortcut ----
Write-Color Yellow "[5/5] Creating desktop shortcut..."
$WScriptShell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcut = $WScriptShell.CreateShortcut("$desktop\MECOM HMI.lnk")
$shortcut.TargetPath = $batPath
$shortcut.WorkingDirectory = $PROJECT_DIR
$shortcut.Description = "MECOM HMI System"
$shortcut.WindowStyle = 1
$shortcut.Save()
Write-Color Green "  Shortcut created on desktop"

# ---- Auto-start option ----
Write-Host ""
$auto = Read-Host "  Add to startup? (Y/N, default=N)"
if ($auto -eq "Y" -or $auto -eq "y") {
    $startup = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
    Copy-Item "$desktop\MECOM HMI.lnk" "$startup\MECOM HMI.lnk" -Force
    Write-Color Green "  Added to startup"
}

# ---- Done ----
Write-Color Cyan ""
Write-Color Cyan "============================================"
Write-Color Cyan "  Installation complete!"
Write-Color Cyan "============================================"
Write-Host ""
Write-Host "  Run: Double-click 'MECOM HMI' on your desktop"
Write-Host "  URL: http://localhost:8501"
Write-Host "  Auto report: daily at 01:00 -> Desktop\report\"
Write-Host ""
Read-Host "  Press Enter to exit"
