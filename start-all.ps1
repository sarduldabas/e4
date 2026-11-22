# Starts the three services in three PowerShell windows (Windows, no Docker needed).
# First time: run  .\start-all.ps1 -Install   to create the Python venvs and install packages.
param([switch]$Install)
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Setup($name) {
  $dir = Join-Path $root $name
  if (-not (Test-Path (Join-Path $dir '.venv'))) { python -m venv (Join-Path $dir '.venv') }
  & (Join-Path $dir '.venv\Scripts\python.exe') -m pip install -r (Join-Path $dir 'requirements.txt')
}

if ($Install) {
  Setup 'agents'; Setup 'backend'
  Push-Location (Join-Path $root 'committee-report-assistant'); npm install; Pop-Location
  Write-Host 'Install done. Run .\start-all.ps1 to start.'; return
}

# Stop services from an earlier start so the ports are free (safe when nothing is running).
foreach ($port in 5173, 8001, 8002) {
  Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}

$agents  = "cd '$root\agents'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8002 --reload"
$backend = "cd '$root\backend'; `$env:AGENTS_URL='http://localhost:8002'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8001 --reload"
$front   = "cd '$root\committee-report-assistant'; npm run dev"
Start-Process powershell -ArgumentList '-NoExit','-Command',$agents
Start-Process powershell -ArgumentList '-NoExit','-Command',$backend
Start-Process powershell -ArgumentList '-NoExit','-Command',$front
Write-Host 'agents http://localhost:8002/docs | backend http://localhost:8001/docs | front end http://localhost:5173'
