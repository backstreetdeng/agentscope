$oldPid = (Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq 7860 }).OwningProcess
if (-not $oldPid) { $oldPid = (netstat -ano -p TCP | Select-String ":7860\s+.*LISTENING\s+(\d+)$").Matches[0].Groups[1].Value }
Write-Output ("killing PID=" + $oldPid)
Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 1500
$env:PYTHONUTF8 = '1'
$env:AGENT_SERVER_NAME = '0.0.0.0'
$proc = Start-Process -FilePath "E:\AI\data\envs\helloagent\Scripts\python.exe" -ArgumentList @('-u', 'E:\AI\data\envs\helloagent\myproject\app.py') -WorkingDirectory "E:\AI\data\envs\helloagent\myproject" -WindowStyle Hidden -PassThru
Write-Output ("spawned PID=" + $proc.Id)