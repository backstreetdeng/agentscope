param(
    [Parameter(Mandatory=$true)][string]$InputPath,
    [Parameter(Mandatory=$true)][string]$ScopePath,
    [Parameter(Mandatory=$true)][string]$OutputDir
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$inputResolved = (Resolve-Path -LiteralPath $InputPath).Path
$scopeResolved = (Resolve-Path -LiteralPath $ScopePath).Path
$outputResolved = [System.IO.Path]::GetFullPath($OutputDir)
[void][System.IO.Directory]::CreateDirectory($outputResolved)
$auditPath = Join-Path $outputResolved 'powerpoint-measurements.json'
$manifest = Get-Content -Raw -LiteralPath $scopeResolved -Encoding UTF8 | ConvertFrom-Json
$measurements = [System.Collections.Generic.List[object]]::new()
$obstacles = [System.Collections.Generic.List[object]]::new()
$issues = [System.Collections.Generic.List[object]]::new()
$app = $null
$deck = $null
$roundtrip = $null

function File-Sha256([string]$path) {
    # Use .NET rather than Get-FileHash: the packaged Python subprocess can
    # inherit a restricted PSModulePath without the optional utility cmdlet.
    $stream = [System.IO.File]::OpenRead($path)
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try { return ([System.BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}

function New-IsolatedPowerPoint {
    if (@([System.Diagnostics.Process]::GetProcessesByName('POWERPNT')).Count -gt 0) {
        throw 'user_or_other_powerpoint_active: Refusing to attach to an existing PowerPoint process.'
    }
    return New-Object -ComObject PowerPoint.Application
}

function Release-OwnedPowerPoint($application) {
    try {
        try {
            if ($application.Presentations.Count -eq 0) { $application.Quit() }
            else { throw 'user_presentation_opened_during_validation: Remaining user presentations were left open.' }
        } catch {
            # Hidden PowerPoint may exit on its own after its last deck closes.
            # Only that zero-process RPC shutdown is benign; never kill/reuse
            # another application or disregard a still-active user's deck.
            if (@([System.Diagnostics.Process]::GetProcessesByName('POWERPNT')).Count -gt 0 -or $_.Exception.Message -notmatch '0x800706BA|RPC server is unavailable') { throw }
        }
    } finally { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($application) }
}

$result = [ordered]@{
    schema_version=1; gate='macro_layout_measurements'; success=$false;
    measurement_id=$manifest.measurement_id;
    artifact_path=$inputResolved; artifact_sha256=(File-Sha256 $inputResolved);
    measured_at=[DateTime]::UtcNow.ToString('o'); slide_width=$null; slide_height=$null;
    office_passed=$false; slides=0; rendered=0; roundtrip_slides=0;
    measurements=$measurements; obstacles=$obstacles; issues=$issues
}

function Find-Shape($shapes, [int]$shapeId) {
    foreach ($shape in $shapes) {
        if ($shape.Id -eq $shapeId) { return $shape }
        if ($shape.Type -eq 6) {
            $found = Find-Shape $shape.GroupItems $shapeId
            if ($null -ne $found) { return $found }
        }
    }
    return $null
}

function Add-Obstacles($shapes, [int]$slideNumber) {
    foreach ($shape in $shapes) {
        if ($shape.Visible -eq 0) { continue }
        if ($shape.Type -eq 6) { Add-Obstacles $shape.GroupItems $slideNumber; continue }
        $kind = if ($shape.HasChart -eq -1) { 'chart' } elseif ($shape.HasTable -eq -1) { 'table' } else { $null }
        if ($null -ne $kind) {
            $obstacles.Add([pscustomobject]@{slide=$slideNumber;shape_id=$shape.Id;kind=$kind;
                box=[pscustomobject]@{x=[double]$shape.Left;y=[double]$shape.Top;width=[double]$shape.Width;height=[double]$shape.Height}})
        }
    }
}

try {
    # PowerPoint COM can reuse an existing instance. Refuse rather than risk
    # touching or closing a user's open presentation.
    if (@([System.Diagnostics.Process]::GetProcessesByName('POWERPNT')).Count -gt 0) {
        throw 'user_powerpoint_active: Close PowerPoint or retry later; existing user presentations are untouched.'
    }
    if ($result.artifact_sha256 -ne $manifest.artifact_sha256) { throw 'artifact_hash_changed_before_measurement' }
    $app = New-IsolatedPowerPoint
    $deck = $app.Presentations.Open($inputResolved, $true, $false, $false)
    $result.slides = [int]$deck.Slides.Count
    $copyPath = Join-Path $outputResolved 'office-roundtrip.pptx'
    $deck.SaveCopyAs($copyPath, 24)
    $deck.Close()
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($deck)
    $deck=$null
    try { Release-OwnedPowerPoint $app } finally { $app=$null }
    $app=New-IsolatedPowerPoint
    $roundtrip=$app.Presentations.Open($copyPath, $true, $false, $false)
    $result.roundtrip_slides=[int]$roundtrip.Slides.Count
    $roundtrip.Close()
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($roundtrip)
    $roundtrip=$null
    try { Release-OwnedPowerPoint $app } finally { $app=$null }
    # All measurements and renders belong to the ORIGINAL same-hash artifact,
    # not to Office's diagnostic normalization copy.
    $app=New-IsolatedPowerPoint
    $deck=$app.Presentations.Open($inputResolved, $true, $false, $false)
    $result.slide_width = [double]$deck.PageSetup.SlideWidth
    $result.slide_height = [double]$deck.PageSetup.SlideHeight
    $renderDir = Join-Path $outputResolved 'rendered'
    [void][System.IO.Directory]::CreateDirectory($renderDir)
    for ($slideNumber=1; $slideNumber -le $deck.Slides.Count; $slideNumber++) {
        $slide = $deck.Slides.Item([int]$slideNumber)
        # Export forces Office to lay out the same read-only artifact before
        # BoundHeight/BoundWidth are sampled. The audit never saves the deck.
        $slide.Export((Join-Path $renderDir ("slide-{0:D2}.png" -f [int]$slideNumber)), 'PNG', 1920, 1080)
        $result.rendered++
        Add-Obstacles $slide.Shapes ([int]$slideNumber)
    }
    $result.office_passed=($result.slides -eq 33 -and $result.rendered -eq 33 -and $result.roundtrip_slides -eq 33)
    if (-not $result.office_passed) { $issues.Add([pscustomobject]@{code='macro_office_roundtrip_or_render_incomplete';slides=$result.slides;rendered=$result.rendered;roundtrip_slides=$result.roundtrip_slides}) }
    foreach ($target in $manifest.targets) {
        $item = [ordered]@{slide=[int]$target.slide;shape_id=[int]$target.shape_id;role=$target.role;
            kind=$target.kind;cell_row=$target.cell_row;cell_column=$target.cell_column;measured=$false}
        try {
            $slide = $deck.Slides.Item([int]$target.slide)
            $container = Find-Shape $slide.Shapes ([int]$target.shape_id)
            if ($null -eq $container) { throw 'shape_missing' }
            if ($container.Visible -eq 0) { throw 'required_text_not_visible' }
            $shape = $container
            $x=[double]$shape.Left; $y=[double]$shape.Top; $width=[double]$shape.Width; $height=[double]$shape.Height
            if ($target.kind -eq 'table_cell') {
                if ($container.HasTable -ne -1) { throw 'required_table_missing' }
                $row=[int]$target.cell_row; $column=[int]$target.cell_column
                $table=$container.Table
                if ($row -lt 1 -or $row -gt $table.Rows.Count -or $column -lt 1 -or $column -gt $table.Columns.Count) { throw 'table_cell_missing' }
                $shape=$table.Cell($row,$column).Shape
                $x=[double]$container.Left; $y=[double]$container.Top
                for ($index=1; $index -lt $column; $index++) { $x += [double]$table.Columns.Item($index).Width }
                for ($index=1; $index -lt $row; $index++) { $y += [double]$table.Rows.Item($index).Height }
                $width=[double]$table.Columns.Item($column).Width; $height=[double]$table.Rows.Item($row).Height
                if ($target.row_span -gt 1) {
                    for ($index=1; $index -lt [int]$target.row_span; $index++) { $height += [double]$table.Rows.Item($row+$index).Height }
                }
                if ($target.column_span -gt 1) {
                    for ($index=1; $index -lt [int]$target.column_span; $index++) { $width += [double]$table.Columns.Item($column+$index).Width }
                }
            }
            if ($shape.HasTextFrame -ne -1) { throw 'required_text_frame_missing' }
            $frame=$shape.TextFrame2
            $range=$frame.TextRange
            $item.text=[string]$range.Text
            $item.visible=$true; $item.rotation=[double]$shape.Rotation
            $item.text_box=[pscustomobject]@{x=$x;y=$y;width=$width;height=$height;
                margin_left=[double]$frame.MarginLeft;margin_right=[double]$frame.MarginRight;
                margin_top=[double]$frame.MarginTop;margin_bottom=[double]$frame.MarginBottom}
            $item.rendered_bounds=[pscustomobject]@{x=[double]$range.BoundLeft;y=[double]$range.BoundTop;
                width=[double]$range.BoundWidth;height=[double]$range.BoundHeight}
            $item.font_size=[double]$range.Font.Size
            $item.auto_size=[int]$frame.AutoSize
            $item.measurement_method='PowerPoint.TextRange2.Bound* after slide export'
            $item.measured=$true
        } catch {
            $item.error=$_.Exception.Message
            $issues.Add([pscustomobject]@{code='text_measurement_unavailable';slide=$target.slide;shape_id=$target.shape_id;
                cell_row=$target.cell_row;cell_column=$target.cell_column;detail=$_.Exception.Message})
        }
        $measurements.Add([pscustomobject]$item)
    }
    $result.success = ($issues.Count -eq 0 -and $measurements.Count -eq @($manifest.targets).Count -and $measurements.Count -gt 0)
} catch {
    $issues.Add([pscustomobject]@{code='powerpoint_measurement_unavailable';detail=$_.Exception.Message})
} finally {
    if ($null -ne $roundtrip) {
        try { $roundtrip.Close() } catch { $issues.Add([pscustomobject]@{code='owned_roundtrip_close_failed';detail=$_.Exception.Message}); $result.success=$false; $result.office_passed=$false }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($roundtrip)
    }
    if ($null -ne $deck) {
        try { $deck.Close() } catch { $issues.Add([pscustomobject]@{code='owned_deck_close_failed';detail=$_.Exception.Message}); $result.success=$false }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($deck)
    }
    if ($null -ne $app) {
        # No process-wide kill is used. There was no existing user instance,
        # and only this validator-created application is asked to quit. If a
        # user opens a deck during validation, leave their application alive.
        try { Release-OwnedPowerPoint $app }
        catch { $issues.Add([pscustomobject]@{code='owned_application_quit_failed';detail=$_.Exception.Message}); $result.success=$false }
    }
    [GC]::Collect(); [GC]::WaitForPendingFinalizers()
    $afterHash=File-Sha256 $inputResolved
    if ($afterHash -ne $result.artifact_sha256) { $issues.Add([pscustomobject]@{code='artifact_changed_during_measurement'}); $result.success=$false; $result.office_passed=$false }
    $result | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath $auditPath -Encoding UTF8
}
[pscustomobject]@{success=$result.success;full_report=$auditPath;measured=$measurements.Count;issues=$issues.Count} | ConvertTo-Json -Compress
if (-not $result.success) { exit 1 }
