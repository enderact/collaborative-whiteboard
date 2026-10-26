# Start a backend, re-collect every measurement against it, then stop it again.
# Used after changing anything the document quotes, so the numbers and the code
# cannot disagree.
param([int]$Port = 8061)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

$job = Start-Job -ScriptBlock {
    param($root, $port)
    Set-Location $root
    $env:WB_INSTANCE_ID = "wb-measure"
    & "$root\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port $port
} -ArgumentList $root, $Port

try {
    $base = "http://127.0.0.1:$Port"
    $ready = $false
    foreach ($i in 1..40) {
        Start-Sleep -Milliseconds 750
        try {
            $h = Invoke-RestMethod "$base/api/admin/health" -TimeoutSec 4
            if ($h) { $ready = $true; break }
        } catch { }
    }
    if (-not $ready) {
        "server did not come up on $Port"
        Receive-Job $job
        exit 1
    }
    "server ready on $Port"
    & "$root\.venv\Scripts\python.exe" scripts\collect_measurements.py --base $base
} finally {
    Stop-Job $job -ErrorAction SilentlyContinue
    Remove-Job $job -Force -ErrorAction SilentlyContinue
    Pop-Location
}
