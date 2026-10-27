# PowerShell 7. Development-only access to one fixed source index.
[CmdletBinding()]
param(
    [ValidateSet('index_repository','index_status','list_projects','get_architecture',
        'get_graph_schema','search_graph','trace_path','get_code_snippet','get_file_outline',
        'check_index_coverage','detect_changes','search_code','query_graph')]
    [string]$Tool = 'index_status',
    [string]$ArgumentsJson = '{}',
    [switch]$Json
)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'Run this script with PowerShell 7 (pwsh).' }
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$projectName = 'market-agent-web'
$binary = Join-Path $env:USERPROFILE '.local/bin/codebase-memory-mcp.exe'
if (-not (Test-Path -LiteralPath $binary -PathType Leaf)) { throw 'Installed codebase-memory-mcp executable not found.' }
$toolArgs = ConvertFrom-Json -InputObject $ArgumentsJson -AsHashtable
if ($toolArgs -isnot [System.Collections.IDictionary]) { throw 'ArgumentsJson must be a JSON object.' }
if ($Tool -eq 'index_repository') {
    foreach ($key in @('mode','target_projects','repo_path','project','name','persistence','async','status')) {
        [void]$toolArgs.Remove($key)
    }
    $toolArgs['repo_path'] = $projectRoot
    $toolArgs['name'] = $projectName
    $toolArgs['mode'] = 'full'
    $toolArgs['persistence'] = $false
} elseif ($Tool -ne 'list_projects') {
    $toolArgs['project'] = $projectName
}
$argumentPath = Join-Path ([IO.Path]::GetTempPath()) ('market-agent-cbm-' + [guid]::NewGuid().ToString('N') + '.json')
$savedCount = [Environment]::GetEnvironmentVariable('GIT_CONFIG_COUNT', 'Process')
$hadCount = Test-Path -LiteralPath 'Env:GIT_CONFIG_COUNT'
$nextSlot = if ($savedCount) { [int]$savedCount } else { 0 }
$keyName = 'GIT_CONFIG_KEY_' + $nextSlot
$valueName = 'GIT_CONFIG_VALUE_' + $nextSlot
$savedKey = [Environment]::GetEnvironmentVariable($keyName, 'Process')
$savedValue = [Environment]::GetEnvironmentVariable($valueName, 'Process')
$hadKey = Test-Path -LiteralPath ('Env:' + $keyName)
$hadValue = Test-Path -LiteralPath ('Env:' + $valueName)
try {
    # Exact repository trust for this child only; never change global Git config.
    [Environment]::SetEnvironmentVariable('GIT_CONFIG_COUNT', [string]($nextSlot + 1), 'Process')
    [Environment]::SetEnvironmentVariable($keyName, 'safe.directory', 'Process')
    [Environment]::SetEnvironmentVariable($valueName, $projectRoot.Replace('\', '/'), 'Process')
    [IO.File]::WriteAllText($argumentPath, ($toolArgs | ConvertTo-Json -Depth 20), [Text.UTF8Encoding]::new($false))
    if ($Json) { & $binary cli --json $Tool --args-file $argumentPath }
    else { & $binary cli $Tool --args-file $argumentPath }
    if ($LASTEXITCODE -ne 0) { throw "Code graph tool failed with exit code $LASTEXITCODE" }
} finally {
    if ($hadCount) { [Environment]::SetEnvironmentVariable('GIT_CONFIG_COUNT', $savedCount, 'Process') }
    else { Remove-Item -LiteralPath 'Env:GIT_CONFIG_COUNT' -ErrorAction SilentlyContinue }
    if ($hadKey) { [Environment]::SetEnvironmentVariable($keyName, $savedKey, 'Process') }
    else { Remove-Item -LiteralPath ('Env:' + $keyName) -ErrorAction SilentlyContinue }
    if ($hadValue) { [Environment]::SetEnvironmentVariable($valueName, $savedValue, 'Process') }
    else { Remove-Item -LiteralPath ('Env:' + $valueName) -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $argumentPath) { Remove-Item -LiteralPath $argumentPath -Force }
}
