param(
  [string]$FrpcExe = "$PSScriptRoot\frpc.exe",
  [string]$Config = "$PSScriptRoot\frpc.local.toml"
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $FrpcExe)) {
  throw "frpc.exe not found: $FrpcExe"
}

if (-not (Test-Path -LiteralPath $Config)) {
  throw "frpc config not found: $Config"
}

Write-Host "Starting FRPC with config: $Config"
& $FrpcExe -c $Config
