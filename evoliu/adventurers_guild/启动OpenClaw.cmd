@echo off
chcp 65001 >nul
set OPENCLAW_CONFIG_PATH=E:\liusisi\SmartSisi\evoliu\adventurers_guild\openclaw\openclaw_config\openclaw.json
set OPENCLAW_STATE_DIR=E:\liusisi\SmartSisi\evoliu\adventurers_guild\openclaw\openclaw_config
cd /d E:\liusisi\SmartSisi\evoliu\adventurers_guild\openclaw
echo ========================================
echo OpenClaw Starting...
echo Config: %OPENCLAW_CONFIG_PATH%
echo Model: Claude Opus 4.6 (Free)
echo Port: http://127.0.0.1:18789
echo ========================================
node dist\entry.js gateway --port 18789
