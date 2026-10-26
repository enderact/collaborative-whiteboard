<#
  Starts one backend instance in the foreground.

      .\scripts\run.ps1                 # instance wb-1 on port 8001
      .\scripts\run.ps1 -Port 8002 -Instance wb-2
#>
param(
  [int]$Port = 8001,
  [string]$Instance = "wb-1",
  [switch]$Reload
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "created .env from .env.example" -ForegroundColor Yellow
}

$env:INSTANCE_ID = $Instance
$args = @("-m", "uvicorn", "app.main:app", "--port", $Port, "--host", "127.0.0.1")
if ($Reload) { $args += "--reload" }

Write-Host "starting $Instance on http://127.0.0.1:$Port" -ForegroundColor Cyan
& ".\.venv\Scripts\python.exe" @args
