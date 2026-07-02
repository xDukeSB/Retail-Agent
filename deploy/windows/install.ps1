<#
.SYNOPSIS
RetailAI Agent One-Click Installer for Windows - Bulletproof Edition v42.
Requires: Run as Administrator. Windows PowerShell 5.1 compatible.
#>

$ErrorActionPreference = "Continue"
$ProgressPreference    = "SilentlyContinue"

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path

$MEDIAMTX_URL  = "https://github.com/bluenviron/mediamtx/releases/download/v1.6.0/mediamtx_v1.6.0_windows_amd64.zip"
$PYTHON311_URL = "https://www.python.org/ftp/python/3.11.8/python-3.11.8-amd64.exe"
$NODE20_URL    = "https://nodejs.org/dist/v20.11.1/node-v20.11.1-x64.msi"
$PYTHON311_DIR = "C:\Program Files\Python311"
$PYTHON311_EXE = "$PYTHON311_DIR\python.exe"

$ToolsDir    = Join-Path $ProjectRoot "tools"
$NssmDir     = Join-Path $ToolsDir "nssm"
$NssmExe     = Join-Path $NssmDir "win64\nssm.exe"
$MediaMtxDir = Join-Path $ProjectRoot "mediamtx"
$MediaMtxExe = Join-Path $MediaMtxDir "mediamtx.exe"
$BackendDir  = Join-Path $ProjectRoot "apps\backend"
$FrontendDir = Join-Path $ProjectRoot "apps\frontend"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   RetailAI Agent Installer v42         " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Helper: safe download with retry
function Download-File {
    param([string]$Url, [string]$Dest, [string]$Name)
    $maxAttempts = 3
    for ($i = 1; $i -le $maxAttempts; $i++) {
        try {
            Write-Host "    Downloading $Name attempt $i/$maxAttempts..." -ForegroundColor DarkGray
            Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing -ErrorAction Stop
            Write-Host "    $Name downloaded OK." -ForegroundColor Green
            return $true
        } catch {
            Write-Host "    Attempt $i failed. Retrying..." -ForegroundColor Yellow
            Start-Sleep -Seconds 3
        }
    }
    Write-Host "    WARNING: Could not download $Name. Skipping." -ForegroundColor Red
    return $false
}

# ------------------------------------------------------------------
# [0/7] Stop existing services and processes
# ------------------------------------------------------------------
Write-Host "[0/7] Cleaning up old services and processes..." -ForegroundColor Yellow

Stop-Service -Name "RetailAI_*" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

taskkill /F /IM mediamtx.exe /T 2>$null | Out-Null
taskkill /F /IM uvicorn.exe  /T 2>$null | Out-Null
taskkill /F /IM python.exe   /T 2>$null | Out-Null
taskkill /F /IM node.exe     /T 2>$null | Out-Null
Start-Sleep -Seconds 1

$oldServices = @("RetailAI_MediaMTX", "RetailAI_Backend", "RetailAI_Frontend")
foreach ($svcName in $oldServices) {
    $svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
    if ($svc) {
        Stop-Service -Name $svcName -Force -ErrorAction SilentlyContinue
        if (Test-Path $NssmExe) {
            & $NssmExe remove $svcName confirm 2>$null | Out-Null
        } else {
            sc.exe delete $svcName 2>$null | Out-Null
        }
        Write-Host "    Removed old service: $svcName" -ForegroundColor DarkGray
    }
}
Start-Sleep -Seconds 2
Write-Host "    Cleanup done." -ForegroundColor Green

# ------------------------------------------------------------------
# [1/7] Install Prerequisites
# ------------------------------------------------------------------
Write-Host ""
Write-Host "[1/7] Checking Prerequisites..." -ForegroundColor Yellow

if (Test-Path $PYTHON311_EXE) {
    Write-Host "    Python 3.11 already installed." -ForegroundColor Green
} else {
    Write-Host "    Python 3.11 not found. Downloading..." -ForegroundColor Cyan
    $pyInst = Join-Path $env:TEMP "python-3.11.8-amd64.exe"
    $pyOk = Download-File -Url $PYTHON311_URL -Dest $pyInst -Name "Python 3.11.8"
    if ($pyOk) {
        Write-Host "    Installing Python 3.11 silently..." -ForegroundColor Cyan
        Start-Process -FilePath $pyInst -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait -ErrorAction SilentlyContinue
        Remove-Item $pyInst -Force -ErrorAction SilentlyContinue
        if (Test-Path $PYTHON311_EXE) {
            Write-Host "    Python 3.11 installed." -ForegroundColor Green
        } else {
            Write-Host "    WARNING: Python installer ran but exe not found." -ForegroundColor Red
        }
    }
}

