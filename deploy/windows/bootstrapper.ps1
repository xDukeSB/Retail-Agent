<#
.SYNOPSIS
    RetailAI Agent — One-Line Cloud Installer for Windows

.DESCRIPTION
    Run this one-liner in an Admin PowerShell window on the target PC:

        iwr -useb https://storage.googleapis.com/retailai-downloads/bootstrapper.ps1?v=33 | iex

    The script downloads the ZIP from cloud storage, extracts it to C:\RetailAI,
    and runs the full installer (Python, Node, MediaMTX, Windows Services).

.NOTES
    Requires:  Administrator privileges
    Tested on: Windows 10, Windows 11, Windows Server 2019+
    Version:   v33
#>

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
$ZIP_URL     = "https://storage.googleapis.com/retailai-downloads/RetailAI_Agent_Production_Ready.zip"
$INSTALL_DIR = "C:\RetailAI"
$ZIP_FILE    = "$env:TEMP\RetailAI_Release.zip"

# ─────────────────────────────────────────────────────────────────────────────
#  BANNER
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   RetailAI Agent  v33  --  Cloud Installer                " -ForegroundColor Cyan
Write-Host "   Local-First CCTV AI Platform for Retail Stores          " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 1 — Prepare install directory
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "[1/4] Preparing installation directory at $INSTALL_DIR..." -ForegroundColor Yellow
if (Test-Path $INSTALL_DIR) {
    Write-Host "      Directory exists — overwriting files..." -ForegroundColor DarkGray
} else {
    New-Item -ItemType Directory -Path $INSTALL_DIR -Force | Out-Null
}

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 2 — Download ZIP (3 retries)
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "[2/4] Downloading RetailAI Agent from cloud..." -ForegroundColor Yellow
Write-Host "      URL: $ZIP_URL" -ForegroundColor DarkGray
Write-Host "      (This may take a minute — ZIP is ~600 KB)" -ForegroundColor DarkGray

$downloaded = $false
for ($attempt = 1; $attempt -le 3; $attempt++) {
    try {
        Write-Host "      Attempt $attempt of 3..." -ForegroundColor DarkGray
        Invoke-WebRequest -Uri $ZIP_URL -OutFile $ZIP_FILE -UseBasicParsing -ErrorAction Stop
        Write-Host "      Download complete." -ForegroundColor Green
        $downloaded = $true
        break
    } catch {
        Write-Host "      Attempt $attempt failed: $_" -ForegroundColor Yellow
        Start-Sleep -Seconds 5
    }
}

if (!$downloaded) {
    Write-Host ""
    Write-Host "  ERROR: Could not download the ZIP after 3 attempts." -ForegroundColor Red
    Write-Host "  Check your internet connection and try again." -ForegroundColor Yellow
    exit 1
}

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 3 — Extract ZIP
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "[3/4] Extracting files to $INSTALL_DIR..." -ForegroundColor Yellow
try {
    Expand-Archive -Path $ZIP_FILE -DestinationPath $INSTALL_DIR -Force
    Remove-Item -Path $ZIP_FILE -Force -ErrorAction SilentlyContinue
    Write-Host "      Extraction complete." -ForegroundColor Green
} catch {
    Write-Error "Failed to extract ZIP: $_"
    exit 1
}

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 4 — Run the full installer from the extracted package
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "[4/4] Launching core installer..." -ForegroundColor Yellow
Write-Host ""

$InstallScript = Join-Path $INSTALL_DIR "deploy\windows\install.ps1"

if (!(Test-Path $InstallScript)) {
    Write-Error "install.ps1 not found at $InstallScript — ZIP may be corrupted or mis-packaged."
    exit 1
}

Set-Location $INSTALL_DIR
& powershell.exe -ExecutionPolicy Bypass -File $InstallScript

# ─────────────────────────────────────────────────────────────────────────────
#  DONE
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "   RetailAI Agent -- Installation complete!                " -ForegroundColor Green
Write-Host "   Dashboard:  http://localhost:3000                        " -ForegroundColor Green
Write-Host "   API Docs:   http://localhost:8000/api/docs               " -ForegroundColor Green
Write-Host "   (Hold Ctrl and click a link to open in browser)          " -ForegroundColor DarkGray
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
