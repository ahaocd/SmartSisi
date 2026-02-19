# Network Lane

This folder contains network-access templates for cross-network reachability.

## Files

1. `profiles.example.env`: canonical endpoint and bridge ports.
2. `frp/frps.toml.example`: server-side tunnel template.
3. `frp/frpc_pc.toml.example`: PC-side tunnel template.
4. `check_endpoints.ps1`: host-side canonical endpoint probe.

## Probe Example

```powershell
.\check_endpoints.ps1 -Endpoint "wss://gw.example.com/device"
```
