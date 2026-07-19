# Restart this project's local web agent and verify port 7860.
$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$venvRoot = Split-Path $projectRoot -Parent
$python = Join-Path $venvRoot 'Scripts\python.exe'
$app = Join-Path $projectRoot 'app.py'
$port = 7860
$url = "http://127.0.0.1:$port/"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Virtual environment Python was not found: $python"
}
if (-not (Test-Path -LiteralPath $app)) {
    throw "Web entry file was not found: $app"
}

# Only stop a Python listener on this service port; do not scan other processes.
$listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $oldProcess = Get-Process -Id $listener.OwningProcess -ErrorAction Stop
    if ($oldProcess.ProcessName -notmatch '^python') {
        throw "Port $port is occupied by non-Python PID=$($listener.OwningProcess); it was not stopped."
    }
    Write-Host "Stopping previous agent PID=$($listener.OwningProcess)"
    Stop-Process -Id $listener.OwningProcess -Force
    Start-Sleep -Milliseconds 800
}

$listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    throw "Port $port is still occupied by PID=$($listener.OwningProcess)."
}

$env:PYTHONUTF8 = '1'
$process = Start-Process -FilePath $python -ArgumentList @($app) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru

for ($attempt = 1; $attempt -le 20; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
            Write-Host "Agent is running: $url"
            Write-Host "PID=$($process.Id)"
            exit 0
        }
    }
    catch {
    }
}

if ($process.HasExited) {
    throw "Agent process exited with code $($process.ExitCode)."
}
throw "Agent did not respond within 10 seconds."
