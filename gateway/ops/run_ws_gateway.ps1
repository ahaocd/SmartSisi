param(
    [string]$Host = "0.0.0.0",
    [int]$Port = 9102,
    [string]$MediaBackend = "ws://127.0.0.1:9002",
    [string]$ControlBackend = "ws://127.0.0.1:9003",
    [string]$AccessToken = "",
    [string]$LogLevel = "INFO"
)

$root = Split-Path -Parent $PSScriptRoot
$projectRoot = Split-Path -Parent $root

Push-Location $projectRoot
try {
    python -m gateway.app.ws_gateway_server `
        --host $Host `
        --port $Port `
        --media-backend $MediaBackend `
        --control-backend $ControlBackend `
        --access-token $AccessToken `
        --log-level $LogLevel
} finally {
    Pop-Location
}
