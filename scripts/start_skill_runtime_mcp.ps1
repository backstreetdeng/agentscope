param(
    [ValidateSet('streamable-http', 'stdio', 'sse')]
    [string]$Transport = 'streamable-http',
    [switch]$Background
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path (Split-Path $projectRoot -Parent) 'Scripts\python.exe'
$server = Join-Path $projectRoot 'mcp\skill_runtime_server.py'

if (-not (Test-Path -LiteralPath $python)) {
    throw "Virtual environment Python was not found: $python"
}

$env:MCP_TRANSPORT = $Transport
$env:PYTHONUTF8 = '1'
if (-not $Background) {
    & $python $server
    exit $LASTEXITCODE
}

if ($Transport -ne 'streamable-http') {
    throw 'Background mode only supports streamable-http.'
}

$port = 8820
$listenerPids = @(
    netstat -ano -p TCP |
        Select-String ":$port\s+.*LISTENING\s+(\d+)$" |
        ForEach-Object { [int]$_.Matches[0].Groups[1].Value } |
        Sort-Object -Unique
)
foreach ($listenerPid in $listenerPids) {
    $process = Get-Process -Id $listenerPid -ErrorAction Stop
    if ($process.ProcessName -notmatch '^python') {
        throw "Port $port is occupied by non-Python PID=$listenerPid."
    }
    Stop-Process -Id $process.Id -Force
}

Start-Process -FilePath $python -ArgumentList @($server) -WorkingDirectory $projectRoot -WindowStyle Hidden | Out-Null
for ($attempt = 1; $attempt -le 60; $attempt++) {
    Start-Sleep -Milliseconds 500
    $listening = netstat -ano -p TCP | Select-String ":$port\s+.*LISTENING\s+(\d+)$" | Select-Object -First 1
    if ($listening) {
        Write-Host "Skill Runtime MCP is running: http://127.0.0.1:$port/mcp"
        exit 0
    }
}

throw 'Skill Runtime MCP did not start within 30 seconds.'
