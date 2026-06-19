# Clara – Start all services
# Run from the repo root: powershell -File start.ps1

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$lk   = Join-Path $root "livekit-server\livekit-server.exe"
$srv  = Join-Path $root "server"
$cli  = Join-Path $root "client"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Clara – Avery Wellness Clinic Voice Agent" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. LiveKit server ────────────────────────────────────────────────────────
Write-Host "[1/3] Starting LiveKit server on :7880 ..." -ForegroundColor Yellow
$lkProc = Start-Process -FilePath $lk `
    -ArgumentList "--dev", "--bind", "0.0.0.0" `
    -PassThru -NoNewWindow
Write-Host "      LiveKit PID: $($lkProc.Id)" -ForegroundColor Green

Start-Sleep -Seconds 2

# ── 2. FastAPI admin API ─────────────────────────────────────────────────────
Write-Host "[2/3] Starting FastAPI admin API on :8000 ..." -ForegroundColor Yellow
$apiProc = Start-Process -FilePath (Join-Path $srv ".venv\Scripts\python.exe") `
    -ArgumentList "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--reload" `
    -WorkingDirectory $srv `
    -PassThru -NoNewWindow
Write-Host "      FastAPI PID: $($apiProc.Id)" -ForegroundColor Green

Start-Sleep -Seconds 3

# ── 3. Next.js dashboard ─────────────────────────────────────────────────────
Write-Host "[3/3] Starting Next.js dashboard on :3000 ..." -ForegroundColor Yellow
$uiProc = Start-Process -FilePath "npm.cmd" `
    -ArgumentList "run", "dev" `
    -WorkingDirectory $cli `
    -PassThru -NoNewWindow
Write-Host "      Next.js PID: $($uiProc.Id)" -ForegroundColor Green

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  All services running!" -ForegroundColor Green
Write-Host ""
Write-Host "  Dashboard  →  http://localhost:3000" -ForegroundColor White
Write-Host "  Admin API  →  http://localhost:8000/docs" -ForegroundColor White
Write-Host "  LiveKit    →  ws://localhost:7880" -ForegroundColor White
Write-Host ""
Write-Host "  To start the voice agent (in a new terminal):" -ForegroundColor Yellow
Write-Host "    cd server" -ForegroundColor White
Write-Host "    .\.venv\Scripts\python.exe agent.py start" -ForegroundColor White
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop all services." -ForegroundColor Gray

# Keep the script alive so Ctrl+C propagates
try {
    while ($true) { Start-Sleep -Seconds 5 }
} finally {
    Write-Host "`nStopping services..." -ForegroundColor Red
    Stop-Process -Id $lkProc.Id  -ErrorAction SilentlyContinue
    Stop-Process -Id $apiProc.Id -ErrorAction SilentlyContinue
    Stop-Process -Id $uiProc.Id  -ErrorAction SilentlyContinue
}
