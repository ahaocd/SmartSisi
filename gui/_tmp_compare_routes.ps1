$regexBackend = "@__app\.route\('([^']+)'"
$regexFront = "[\"'](/api/[^\"']+|/v1/[^\"']+|/to_[^\"']+|/transparent_pass)[\"']"
$backend = Select-String -Path "e:\liusisi\SmartSisi\gui\flask_server.py" -Pattern $regexBackend | ForEach-Object {
  if ($_.Matches.Count -gt 0) { $_.Matches[0].Groups[1].Value }
}
$frontend = Get-ChildItem -Recurse -File -Path "e:\liusisi\SmartSisi\gui\frontend\src" | Select-String -Pattern $regexFront | ForEach-Object {
  foreach ($m in $_.Matches) { $m.Groups[1].Value }
}
$backendSet = $backend | Sort-Object -Unique
$frontendSet = $frontend | Sort-Object -Unique
Write-Output "=== Frontend calls ==="
$frontendSet
Write-Output "=== Frontend only (no backend route) ==="
Compare-Object -ReferenceObject $backendSet -DifferenceObject $frontendSet | Where-Object { $_.SideIndicator -eq '=>' } | ForEach-Object { $_.InputObject }
Write-Output "=== Backend only (not called by frontend src) ==="
Compare-Object -ReferenceObject $backendSet -DifferenceObject $frontendSet | Where-Object { $_.SideIndicator -eq '<=' } | ForEach-Object { $_.InputObject }
