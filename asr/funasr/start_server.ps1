# FunASR 独立环境启动脚本 (PowerShell)
# websockets: 12.0 (兼容版本)
# 模型缓存: 使用已有的 C:\Users\senlin\.cache\modelscope

Write-Host "========================================"
Write-Host "  FunASR 独立环境启动器"
Write-Host "  websockets: 12.0 (兼容版本)"
Write-Host "  模型缓存: 使用已有模型，无需重新下载"
Write-Host "========================================"
Write-Host ""

# 设置模型缓存目录
$env:MODELSCOPE_CACHE = "C:\Users\senlin\.cache\modelscope\hub"

# 切换到脚本目录
Set-Location $PSScriptRoot

# 激活虚拟环境
& ".\venv\Scripts\Activate.ps1"

Write-Host "正在启动 FunASR 服务..."
python -u ASR_server.py --host "0.0.0.0" --port 10197 --ngpu 0
