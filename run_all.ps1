# run_all.ps1 - run the whole project from Windows PowerShell using Docker.
#
#   cd "<folder that contains docker-compose.yml>"
#   .\run_all.ps1                 # 10% dataset (200k sessions), live MongoDB + HBase
#   .\run_all.ps1 -Scale 1.0      # full dataset (2M sessions) - needs ~8 GB RAM for Docker
#   .\run_all.ps1 -Offline        # no databases (mongomock + HBase emulator)
#
# If PowerShell blocks the script:  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
param(
    [double]$Scale = 0.1,
    [switch]$Offline
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "`n=== Starting containers (mongo, hbase, app) ===" -ForegroundColor Cyan
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw "docker compose failed - is Docker Desktop running?" }

Write-Host "`n=== Running the pipeline inside the 'app' container ===" -ForegroundColor Cyan
$cmd = @("compose", "exec", "-e", "SCALE=$Scale", "app", "bash", "run_all.sh")
if ($Offline) { $cmd += "--offline" }
docker @cmd
if ($LASTEXITCODE -ne 0) { throw "pipeline failed - see the messages above" }

if (-not $Offline) {
    Write-Host "`n=== HBase tables (from the HBase shell) ===" -ForegroundColor Cyan
    "list`ndescribe 'user_sessions'`nscan 'user_sessions', {ROWPREFIXFILTER => 'user_000042|', COLUMNS => ['info'], LIMIT => 3}" |
        docker exec -i hbase hbase shell -n
}

Write-Host "`nDone. Results: .\output   Figures: .\report\figures" -ForegroundColor Green
Write-Host "MongoDB: mongodb://localhost:27017   HBase UI: http://localhost:16010"
