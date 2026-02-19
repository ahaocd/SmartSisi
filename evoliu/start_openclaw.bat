@echo off
echo Starting OpenClaw Gateway with ModelScope API...
echo.
echo Access URL: http://127.0.0.1:18789/?token=openclaw-dev-token-104826703
echo.
wsl -d Ubuntu -- bash -c "cd /home/sisi/openclaw && node dist/entry.js gateway --port 18789"
