<#
.SYNOPSIS
  Starts SkillWatch AI: backend (FastAPI), worker (simulated live camera feed) and frontend (React).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\run_all.ps1
  powershell -ExecutionPolicy Bypass -File .\run_all.ps1 -ResetDemo        # wipe and rebuild demo data
  powershell -ExecutionPolicy Bypass -File .\run_all.ps1 -SkipInstall -NoWorker
#>
param(
  [switch]$ResetDemo,
  [switch]$SkipInstall,
  [switch]$NoWorker,
  [switch]$WithYolo,
  [int]$WorkerMinutes = 5
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Step([string]$msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Need([string]$cmd, [string]$hint) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "$cmd was not found. $hint" }
}

Need "python" "Install Python 3.11 from python.org and tick 'Add python.exe to PATH'."
Need "node" "Install Node.js 20 LTS from nodejs.org."

# 1. Python environment
$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
  Step "Creating virtual environment (.venv)"
  python -m venv .venv
  if ($LASTEXITCODE -ne 0) { throw "Could not create the virtual environment" }
}
if (-not $SkipInstall) {
  Step "Installing Python packages (first run takes a few minutes)"
  & $venvPy -m pip install --upgrade pip | Out-Null
  $req = "requirements.txt"
  if ($WithYolo) { $req = "requirements-yolo.txt" }
  & $venvPy -m pip install -r $req
  if ($LASTEXITCODE -ne 0) { throw "pip install failed. Scroll up for the error." }
}

# 2. Settings
if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Step "Created .env from .env.example"
}
# MongoDB must be running (local or Docker). A warning only: an Atlas URL in .env is fine without a local server.
try { $tcp = New-Object Net.Sockets.TcpClient; $tcp.Connect("localhost", 27017); $tcp.Close() }
catch { Write-Warning "No MongoDB found on localhost:27017. Start one (see the MongoDB section of README.md) or set MONGO_URL in .env to an Atlas address." }
$ingestKey = ""
$keyLine = Get-Content ".env" | Where-Object { $_ -match '^INGEST_API_KEY=' } | Select-Object -First 1
if ($keyLine) { $ingestKey = ($keyLine -replace '^INGEST_API_KEY=', '').Trim() }

# 3. Frontend packages
if (-not $SkipInstall -and -not (Test-Path "frontend\node_modules")) {
  Step "Installing frontend packages"
  Push-Location "frontend"
  npm install
  $npmCode = $LASTEXITCODE
  Pop-Location
  if ($npmCode -ne 0) { throw "npm install failed. Scroll up for the error." }
}

# 4. Demo data: footage, database, seeded users, a first analysis and 7 days of history
if ($ResetDemo -or -not (Test-Path "data\skillwatch.db")) {
  Step "Preparing demo data"
  & $venvPy -m scripts.run_demo --reset
  if ($LASTEXITCODE -ne 0) { throw "Demo data setup failed. Scroll up for the error." }
}

# 5. Start everything (each in its own window so you can read the logs)
Step "Starting backend on http://127.0.0.1:8000"
$backend = Start-Process -FilePath $venvPy -WorkingDirectory $PSScriptRoot -PassThru `
  -ArgumentList @("-m", "uvicorn", "backend.app.main:app", "--port", "8000")

$ready = $false
for ($i = 0; $i -lt 40 -and -not $ready; $i++) {
  try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 2 | Out-Null
    $ready = $true
  } catch { Start-Sleep -Seconds 1 }
}
if (-not $ready) {
  & taskkill /PID $backend.Id /T /F | Out-Null
  throw "The backend did not start. Look at the backend window for the error."
}

$worker = $null
if ($NoWorker) {
  Step "Worker skipped (-NoWorker)"
} elseif ($ingestKey -eq "") {
  Write-Host "INGEST_API_KEY is empty in .env, so the worker was not started." -ForegroundColor Yellow
} else {
  Step "Starting worker (a simulated camera feed, every $WorkerMinutes minutes)"
  $worker = Start-Process -FilePath $venvPy -WorkingDirectory $PSScriptRoot -PassThru `
    -ArgumentList @("-m", "vision.lowbw", "worker", "--interval-min", "$WorkerMinutes", "--api-key", $ingestKey)
}

Step "Starting frontend on http://localhost:5173"
$frontend = Start-Process -FilePath "cmd.exe" -WorkingDirectory (Join-Path $PSScriptRoot "frontend") -PassThru `
  -ArgumentList @("/c", "npm run dev")

Start-Sleep -Seconds 6
Start-Process "http://localhost:5173"

Write-Host ""
Write-Host "SkillWatch AI is running." -ForegroundColor Green
Write-Host "  Dashboard : http://localhost:5173"
Write-Host "  API docs  : http://127.0.0.1:8000/docs"
Write-Host "  Logins    : superadmin@skillwatch.local, officer@skillwatch.local, admin.sc001@skillwatch.local"
Write-Host "  Password  : Demo@12345"
Write-Host ""
Read-Host "Press Enter here to stop everything"

foreach ($p in @($frontend, $worker, $backend)) {
  if ($p -ne $null) { & taskkill /PID $p.Id /T /F 2>$null | Out-Null }
}
Write-Host "Stopped."
