# ============================================================
# Performance Test Runner (Windows)
# Network Engineer: Israr Sadaq
# ============================================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Network Performance Test Runner" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Install Python dependencies
Write-Host "`n[1/3] Installing dependencies..." -ForegroundColor Yellow
pip install iperf3 requests

# Run single test
Write-Host "`n[2/3] Running performance tests..." -ForegroundColor Yellow
python latency_framework.py --config configs/default.json --once

Write-Host "`n[3/3] Test complete!" -ForegroundColor Green
Write-Host "Reports saved to: reports/" -ForegroundColor Yellow