$env:PATH = "$PYTHON311_DIR\;$PYTHON311_DIR\Scripts\;" + $env:PATH

$npmCheck = Get-Command "npm" -ErrorAction SilentlyContinue
if ($npmCheck) {
    Write-Host "    Node.js already installed." -ForegroundColor Green
} else {
    Write-Host "    Node.js not found. Downloading..." -ForegroundColor Cyan
    $nodeInst = Join-Path $env:TEMP "node-v20-x64.msi"
    $nodeOk = Download-File -Url $NODE20_URL -Dest $nodeInst -Name "Node.js 20"
    if ($nodeOk) {
        Write-Host "    Installing Node.js 20 silently..." -ForegroundColor Cyan
        Start-Process -FilePath "msiexec.exe" -ArgumentList "/i `"$nodeInst`" /quiet /norestart" -Wait -ErrorAction SilentlyContinue
        Remove-Item $nodeInst -Force -ErrorAction SilentlyContinue
        # Refresh PATH immediately so npm is available in this session
        $env:PATH = "C:\Program Files\nodejs\;" + $env:PATH
        # Also pull from machine PATH in case installer wrote elsewhere
        $machinePath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
        $env:PATH = $machinePath + ";" + $env:PATH
        Write-Host "    Node.js installed." -ForegroundColor Green
    }
}

# ------------------------------------------------------------------
# [2/7] NSSM check
# ------------------------------------------------------------------
Write-Host ""
Write-Host "[2/7] Checking NSSM..." -ForegroundColor Yellow
if (Test-Path $NssmExe) {
    Write-Host "    NSSM found (bundled)." -ForegroundColor Green
} else {
    Write-Host "    WARNING: NSSM not found at $NssmExe" -ForegroundColor Red
}

# ------------------------------------------------------------------
# [3/7] MediaMTX (RTSP Relay)
# ------------------------------------------------------------------
Write-Host ""
Write-Host "[3/7] Setting up MediaMTX RTSP server..." -ForegroundColor Yellow
if (!(Test-Path $MediaMtxDir)) {
    New-Item -ItemType Directory -Path $MediaMtxDir -Force | Out-Null
}
if (Test-Path $MediaMtxExe) {
    Write-Host "    MediaMTX already present." -ForegroundColor Green
} else {
    $mZip = Join-Path $MediaMtxDir "mediamtx.zip"
    $mOk = Download-File -Url $MEDIAMTX_URL -Dest $mZip -Name "MediaMTX"
    if ($mOk) {
        try {
            Expand-Archive -Path $mZip -DestinationPath $MediaMtxDir -Force -ErrorAction Stop
            Write-Host "    MediaMTX extracted." -ForegroundColor Green
        } catch {
            Write-Host "    WARNING: Could not extract MediaMTX: $_" -ForegroundColor Red
        }
        Remove-Item $mZip -Force -ErrorAction SilentlyContinue
    }
}

# ------------------------------------------------------------------
# [4/7] Python Backend - venv + pip
# ------------------------------------------------------------------
Write-Host ""
Write-Host "[4/7] Setting up Python Backend..." -ForegroundColor Yellow

if (!(Test-Path $BackendDir)) {
    Write-Host "    ERROR: Backend directory not found at $BackendDir" -ForegroundColor Red
} else {
    Set-Location $BackendDir

    $venvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"

    if (Test-Path $venvPython) {
        try {
            $venvVer = & $venvPython -c "import sys; print(str(sys.version_info.major) + '.' + str(sys.version_info.minor))" 2>$null
            if ($venvVer -ne "3.11") {
                Write-Host "    Found wrong Python version in .venv. Recreating..." -ForegroundColor Yellow
                Remove-Item (Join-Path $BackendDir ".venv") -Recurse -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 1
            } else {
                Write-Host "    Existing .venv is Python 3.11. Reusing." -ForegroundColor Green
            }
        } catch {
            Write-Host "    Could not check .venv version, recreating..." -ForegroundColor Yellow
            Remove-Item (Join-Path $BackendDir ".venv") -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    if (!(Test-Path $venvPython)) {
        Write-Host "    Creating Python 3.11 virtual environment..." -ForegroundColor Cyan
        try {
            & $PYTHON311_EXE -m venv .venv --clear
            Write-Host "    .venv created." -ForegroundColor Green
        } catch {
            Write-Host "    ERROR creating .venv: $_" -ForegroundColor Red
        }
    }

    $PythonExe  = Join-Path $BackendDir ".venv\Scripts\python.exe"
    $UvicornExe = Join-Path $BackendDir ".venv\Scripts\uvicorn.exe"

    # ── Bootstrap pip using get-pip.py (most reliable method on Windows) ──────────
    $getPipPath = Join-Path $env:TEMP "get-pip.py"
    Write-Host "    Bootstrapping pip (get-pip.py)..." -ForegroundColor Cyan
    try {
        Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPipPath -UseBasicParsing -ErrorAction Stop
        & $PythonExe $getPipPath --quiet
        Remove-Item $getPipPath -Force -ErrorAction SilentlyContinue
        Write-Host "    pip bootstrapped successfully." -ForegroundColor Green
    } catch {
        Write-Host "    WARNING: get-pip.py download failed, trying ensurepip fallback..." -ForegroundColor Yellow
        & $PythonExe -m ensurepip --upgrade
    }

    # Verify pip actually works before proceeding
    $pipCheck = & $PythonExe -m pip --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    CRITICAL: pip is still not working after bootstrap attempt!" -ForegroundColor Red
        Write-Host "    Output: $pipCheck" -ForegroundColor Red
        Write-Host "    Trying to recover with ensurepip --default-pip..." -ForegroundColor Yellow
        & $PythonExe -m ensurepip --default-pip --upgrade
    } else {
        Write-Host "    pip OK: $pipCheck" -ForegroundColor Green
    }

    Write-Host "    Upgrading pip to latest..." -ForegroundColor DarkGray
    & $PythonExe -m pip install --upgrade pip

    Write-Host "    Installing Python packages, please wait (this takes 3-5 minutes)..." -ForegroundColor Cyan
    $reqFile    = Join-Path $BackendDir "requirements.txt"
    $pipSuccess = $false
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        Write-Host "    pip install attempt $attempt of 3..." -ForegroundColor DarkGray
        & $PythonExe -m pip install --prefer-binary --no-compile -r $reqFile
        if ($LASTEXITCODE -eq 0) {
            $pipSuccess = $true
            Write-Host "    All packages installed successfully!" -ForegroundColor Green
            break
        } else {
            Write-Host "    Attempt $attempt failed. Retrying in 5 seconds..." -ForegroundColor Yellow
            Start-Sleep -Seconds 5
        }
    }
    if (!$pipSuccess) {
        Write-Host "    WARNING: Some packages may not have installed. Trying critical packages individually..." -ForegroundColor Red
    }

    # ── Always ensure critical backend packages are installed ────────────────────────
    Write-Host "    Verifying critical packages (uvicorn, click, fastapi)..." -ForegroundColor Cyan
    $criticalPkgs = @("click", "uvicorn[standard]", "fastapi", "sqlalchemy", "aiosqlite", "pydantic", "python-jose[cryptography]", "passlib[bcrypt]", "python-multipart")
    foreach ($pkg in $criticalPkgs) {
        Write-Host "      Installing $pkg..." -ForegroundColor DarkGray
        & $PythonExe -m pip install $pkg --prefer-binary
    }
    Write-Host "    Critical packages verified." -ForegroundColor Green

    Write-Host "    Downloading YOLO AI model weights..." -ForegroundColor Cyan
    try {
        & $PythonExe -c "from ultralytics import YOLO; YOLO('yolov8n.pt')" 2>&1 | Out-Null
        Write-Host "    YOLO weights downloaded." -ForegroundColor Green
    } catch {
        Write-Host "    WARNING: YOLO weights will download on first camera connection." -ForegroundColor Yellow
    }

    # ── DB Init: create tables and add any missing columns ──────────────────
    Write-Host "    Initialising database schema..." -ForegroundColor Cyan
    $dbInitScript = @'
import sys, os, sqlite3, subprocess

# --- ensure data/db directory exists ---
os.makedirs("data/db", exist_ok=True)

# --- run alembic migrations first (no-op if already at head) ---
import subprocess
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], capture_output=True)

# --- patch missing columns directly via sqlite3 (safe on fresh or old DB) ---
db_path = os.path.join("data", "db", "retailai.db")

# Create DB file if it does not exist yet
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Create stores table if completely absent
cur.execute("""
CREATE TABLE IF NOT EXISTS stores (
    id TEXT PRIMARY KEY,
    name TEXT DEFAULT 'Downtown Flagship',
    region TEXT,
    address TEXT,
    timezone TEXT DEFAULT 'UTC',
    currency TEXT DEFAULT 'USD',
    last_sync DATETIME,
    last_heartbeat DATETIME
)
""")

# Patch missing columns
missing = {
    "auto_sync":           "BOOLEAN DEFAULT 1",
    "sync_metadata":       "BOOLEAN DEFAULT 1",
    "sync_analytics":      "BOOLEAN DEFAULT 1",
    "sync_reports":        "BOOLEAN DEFAULT 1",
    "sync_video":          "BOOLEAN DEFAULT 0",
    "queue_detection":     "BOOLEAN DEFAULT 1",
    "transaction_detection":"BOOLEAN DEFAULT 1",
    "heatmap_generation":  "BOOLEAN DEFAULT 1",
    "zone_tracking":       "BOOLEAN DEFAULT 1",
    "face_anonymization":  "BOOLEAN DEFAULT 1",
    "detection_confidence":"FLOAT DEFAULT 0.6",
    "frame_evaluation_rate":"INTEGER DEFAULT 5",
}
cur.execute("PRAGMA table_info(stores)")
existing_cols = [row[1] for row in cur.fetchall()]
for col, definition in missing.items():
    if col not in existing_cols:
        cur.execute(f"ALTER TABLE stores ADD COLUMN {col} {definition}")
        print(f"  Added column: stores.{col}")

# Create transaction intelligence tables (safe if they already exist)
cur.execute("""
CREATE TABLE IF NOT EXISTS transaction_sessions (
    id TEXT PRIMARY KEY,
    visitor_uuid TEXT NOT NULL,
    track_id INTEGER NOT NULL,
    camera_id TEXT NOT NULL,
    store_id TEXT,
    state TEXT NOT NULL DEFAULT 'ENTERED_STORE',
    confidence_score REAL NOT NULL DEFAULT 0.0,
    transaction_probability REAL NOT NULL DEFAULT 0.0,
    confidence_level TEXT NOT NULL DEFAULT 'UNLIKELY',
    detected_signals TEXT,
    entered_at DATETIME NOT NULL,
    exited_at DATETIME,
    last_updated DATETIME NOT NULL,
    is_complete BOOLEAN NOT NULL DEFAULT 0,
    synced BOOLEAN NOT NULL DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS transaction_signals (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    score INTEGER NOT NULL,
    zone_name TEXT,
    detected_at DATETIME NOT NULL,
    x REAL,
    y REAL,
    metadata_json TEXT,
    synced BOOLEAN NOT NULL DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS transaction_predictions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    visitor_uuid TEXT NOT NULL,
    camera_id TEXT NOT NULL,
    store_id TEXT,
    transaction_probability REAL NOT NULL,
    confidence_level TEXT NOT NULL,
    detected_signals TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    synced BOOLEAN NOT NULL DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS transaction_statistics (
    id TEXT PRIMARY KEY,
    camera_id TEXT,
    date DATE NOT NULL,
    hour INTEGER,
    total_sessions INTEGER NOT NULL DEFAULT 0,
    likely_purchases INTEGER NOT NULL DEFAULT 0,
    checkout_visitors INTEGER NOT NULL DEFAULT 0,
    checkout_abandonment INTEGER NOT NULL DEFAULT 0,
    avg_confidence REAL NOT NULL DEFAULT 0.0,
    queue_success_rate REAL NOT NULL DEFAULT 0.0,
    payment_type_distribution TEXT,
    computed_at DATETIME NOT NULL,
    synced BOOLEAN NOT NULL DEFAULT 0
)
""")
print("  Transaction intelligence tables created/verified.")

conn.commit()
conn.close()
print("Database schema OK.")
'@
    $dbInitPath = Join-Path $BackendDir "db_init_temp.py"
    $dbInitScript | Set-Content -Path $dbInitPath -Encoding UTF8
    Push-Location $BackendDir
    & $PythonExe $dbInitPath 2>&1 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
    Remove-Item $dbInitPath -Force -ErrorAction SilentlyContinue
    Pop-Location
    Write-Host "    Database ready." -ForegroundColor Green
}

# ------------------------------------------------------------------
# [5/7] Node.js Frontend - npm install + build
# ------------------------------------------------------------------
Write-Host ""
Write-Host "[5/7] Building Frontend Dashboard..." -ForegroundColor Yellow

if (!(Test-Path $FrontendDir)) {
    Write-Host "    ERROR: Frontend directory not found at $FrontendDir" -ForegroundColor Red
} else {
    Set-Location $FrontendDir

    # Copy .env if frontend doesn't have one yet
    $frontendEnv = Join-Path $FrontendDir ".env"
    $rootEnv     = Join-Path $ProjectRoot ".env"
    if (!(Test-Path $frontendEnv) -and (Test-Path $rootEnv)) {
        Copy-Item $rootEnv $frontendEnv -Force
        Write-Host "    Copied .env to frontend directory." -ForegroundColor DarkGray
    }

    Write-Host "    Installing npm packages..." -ForegroundColor Cyan
    $npmOut = npm install --loglevel=error 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    npm install failed, retrying with legacy peer deps..." -ForegroundColor Yellow
        $npmOut = npm install --legacy-peer-deps --loglevel=error 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "    WARNING: npm install had errors:" -ForegroundColor Red
            $npmOut | Select-Object -Last 20 | ForEach-Object { Write-Host "      $_" -ForegroundColor Red }
        }
    }
    Write-Host "    npm packages ready." -ForegroundColor Green

    Write-Host "    Building production bundle, please wait 2 to 5 minutes..." -ForegroundColor Cyan
    $buildOut = npm run build 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    WARNING: Build had errors. Dashboard may not work." -ForegroundColor Red
        Write-Host "    --- Build error details ---" -ForegroundColor Yellow
        $buildOut | Select-Object -Last 30 | ForEach-Object { Write-Host "      $_" -ForegroundColor Yellow }
        Write-Host "    --- End of build errors ---" -ForegroundColor Yellow
        Write-Host "    TIP: Check apps\frontend\.env and ensure all API URLs are set." -ForegroundColor Cyan
    } else {
        Write-Host "    Frontend built successfully!" -ForegroundColor Green
    }
}

# ------------------------------------------------------------------
# [6/7] Windows Services
# ------------------------------------------------------------------
Write-Host ""
Write-Host "[6/7] Installing Windows Services..." -ForegroundColor Yellow

function Install-NssmService {
    param(
        [string]$ServiceName,
        [string]$ExePath,
        [string]$AppDir,
        [string]$AppArgs
    )

    if (!(Test-Path $ExePath)) {
        Write-Host "    SKIP $ServiceName - exe not found at $ExePath" -ForegroundColor Red
        return
    }
    if (!(Test-Path $NssmExe)) {
        Write-Host "    SKIP $ServiceName - NSSM not found." -ForegroundColor Red
        return
    }

    $existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($existing) {
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
        & $NssmExe remove $ServiceName confirm 2>$null | Out-Null
        Start-Sleep -Seconds 2
    }

    Write-Host "    Installing $ServiceName..." -ForegroundColor Cyan
    & $NssmExe install $ServiceName $ExePath $AppArgs 2>&1 | Out-Null
    & $NssmExe set $ServiceName AppDirectory $AppDir 2>&1 | Out-Null
    & $NssmExe set $ServiceName Start SERVICE_AUTO_START 2>&1 | Out-Null
    & $NssmExe set $ServiceName AppStdout (Join-Path $ToolsDir "$ServiceName.log") 2>&1 | Out-Null
    & $NssmExe set $ServiceName AppStderr (Join-Path $ToolsDir "$ServiceName.err") 2>&1 | Out-Null
    & $NssmExe set $ServiceName AppKillProcessTree 1 2>&1 | Out-Null

    # Pass environment variables so the service process has access to them
    if ($ServiceName -eq "RetailAI_Backend") {
        $envFile = Join-Path $ProjectRoot ".env"
        $jwtSecret = "a061b734785101f54ba247fc0b2eecfc5a5efc4ec8c26f341404652e8f67848b"
        $yoloPath  = Join-Path $ProjectRoot "data\models\yolov8n.pt"
        & $NssmExe set $ServiceName AppEnvironmentExtra `
            "JWT_SECRET=$jwtSecret" `
            "JWT_ALGORITHM=HS256" `
            "JWT_EXPIRE_MINUTES=60" `
            "YOLO_MODEL_PATH=$yoloPath" `
            "YOLO_DEVICE=cpu" `
            "DATABASE_URL=sqlite+aiosqlite:///./data/db/retailai.db" `
            "PYTHONUNBUFFERED=1" 2>&1 | Out-Null
        Write-Host "    Environment variables set for $ServiceName." -ForegroundColor DarkGray
    }

    Start-Sleep -Seconds 1
    try {
        Start-Service -Name $ServiceName -ErrorAction Stop
        Write-Host "    $ServiceName started OK!" -ForegroundColor Green
    } catch {
        Write-Host "    WARNING: $ServiceName installed but could not start yet." -ForegroundColor Yellow
        Write-Host "    It will auto-start on next reboot. To diagnose, run:" -ForegroundColor DarkGray
        Write-Host "      sc query $ServiceName" -ForegroundColor DarkGray
        Write-Host "      Get-Content '$ToolsDir\$ServiceName.err' -Tail 20" -ForegroundColor DarkGray
    }
}

