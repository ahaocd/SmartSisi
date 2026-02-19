# ESP32-C3 MicroPython固件上传与日志监控指南

## 🎯 固件上传命令

### ✅ 方法1：esptool.py上传（推荐）

```powershell
# 进入项目目录
cd E:\liusisi\SmartSisi\llm\a2a\tools\micropythone_sisidesk

# 1. 擦除Flash（重要！）
esptool.py --chip esp32c3 --port COM25 erase_flash

# 2. 上传MicroPython固件
esptool.py --chip esp32c3 --port COM25 --baud 460800 write_flash -z 0x0 sisi.bin

# 3. 验证上传（可选）
esptool.py --chip esp32c3 --port COM25 verify_flash 0x0 sisi.bin
```

### ✅ 方法2：ESP-IDF工具链上传

```powershell
# 如果您有ESP-IDF环境
idf.py -p COM29 -b 460800 flash

# 或者使用esptool.py（ESP-IDF内置）
python %IDF_PATH%\components\esptool_py\esptool\esptool.py --chip esp32c3 --port COM29 --baud 460800 write_flash -z 0x0 sisi.bin
```

### ✅ 方法3：一键上传脚本

```powershell
# 创建批处理文件 upload_firmware.bat
@echo off
echo 正在上传ESP32-C3 MicroPython固件...
cd /d E:\liusisi\SmartSisi\llm\a2a\tools\micropythone_sisidesk
esptool.py --chip esp32c3 --port COM24 erase_flash
timeout /t 2 /nobreak >nul
esptool.py --chip esp32c3 --port COM24 --baud 460800 write_flash -z 0x0 sisi.bin
echo 固件上传完成！
pause
```

## 🔍 PowerShell日志监控

### ✅ 方法1：mpremote实时监控（推荐）

```powershell
# 基本日志监控
cd E:\liusisi\SmartSisi\llm\a2a\tools\micropythone_sisidesk
mpremote connect COM24

# 进入REPL交互模式
mpremote connect COM24 repl

# 一键监控（单行命令）
cd E:\liusisi\SmartSisi\llm\a2a\tools\micropythone_sisidesk; mpremote connect COM24
```

### ✅ 方法2：Python串口监控

```powershell
# 基础监控
python -m serial.tools.miniterm COM24 115200

# 带过滤的监控
python -m serial.tools.miniterm COM24 115200 --eol LF --filter direct

# 原始数据监控
python -m serial.tools.miniterm COM24 115200 --raw
```

### ✅ 方法3：PowerShell原生串口监控

```powershell
# 单行命令（复制粘贴即可使用）
$port = New-Object System.IO.Ports.SerialPort COM2,115200; $port.Open(); Write-Host "ESP32-C3日志监控启动 - COM29:115200" -ForegroundColor Green; try { while($true) { if($port.BytesToRead -gt 0) { $data = $port.ReadExisting(); Write-Host $data -NoNewline -ForegroundColor Cyan }; Start-Sleep -Milliseconds 50 } } catch { Write-Host "`n连接中断" -ForegroundColor Red } finally { $port.Close(); Write-Host "串口已关闭" -ForegroundColor Yellow }

# 多行版本（更易读）
$port = New-Object System.IO.Ports.SerialPort COM29,115200
$port.Open()
Write-Host "ESP32-C3日志监控启动 - COM29:115200" -ForegroundColor Green
try {
    while($true) {
        if($port.BytesToRead -gt 0) {
            $data = $port.ReadExisting()
            Write-Host $data -NoNewline -ForegroundColor Cyan
        }
        Start-Sleep -Milliseconds 50
    }
} catch {
    Write-Host "`n连接中断" -ForegroundColor Red
} finally {
    $port.Close()
    Write-Host "串口已关闭" -ForegroundColor Yellow
}
```

## 🚀 完整操作流程

### 📋 固件上传流程

```powershell
# 1. 进入项目目录
cd E:\liusisi\SmartSisi\llm\a2a\tools\micropythone_sisidesk

# 2. 擦除并上传固件
esptool.py --chip esp32c3 --port COM25 erase_flash; esptool.py --chip esp32c3 --port COM25--baud 460800 write_flash -z 0x0 sisi.bin

# 3. 等待重启（约5秒）
timeout /t 5 /nobreak

# 4. 开始监控日志
mpremote connect COM29
```

### 📋 代码上传流程

```powershell
# 1. 上传核心文件
mpremote connect COM24 cp boot.py config.py main.py sisi_desk.py led.py motor.py :

# 2. 重启设备
mpremote connect COM24 exec "import machine; machine.reset()"

# 3. 监控启动日志
mpremote connect COM29
```

## ⚠️ 故障排除

### 🔧 COM端口问题

```powershell
# 检查端口状态
mode COM24

# 查看可用端口
mpremote connect list

# 重新插拔USB后重试
```

### 🔧 上传失败处理

```powershell
# 1. 降低波特率重试
esptool.py --chip esp32c3 --port COM24 --baud 115200 write_flash -z 0x0 sisi.bin

# 2. 手动进入下载模式
# 按住BOOT键，按一下RESET键，松开BOOT键

# 3. 检查驱动程序
# 设备管理器 -> 端口 -> 确认COM24正常
```

## 🎯 快速命令参考

### 一键操作命令

```powershell
# 固件上传+监控
cd E:\liusisi\SmartSisi\llm\a2a\tools\micropythone_sisidesk; esptool.py --chip esp32c3 --port COM29 erase_flash; esptool.py --chip esp32c3 --port COM29 --baud 460800 write_flash -z 0x0 sisi.bin; timeout /t 3; mpremote connect COM29

# 代码上传+重启+监控
cd E:\liusisi\SmartSisi\llm\a2a\tools\micropythone_sisidesk; mpremote connect COM29 cp *.py :; mpremote connect COM29 exec "import machine; machine.reset()"; mpremote connect COM29

# 仅监控日志
cd E:\liusisi\SmartSisi\llm\a2a\tools\micropythone_sisidesk; mpremote connect COM29
```

## 📞 退出方式

- **mpremote**: `Ctrl+X` 或 `Ctrl+C`
- **miniterm**: `Ctrl+]`
- **PowerShell串口**: `Ctrl+C`

---

**更新时间**: 2025-06-30
**适用设备**: ESP32-C3-MINI-1-V2.4.2.0
**固件**: MicroPython (sisi.bin)
**串口**: COM29, 115200波特率

