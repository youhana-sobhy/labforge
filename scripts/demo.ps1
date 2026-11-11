# Scripted demo against a running LabForge (http://localhost:8080) using its REST API.
$ErrorActionPreference = "Stop"
$api = "http://localhost:8080/api"
function Say($t) { Write-Host "`n== $t" -ForegroundColor DarkYellow }
function Pause-Demo { if (-not $env:NO_PAUSE) { Read-Host "   (enter to continue)" | Out-Null } }
function Show-Tests($run) {
  foreach ($r in $run.results) {
    $c = if ($r.ok) { "Green" } else { "Red" }
    Write-Host ("  {0} {1}  ({2})" -f ($(if ($r.ok) { "PASS" } else { "FAIL" })), $r.name, $r.detail) -ForegroundColor $c
  }
  Write-Host ("{0}/{1} tests passed" -f $run.passed, $run.total)
}

Say "Launch the Market Branch Office lab"
$lab = Invoke-RestMethod "$api/labs" -Method Post -ContentType application/json `
  -Body (@{ template = "branch-office"; name = "Demo branch"; owner = $env:USERNAME; ttl_minutes = 30 } | ConvertTo-Json)
do { Start-Sleep 1; $lab = Invoke-RestMethod "$api/labs/$($lab.id)" } while ($lab.status -eq "deploying")
Write-Host "$($lab.id) is $($lab.status), ready in $($lab.deploy_seconds)s. Open http://localhost:8080/#/labs/$($lab.id)"
Pause-Demo

Say "Run the built-in tests"
Show-Tests (Invoke-RestMethod "$api/labs/$($lab.id)/checks" -Method Post); Pause-Demo

Say "Push a BAD firewall change: guests may now go anywhere"
$tpl = Invoke-RestMethod "$api/catalog/branch-office"
$good = $tpl.topology.nodes.fw1.ruleset
$bad = $good -replace 'iifname "eth3" oifname "eth2"', 'iifname "eth3"'
$res = Invoke-RestMethod "$api/labs/$($lab.id)/nodes/fw1/config" -Method Post -ContentType application/json `
  -Body (@{ text = $bad; by = "demo" } | ConvertTo-Json)
Write-Host $res.output; Pause-Demo

Say "Run the tests again"
Show-Tests (Invoke-RestMethod "$api/labs/$($lab.id)/checks" -Method Post); Pause-Demo

Say "Roll back and prove it"
Invoke-RestMethod "$api/labs/$($lab.id)/nodes/fw1/config" -Method Post -ContentType application/json `
  -Body (@{ text = $good; by = "demo" } | ConvertTo-Json) | Out-Null
Show-Tests (Invoke-RestMethod "$api/labs/$($lab.id)/checks" -Method Post); Pause-Demo

Say "Destroy the lab"
Invoke-RestMethod "$api/labs/$($lab.id)" -Method Delete | Out-Null
Write-Host "Destroyed." -ForegroundColor Green
