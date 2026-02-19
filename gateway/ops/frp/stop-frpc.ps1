Get-Process -Name frpc -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Host "Stopped frpc processes (if any)."
