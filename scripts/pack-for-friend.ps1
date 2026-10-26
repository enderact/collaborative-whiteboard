<#
  Builds a zip your friend can unpack and run. Leaves out the virtualenv,
  logs, local .env, and Python cache so the archive stays small.

      .\scripts\pack-for-friend.ps1
      .\scripts\pack-for-friend.ps1 -Out D:\whiteboard-handoff.zip
#>
param(
  [string]$Out = (Join-Path (Split-Path $PSScriptRoot -Parent) "..\whiteboard-handoff.zip")
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$Out = [IO.Path]::GetFullPath($Out)
$staging = Join-Path $env:TEMP ("whiteboard-handoff-" + [guid]::NewGuid().ToString("N"))
$skipDirNames = @(".venv", "__pycache__", "logs", ".git")
$skipFiles = @(".env", ".demo-pids")

function Copy-Tree($src, $dst) {
  New-Item -ItemType Directory -Path $dst -Force | Out-Null
  Get-ChildItem $src -Force | ForEach-Object {
    if ($_.PSIsContainer) {
      if ($skipDirNames -contains $_.Name) { return }
      Copy-Tree $_.FullName (Join-Path $dst $_.Name)
    } else {
      if ($skipFiles -contains $_.Name) { return }
      if ($_.Extension -eq ".pyc") { return }
      Copy-Item $_.FullName (Join-Path $dst $_.Name) -Force
    }
  }
}

Copy-Tree $root $staging

if (Test-Path $Out) { Remove-Item $Out -Force }
Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $Out -CompressionLevel Optimal
Remove-Item $staging -Recurse -Force

$sizeMb = [math]::Round((Get-Item $Out).Length / 1MB, 1)
Write-Host "packed $Out  ($sizeMb MB)" -ForegroundColor Green
Write-Host "Send that zip. Tell your friend to read README.md first."
