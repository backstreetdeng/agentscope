# Restart this project's local web agent, verify port 7860, then open the home page.
# Keep UTF-8 with BOM: the desktop launcher uses Windows PowerShell 5.1.
param(
    [switch]$NoOpen,
    [switch]$AllowCloseMonthlyBrowser,
    [ValidatePattern('^(?:\d{1,3}\.){3}\d{1,3}$')]
    [string]$ServerName = '0.0.0.0'
)

$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$venvRoot = Split-Path $projectRoot -Parent
$python = Join-Path $venvRoot 'Scripts\python.exe'
$app = Join-Path $projectRoot 'app.py'
$port = 7860
$url = "http://127.0.0.1:$port/"
$monthlyBrowserProfile = Join-Path $projectRoot 'runtime\monthly-report-browser-profile'
$monthlyBrowserRuntime = Join-Path $projectRoot 'runtime\monthly-report-browser-runtime.json'
$preservedMonthlyBrowserPid = 0
$preservedMonthlyBrowserPort = 0

if ($AllowCloseMonthlyBrowser) {
    throw '参数 -AllowCloseMonthlyBrowser 已停用：服务重启不得以关闭已登录月报浏览器为代价。'
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Virtual environment Python was not found: $python"
}
if (-not (Test-Path -LiteralPath $app)) {
    throw "Web entry file was not found: $app"
}

# A legacy pipe browser is owned by the service and must block a restart.  A
# verified detached-CDP browser is independent and may remain open while only
# port 7860 is restarted.  The historical override is intentionally ignored:
# command-line consent must never silently bypass identity verification.
$monthlyBrowserProcesses = @(
    Get-CimInstance Win32_Process -Filter "name='chrome.exe'" -ErrorAction Stop |
        Where-Object {
            if (-not $_.CommandLine -or $_.CommandLine -match '--type=') { return $false }
            $profileMatch = [regex]::Match(
                $_.CommandLine,
                '(?:"--user-data-dir=([^"]+)"|--user-data-dir="([^"]+)"|--user-data-dir=([^\s"]+))'
            )
            if (-not $profileMatch.Success) { return $false }
            $profileCandidates = @(@(
                $profileMatch.Groups[1].Value,
                $profileMatch.Groups[2].Value,
                $profileMatch.Groups[3].Value
            ) | Where-Object { $_ })
            if ($profileCandidates.Count -ne 1) { return $false }
            [IO.Path]::GetFullPath($profileCandidates[0]) -eq [IO.Path]::GetFullPath($monthlyBrowserProfile)
        }
)
if ($monthlyBrowserProcesses.Count -gt 1) {
    throw '发现多个月报专用 Chrome 主进程。为保护登录会话，本次未重启服务。'
}
if ($monthlyBrowserProcesses.Count -eq 1) {
    $browserProcess = $monthlyBrowserProcesses[0]
    if (-not (Test-Path -LiteralPath $monthlyBrowserRuntime)) {
        throw '月报专用 Chrome 是旧版连接或身份尚未验证。为保护登录会话，本次未重启服务。'
    }
    try {
        $runtime = Get-Content -LiteralPath $monthlyBrowserRuntime -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        throw '月报浏览器运行记录无效。为保护登录会话，本次未重启服务。'
    }
    $owner = Invoke-CimMethod -InputObject $browserProcess -MethodName GetOwner
    $ownerSid = Invoke-CimMethod -InputObject $browserProcess -MethodName GetOwnerSid
    $currentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $portMatch = [regex]::Match($browserProcess.CommandLine, '--remote-debugging-port=(\d+)')
    $profileMatches = [IO.Path]::GetFullPath([string]$runtime.profile_path) -eq [IO.Path]::GetFullPath($monthlyBrowserProfile)
    $identityMatches = (
        $runtime.mode -eq 'detached_cdp' -and
        [int]$runtime.pid -eq [int]$browserProcess.ProcessId -and
        $runtime.windows_sid -eq $currentSid -and
        $ownerSid.Sid -eq $currentSid -and
        $owner.User -eq [Environment]::UserName -and
        $profileMatches -and
        $browserProcess.ExecutablePath -and
        [IO.Path]::GetFileName($browserProcess.ExecutablePath) -ieq 'chrome.exe' -and
        $browserProcess.CommandLine -notmatch '--remote-debugging-pipe' -and
        $portMatch.Success -and
        [int]$portMatch.Groups[1].Value -eq [int]$runtime.cdp_port
    )
    $listenerPid = 0
    if ($identityMatches) {
        foreach ($line in (netstat -ano -p TCP)) {
            if ($line -match ("^\s*TCP\s+127\.0\.0\.1:" + [int]$runtime.cdp_port + "\s+.*LISTENING\s+(\d+)\s*$")) {
                $listenerPid = [int]$Matches[1]
            }
        }
    }
    if (-not $identityMatches -or $listenerPid -ne [int]$browserProcess.ProcessId) {
        throw '月报 Chrome 未通过独立进程、账号、配置目录和本机端口的完整核验。本次未重启服务。'
    }
    $preservedMonthlyBrowserPid = [int]$browserProcess.ProcessId
    $preservedMonthlyBrowserPort = [int]$runtime.cdp_port
}

