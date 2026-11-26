# entry point: monitor + orchestrator, output to run-all.log

$Root = Split-Path $PSScriptRoot -Parent

# fresh unzip has no logs/ or data/
foreach ($d in @('logs', 'data')) {
  $full = Join-Path $Root $d
  if (-not (Test-Path $full)) { New-Item -ItemType Directory -Force -Path $full | Out-Null }
}
$RunLog = Join-Path $Root 'logs\run-all.log'

# closing the monitor does not stop the job, kill leftovers
$stale = 'hidden-run\.ps1|launch\.ps1|监控\.ps1|core\\cli\.py'
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match $stale } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 900

Remove-Item $RunLog -Force -ErrorAction SilentlyContinue

$mon = Join-Path $PSScriptRoot '监控.ps1'
if (Test-Path $mon) {
  $running = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
              Where-Object { $_.CommandLine -like '*监控.ps1*' }).Count
  if ($running -eq 0) {
    Start-Process -FilePath 'powershell' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',$mon) | Out-Null
    Start-Sleep -Milliseconds 1500
  }
}

& (Join-Path $PSScriptRoot 'launch.ps1') *> $RunLog
