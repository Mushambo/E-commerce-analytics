# evidence.ps1 - shows each output one at a time so you can take the report screenshots.
# Run from the project folder:   .\evidence.ps1          (or  .\evidence.ps1 -Step 3  for one step)
param([int]$Step = 0)
Set-Location $PSScriptRoot

function Pause-ForShot($title) {
    Write-Host "`n>>> Take the screenshot for: $title   then press Enter to continue" -ForegroundColor Yellow
    [void](Read-Host)
    Clear-Host
}

if ($Step -in 0, 1) {
    Clear-Host
    Write-Host "=== 1. MongoDB: document count + pipeline 1 (top-selling products) ===" -ForegroundColor Cyan
    Get-Content mongodb\evidence.js | docker exec -i mongo mongosh ecommerce --quiet
    Pause-ForShot "MongoDB"
}
if ($Step -in 0, 2) {
    Write-Host "=== 2. HBase shell: list, describe, prefix scan of user_000042 ===" -ForegroundColor Cyan
    Get-Content hbase\evidence.hbase | docker exec -i hbase hbase shell -n 2>$null
    Pause-ForShot "HBase shell"
}
if ($Step -in 0, 3) {
    Write-Host "=== 3. Spark cleaning job (data-quality counts) ===" -ForegroundColor Cyan
    docker compose exec -T app python spark/01_clean_normalize.py 2>$null
    Write-Host "`n--- data quality report ---" -ForegroundColor Cyan
    Get-Content output\data_quality_report.csv
    Pause-ForShot "Spark 01_clean_normalize"
}
if ($Step -in 0, 4) {
    Write-Host "=== 4. Integrated CLV analysis (MongoDB + HBase via Spark) ===" -ForegroundColor Cyan
    docker compose exec -T app python integration/clv_analysis.py --mongo mongo --hbase hbase 2>$null
    Pause-ForShot "CLV segment table"
}
Write-Host "Done." -ForegroundColor Green