# Only stop Python listeners on this service port; netstat works even when
# Get-NetTCPConnection is blocked by a restricted Windows token.
$listenerPids = @(
    netstat -ano -p TCP |
        Select-String ":$port\s+.*LISTENING\s+(\d+)$" |
        ForEach-Object { [int]$_.Matches[0].Groups[1].Value } |
        Sort-Object -Unique
)
$listenerProcesses = @()
foreach ($listenerPid in $listenerPids) {
    $oldProcess = Get-Process -Id $listenerPid -ErrorAction Stop
    if ($oldProcess.ProcessName -notmatch '^python') {
        throw "Port $port is occupied by non-Python PID=$listenerPid; no process was stopped."
    }
    $listenerProcesses += $oldProcess
}
foreach ($oldProcess in $listenerProcesses) {
    Write-Host "Stopping previous agent PID=$($oldProcess.Id)"
    Stop-Process -Id $oldProcess.Id -Force
}
if ($listenerProcesses.Count -gt 0) {
    Start-Sleep -Milliseconds 1200
}

$listener = netstat -ano -p TCP | Select-String ":$port\s+.*LISTENING\s+(\d+)$" | Select-Object -First 1
if ($listener) {
    throw "Port $port is still occupied after stopping the verified Python listeners."
}

# Prefer installed Node; otherwise use this account's existing desktop runtime.
$toolBin = Join-Path $projectRoot 'runtime\tool-bin'
$env:Path = "$toolBin;$(Join-Path $venvRoot 'Scripts');$env:Path"
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    $bundledNode = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin'
    if (Test-Path -LiteralPath (Join-Path $bundledNode 'node.exe')) {
        $env:Path = "$bundledNode;$env:Path"
    }
}

$env:PYTHONUTF8 = '1'
$env:AGENT_SERVER_NAME = $ServerName
# app.py 首次导入 AgentScope、PPTX 与前端资源可能接近一分钟。直接启动 Python 能避开某些
# Windows PowerShell 环境在输出重定向时的 PATH/Path 冲突，后续用端口探针确认成功。
Start-Process -FilePath $python -ArgumentList @('-u', $app) -WorkingDirectory $projectRoot -WindowStyle Hidden | Out-Null

for ($attempt = 1; $attempt -le 240; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            if ($preservedMonthlyBrowserPid -gt 0) {
                $preservedBrowser = Get-Process -Id $preservedMonthlyBrowserPid -ErrorAction SilentlyContinue
                $preservedListener = netstat -ano -p TCP | Select-String (":$preservedMonthlyBrowserPort\s+.*LISTENING\s+$preservedMonthlyBrowserPid$") | Select-Object -First 1
                if (-not $preservedBrowser -or -not $preservedListener) {
                    throw '服务已启动，但月报专用 Chrome 未保持原进程和连接端口；请停止执行月报并核查。'
                }
            }
            Write-Host "Agent is running: $url"
            if (-not $NoOpen) {
                Write-Host "Opening agent home page: $url"
                Start-Process $url | Out-Null
            }
            exit 0
        }
    }
    catch {
    }
}

throw "Agent did not respond within 120 seconds. Please run: $python -u $app"
