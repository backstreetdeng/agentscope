# Preserve an inactive profile from another Windows account, then allow fresh login.
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$runtimeRoot = Join-Path $projectRoot 'runtime'
$profile = Join-Path $runtimeRoot 'monthly-report-browser-profile'
$session = Join-Path $runtimeRoot 'monthly-report-browser-session.json'
if (-not (Test-Path -LiteralPath $session)) { Write-Output 'No migrated session metadata; no action.'; exit 0 }
$metadata = Get-Content -LiteralPath $session -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $metadata.windows_user -or $metadata.windows_user -ieq [Environment]::UserName) {
    Write-Output 'Session belongs to current account; no action.'
    exit 0
}
$live = @(Get-CimInstance Win32_Process -Filter "name='chrome.exe'" | Where-Object {
    $_.CommandLine -and $_.CommandLine -notmatch '--type=' -and
    $_.CommandLine.IndexOf($profile, [StringComparison]::OrdinalIgnoreCase) -ge 0
})
if ($live.Count -gt 0) { throw 'Dedicated Chrome is running. No files were moved.' }
$archive = Join-Path $runtimeRoot ('migration-recovery-20261016\browser-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$names = @('monthly-report-browser-profile', 'monthly-report-browser-session.json', 'monthly-report-browser-runtime.json')
foreach ($name in $names) {
    $source = [IO.Path]::GetFullPath((Join-Path $runtimeRoot $name))
    $destination = [IO.Path]::GetFullPath((Join-Path $archive $name))
    $prefix = [IO.Path]::GetFullPath($runtimeRoot).TrimEnd('\') + '\'
    if (-not $source.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) -or
        -not $destination.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Migration paths must remain inside this project runtime directory.'
    }
}
New-Item -ItemType Directory -Path $archive | Out-Null
foreach ($name in $names) {
    $source = Join-Path $runtimeRoot $name
    if (Test-Path -LiteralPath $source) {
        Move-Item -LiteralPath $source -Destination (Join-Path $archive $name)
    }
}
New-Item -ItemType Directory -Path $profile | Out-Null
Write-Output "Preserved migrated profile: $archive"
Write-Output 'Fresh profile prepared. BI login still needs user authentication.'
