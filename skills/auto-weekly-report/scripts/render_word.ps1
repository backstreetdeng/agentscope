param([Parameter(Mandatory=$true)][string]$InputPath,[Parameter(Mandatory=$true)][string]$OutputDir,[switch]$UpdateToc)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$path=(Resolve-Path -LiteralPath $InputPath).Path
$output=[IO.Path]::GetFullPath($OutputDir)
[IO.Directory]::CreateDirectory($output) | Out-Null
$alreadyRunning=@(Get-Process WINWORD,wps -ErrorAction SilentlyContinue).Count -gt 0
try { $word=New-Object -ComObject Word.Application }
catch { @{available=$false;success=$false;reason='Microsoft Word compatible COM is not available'} | ConvertTo-Json -Compress; exit 0 }
$document=$null
$result=@{available=$true;success=$false}
try {
    $document=$word.Documents.Open($path,$false,$false,$false)
    if ($UpdateToc) {
        [void]$document.Fields.Update()
        foreach ($toc in $document.TablesOfContents) { [void]$toc.Update() }
        $document.Save()
    }
    $pdf=Join-Path $output (([IO.Path]::GetFileNameWithoutExtension($path))+'.pdf')
    $document.ExportAsFixedFormat($pdf,17)
    $result=@{available=$true;success=(Test-Path -LiteralPath $pdf);pages=[int]$document.ComputeStatistics(2);pdf=$pdf;toc_updated=[bool]$UpdateToc}
}
catch { $result.error=$_.Exception.Message }
finally {
    if ($document) {
        try { $document.Close($false) } catch { }
        try { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document) } catch { }
    }
    if (-not $alreadyRunning) { try { if ($word.Documents.Count -eq 0) { $word.Quit() } } catch { } }
    try { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) } catch { }
}
$result | ConvertTo-Json -Compress
