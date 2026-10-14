param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$OutputDir
)

$ErrorActionPreference = 'Stop'
$resolvedInput = (Resolve-Path -LiteralPath $InputPath).Path
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputDir)
[System.IO.Directory]::CreateDirectory($resolvedOutput) | Out-Null

$existingPowerPoint = @(Get-Process POWERPNT -ErrorAction SilentlyContinue).Count -gt 0
$powerPoint = New-Object -ComObject PowerPoint.Application
try {
    $deck = $powerPoint.Presentations.Open($resolvedInput, $true, $false, $false)
    try {
        $slideCount = $deck.Slides.Count
        $deck.Export($resolvedOutput, 'PNG')
        $rendered = @(Get-ChildItem -LiteralPath $resolvedOutput -Filter '*.PNG' -File)
        [pscustomobject]@{
            success = ($rendered.Count -eq $slideCount)
            slides = $slideCount
            rendered = $rendered.Count
            output_dir = $resolvedOutput
        } | ConvertTo-Json -Compress
    }
    finally {
        $deck.Close()
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($deck)
    }
}
finally {
    # COM may attach to the user's existing PowerPoint process. Only close our
    # read-only deck; never quit an already open business editing session.
    if (-not $existingPowerPoint -and $powerPoint.Presentations.Count -eq 0) {
        $powerPoint.Quit()
    }
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($powerPoint)
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
