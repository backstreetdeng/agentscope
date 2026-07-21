param(
    [Parameter(Mandatory = $true)]
    [string]$TargetProject,

    [string]$Python = "python",

    [switch]$Apply,

    [switch]$Force
)

$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "scripts\install_into_project.py"
$arguments = @($script, "--target", $TargetProject)

if ($Apply) {
    $arguments += "--apply"
}
if ($Force) {
    $arguments += "--force"
}

& $Python @arguments
exit $LASTEXITCODE
