param(
    [string]$BaseUrl = "http://192.168.3.146:8790"
)

# Keep this script encoded as UTF-8 with BOM for Windows PowerShell 5.1.

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envPath = Join-Path $projectRoot ".env"
$pythonPath = Join-Path (Split-Path $projectRoot -Parent) "Scripts\python.exe"
$verifyPath = Join-Path $projectRoot "mcp\scripts\verify_deployment.py"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "未找到 helloagent Python：$pythonPath"
}

$secureToken = Read-Host "请输入服务器当前有效的新 MCP Token" -AsSecureString
$tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
try {
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer)
    if ([string]::IsNullOrWhiteSpace($token)) {
        throw "MCP Token 不能为空。"
    }

    $existingLines = if (Test-Path -LiteralPath $envPath) {
        @(Get-Content -LiteralPath $envPath)
    } else {
        @()
    }
    $lines = New-Object "System.Collections.Generic.List[string]"
    foreach ($line in $existingLines) {
        if ($line -notmatch "^\s*(MARKET_MCP_BASE_URL|MARKET_MCP_API_TOKEN)\s*=") {
            [void]$lines.Add($line)
        }
    }
    [void]$lines.Add("MARKET_MCP_BASE_URL=$($BaseUrl.TrimEnd('/'))")
    [void]$lines.Add("MARKET_MCP_API_TOKEN=$($token.Trim())")

    $utf8NoBom = [Text.UTF8Encoding]::new($false)
    $temporaryEnvPath = "$envPath.tmp"
    [IO.File]::WriteAllLines($temporaryEnvPath, $lines, $utf8NoBom)
    Move-Item -LiteralPath $temporaryEnvPath -Destination $envPath -Force

    $writtenLines = @(Get-Content -LiteralPath $envPath)
    $baseUrlCount = @($writtenLines | Where-Object { $_ -match "^MARKET_MCP_BASE_URL=" }).Count
    $tokenCount = @($writtenLines | Where-Object { $_ -match "^MARKET_MCP_API_TOKEN=" }).Count
    if (($baseUrlCount -ne 1) -or ($tokenCount -ne 1)) {
        throw "本地 .env 写入校验失败。"
    }

    Write-Host "已安全写入本地 .env：$envPath"
    Write-Host "正在验证四个插件……"
    & $pythonPath $verifyPath --base-url $BaseUrl.TrimEnd("/") --token $token.Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "远程 MCP 验证失败，请检查服务器 Token、端口和网关状态。"
    }

    Write-Host "四个 MCP 插件已完成本地配置。刷新智能体首页即可查看实时状态。"
}
catch {
    $logDir = Join-Path $projectRoot "outputs"
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $logPath = Join-Path $logDir "configure-market-mcp-error.log"
    $safeMessage = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $($_.Exception.GetType().Name): $($_.Exception.Message)"
    [IO.File]::WriteAllText($logPath, $safeMessage, [Text.UTF8Encoding]::new($false))
    Write-Host ""
    Write-Host "配置失败：$($_.Exception.Message)" -ForegroundColor Red
    Write-Host "诊断日志：$logPath" -ForegroundColor Yellow
    Write-Host "窗口会保持打开，请把上面的错误文字发给我。" -ForegroundColor Yellow
}
finally {
    if ($tokenPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
    }
    Remove-Variable token -ErrorAction SilentlyContinue
}
