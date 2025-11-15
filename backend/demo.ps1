# PowerShell demo script for Chrysalis

$API_URL = if ($env:API_URL) { $env:API_URL } else { "http://localhost:8000" }

Write-Host "Posting Batch A (no drift)..." -ForegroundColor Green
$responseA = Invoke-RestMethod -Uri "$API_URL/ingest" -Method Post -ContentType "application/json" -InFile "../fixtures/batch_A.json"
$responseA | ConvertTo-Json

Start-Sleep -Seconds 2

Write-Host "Posting Batch B (add field currency)..." -ForegroundColor Green
$responseB = Invoke-RestMethod -Uri "$API_URL/ingest" -Method Post -ContentType "application/json" -InFile "../fixtures/batch_B.json"
$responseB | ConvertTo-Json

Start-Sleep -Seconds 2

Write-Host "Posting Batch C (price type string)..." -ForegroundColor Green
$responseC = Invoke-RestMethod -Uri "$API_URL/ingest" -Method Post -ContentType "application/json" -InFile "../fixtures/batch_C.json"
$responseC | ConvertTo-Json

Write-Host "`nDone. Open Streamlit at http://localhost:8501 to view results." -ForegroundColor Cyan

