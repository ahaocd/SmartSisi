param(
    [int]$Port = 9102
)

$matches = netstat -ano | Select-String -Pattern (":$Port\\s+.*LISTENING\\s+(\\d+)$")
if (-not $matches) {
    Write-Host "No gateway process is listening on port $Port."
    exit 0
}

$pids = @()
foreach ($m in $matches) {
    $parts = ($m.Line -split '\s+') | Where-Object { $_ -ne "" }
    if ($parts.Count -ge 5) {
        $pid = [int]$parts[-1]
        if ($pid -gt 0) {
            $pids += $pid
        }
    }
}

$pids = $pids | Select-Object -Unique
foreach ($pid in $pids) {
    try {
        Stop-Process -Id $pid -Force
        Write-Host "Stopped PID $pid on port $Port."
    } catch {
        Write-Host ("Failed to stop PID {0}: {1}" -f $pid, $_.Exception.Message)
    }
}
