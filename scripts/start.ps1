# Start LabForge on Windows (Docker Desktop) and open it in the browser.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
docker info *> $null
if ($LASTEXITCODE -ne 0) { Write-Error "Docker Desktop is not running. Start it and try again." }
docker compose up -d --build
Write-Host "Waiting for LabForge..." -ForegroundColor Cyan
for ($i = 0; $i -lt 60; $i++) {
  try { Invoke-RestMethod http://localhost:8080/api/health | Out-Null; break } catch { Start-Sleep 1 }
}
Write-Host "Pre-pulling lab images (first run only)..." -ForegroundColor Cyan
docker pull -q frrouting/frr:v8.4.1 | Out-Null
docker pull -q nicolaka/netshoot:v0.14 | Out-Null
Start-Process "http://localhost:8080"
Write-Host "LabForge is running on http://localhost:8080" -ForegroundColor Green
