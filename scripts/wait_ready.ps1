$ready = $false
for ($i = 1; $i -le 60; $i++) {
    Start-Sleep -Milliseconds 1000
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:7860/" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($r.StatusCode -eq 200) {
            Write-Output ("READY at attempt " + $i)
            $ready = $true
            break
        }
    }
    catch {
        Write-Output ("attempt " + $i + ": " + $_.Exception.Message)
    }
}
if (-not $ready) { Write-Output "NOT READY after 60s" }
netstat -ano | Select-String ":7860" | Where-Object { $_ -match "LISTENING" } | Out-String