param(
    [string]$Host = "0.0.0.0",
    [int]$Port = 9102,
    [string]$MediaBackend = "ws://127.0.0.1:9002",
    [string]$ControlBackend = "ws://127.0.0.1:9003",
    [string]$AccessToken = "",
    [string]$LogLevel = "INFO",
    [switch]$WithFrpc,
    [string]$FrpcExe = "$PSScriptRoot\frp\frpc.exe",
    [string]$FrpcConfig = "$PSScriptRoot\frp\frpc.local.toml"
)

$root = Split-Path -Parent $PSScriptRoot
$projectRoot = Split-Path -Parent $root
$frpcProcess = $null

if ($WithFrpc) {
    if (-not (Test-Path -LiteralPath $FrpcExe)) {
        throw "frpc.exe not found: $FrpcExe"
    }
    if (-not (Test-Path -LiteralPath $FrpcConfig)) {
        throw "frpc config not found: $FrpcConfig"
    }

    $frpcProcess = Start-Process -FilePath $FrpcExe -ArgumentList @("-c", $FrpcConfig) -PassThru -WindowStyle Hidden
    Start-Sleep -Milliseconds 600
    if ($frpcProcess.HasExited) {
        throw "frpc exited immediately with code $($frpcProcess.ExitCode)"
    }
    Write-Host "Started frpc PID=$($frpcProcess.Id) config=$FrpcConfig"
}

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
    if ($frpcProcess -and -not $frpcProcess.HasExited) {
        Stop-Process -Id $frpcProcess.Id -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped frpc PID=$($frpcProcess.Id)"
    }
    Pop-Location
}
