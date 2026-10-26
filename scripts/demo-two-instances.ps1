<#
  Starts two independent backend processes so the Redis Pub/Sub layer can be shown
  doing something a single process could not.

  Open the same room code on both ports in two browser windows. Each window shows
  the instance that served it in the top bar, and a stroke drawn in one appears in
  the other, which means the event crossed a process boundary through Redis.

      .\scripts\demo-two-instances.ps1
      .\scripts\demo-two-instances.ps1 -Stop
#>
param(
  [int]$PortA = 8001,
  [int]$PortB = 8002,
  [switch]$Stop
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$pidFile = Join-Path $root ".demo-pids"

if ($Stop) {
  if (-not (Test-Path $pidFile)) { Write-Host "nothing recorded as running"; exit 0 }
  Get-Content $pidFile | ForEach-Object {
    $processId = [int]$_
    $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($proc) { $proc.Kill(); Write-Host "stopped pid $processId" -ForegroundColor Yellow }
  }
  Remove-Item $pidFile -Force
  exit 0
}

if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }

$pids = @()
foreach ($cfg in @(@{ Port = $PortA; Name = "wb-1" }, @{ Port = $PortB; Name = "wb-2" })) {
  $env:INSTANCE_ID = $cfg.Name
  $proc = Start-Process -FilePath ".\.venv\Scripts\python.exe" `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--port", $cfg.Port, "--host", "127.0.0.1", "--log-level", "warning") `
    -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput "logs\$($cfg.Name).out.log" `
    -RedirectStandardError  "logs\$($cfg.Name).err.log"
  $pids += $proc.Id
  Write-Host "started $($cfg.Name) on http://127.0.0.1:$($cfg.Port)  (pid $($proc.Id))" -ForegroundColor Cyan
}
$pids | Set-Content $pidFile

Write-Host "`nwaiting for both instances to answer /api/admin/health ..." -NoNewline
foreach ($p in @($PortA, $PortB)) {
  for ($i = 0; $i -lt 60; $i++) {
    try { Invoke-RestMethod "http://127.0.0.1:$p/api/admin/health" -TimeoutSec 2 | Out-Null; break }
    catch { Start-Sleep -Milliseconds 500 }
  }
}
Write-Host " ready`n" -ForegroundColor Green
Write-Host "Open one board in each window, then draw:" -ForegroundColor White
Write-Host "  http://127.0.0.1:$PortA"
Write-Host "  http://127.0.0.1:$PortB"
Write-Host "`nStop both with:  .\scripts\demo-two-instances.ps1 -Stop" -ForegroundColor DarkGray