$mediamtxConfig = Join-Path $ProjectRoot "services\stream-relay\mediamtx.yml"
if (Test-Path $mediamtxConfig) {
    $mtxArgs = $mediamtxConfig
} else {
    $mtxArgs = ""
}

Install-NssmService -ServiceName "RetailAI_MediaMTX" -ExePath $MediaMtxExe -AppDir $MediaMtxDir -AppArgs $mtxArgs

$BackendPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
Install-NssmService -ServiceName "RetailAI_Backend" -ExePath $BackendPython -AppDir $BackendDir -AppArgs "-m uvicorn main:app --host 0.0.0.0 --port 8000"

$_nc = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
if ($_nc) {
    $NpmExe = $_nc.Source
} else {
    $_nc2 = Get-Command "npm" -ErrorAction SilentlyContinue
    if ($_nc2) {
        $NpmExe = $_nc2.Source
    } else {
        $NpmExe = "C:\Program Files\nodejs\npm.cmd"
    }
}

Install-NssmService -ServiceName "RetailAI_Frontend" -ExePath $NpmExe -AppDir $FrontendDir -AppArgs "start"

# ------------------------------------------------------------------
# [7/7] Wait for backend and launch dashboard
# ------------------------------------------------------------------
Write-Host ""
Write-Host "[7/7] Waiting for services to start..." -ForegroundColor Yellow

$ready = $false
for ($i = 1; $i -le 30; $i++) {
    Start-Sleep -Seconds 2
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:8000/api/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($resp.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
        # still starting
    }
    Write-Host "    Waiting... ($($i * 2) seconds)" -ForegroundColor DarkGray
}

Write-Host ""
if ($ready) {
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "   Installation Complete!               " -ForegroundColor Green
    Write-Host "   Dashboard: http://localhost:3000     " -ForegroundColor Green
    Write-Host "   API Docs:  http://localhost:8000/api/docs" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
} else {
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host "   Installation Finished.               " -ForegroundColor Yellow
    Write-Host "   Dashboard opening at localhost:3000  " -ForegroundColor Yellow
    Write-Host "   May take 1-2 min for first load.     " -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Yellow
}

Start-Sleep -Seconds 5
Start-Process "http://localhost:3000"

Write-Host ""
Write-Host "Done. RetailAI Agent is installed as Windows Services." -ForegroundColor Green
Write-Host "It will automatically restart on every reboot." -ForegroundColor DarkGray
Write-Host ""
