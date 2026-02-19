param(
    [string]$Endpoint = ""
)

if ([string]::IsNullOrWhiteSpace($Endpoint)) {
    Write-Host "Usage:"
    Write-Host "  .\\check_endpoints.ps1 -Endpoint \"wss://gw.example.com/device\""
    exit 1
}

function Parse-Endpoint([string]$raw) {
    try {
        $uri = [System.Uri]$raw
        if (-not $uri.Host) { return $null }
        $port = $uri.Port
        if ($port -le 0) {
            if ($uri.Scheme -eq "wss") { $port = 443 } else { $port = 80 }
        }
        return [PSCustomObject]@{
            Raw = $raw
            Host = $uri.Host
            Port = $port
            Scheme = $uri.Scheme
        }
    } catch {
        return $null
    }
}

$ep = Parse-Endpoint $Endpoint
if ($null -eq $ep) {
    Write-Host "[INVALID] $Endpoint"
    exit 1
}

Write-Host "Endpoint probe start..."
$ok = Test-NetConnection -ComputerName $ep.Host -Port $ep.Port -InformationLevel Quiet
if ($ok) {
    Write-Host "[OK]    $($ep.Raw)"
    exit 0
} else {
    Write-Host "[FAIL]  $($ep.Raw)"
    exit 2
}
