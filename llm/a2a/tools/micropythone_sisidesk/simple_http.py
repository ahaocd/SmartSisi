"""
simple_http.py - 紧急模式简易HTTP服务器
当主系统无法启动时提供基本Web界面
"""

import socket
import time
import json
from machine import Pin

# 全局状态
MOTOR_PIN1 = None
MOTOR_PIN2 = None
LED_PIN = None

def init_emergency_pins():
    """初始化紧急模式下的引脚"""
    global MOTOR_PIN1, MOTOR_PIN2, LED_PIN
    
    try:
        import config
        # 初始化基本引脚
        MOTOR_PIN1 = Pin(config.DC_MOTOR_IN1_PIN, Pin.OUT, value=0)
        MOTOR_PIN2 = Pin(config.DC_MOTOR_IN2_PIN, Pin.OUT, value=0)
        LED_PIN = Pin(config.LED_PIN, Pin.OUT, value=0)
        
        print("紧急模式: 引脚初始化成功")
        return True
    except Exception as e:
        print(f"紧急模式: 引脚初始化失败 - {e}")
        
        # 使用默认值
        try:
            MOTOR_PIN1 = Pin(5, Pin.OUT, value=0)
            MOTOR_PIN2 = Pin(6, Pin.OUT, value=0)
            LED_PIN = Pin(10, Pin.OUT, value=0)
            print("紧急模式: 使用默认引脚配置")
            return True
        except:
            print("紧急模式: 无法初始化默认引脚")
            return False

def generate_emergency_html():
    """生成紧急模式的HTML页面 - 极简版本"""
    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>紧急模式</title>
    <style>
        body {font-family:Arial; background:#ffebee; padding:10px}
        h1 {color:#c62828; text-align:center}
        .panel {background:white; padding:10px; margin:10px 0; border-radius:5px}
        .btn {padding:10px; margin:5px; background:#c62828; color:white; border:none; border-radius:3px}
        .btn-gray {background:#9e9e9e}
    </style>
</head>
<body>
    <h1>⚠️ 紧急模式 ⚠️</h1>
    <div class="panel">系统启动失败，已进入紧急模式。仅提供基本控制功能。</div>
    
    <div class="panel">
        <h2>电机控制</h2>
        <button class="btn" onclick="fetch('/api/motor/forward')">正转10秒</button>
        <button class="btn" onclick="fetch('/api/motor/backward')">反转10秒</button>
        <button class="btn btn-gray" onclick="fetch('/api/motor/stop')">停止</button>
    </div>
    
    <div class="panel">
        <h2>LED控制</h2>
        <button class="btn" onclick="fetch('/api/led/on')">打开</button>
        <button class="btn btn-gray" onclick="fetch('/api/led/off')">关闭</button>
    </div>
    
    <div class="panel">
        <h2>系统控制</h2>
        <button class="btn" onclick="fetch('/api/system/reboot')">重启系统</button>
    </div>
</body>
</html>
"""
    return html

def handle_emergency_api(endpoint):
    """处理紧急模式下的API请求"""
    global MOTOR_PIN1, MOTOR_PIN2, LED_PIN
    
    # 检查引脚是否已初始化
    if MOTOR_PIN1 is None or MOTOR_PIN2 is None or LED_PIN is None:
        if not init_emergency_pins():
            return {"success": False, "message": "引脚未初始化"}
    
    # 电机控制
    if endpoint == "motor/forward":
        MOTOR_PIN1.value(1)
        MOTOR_PIN2.value(0)
        time.sleep(10)  # 运行10秒
        MOTOR_PIN1.value(0)
        MOTOR_PIN2.value(0)
        return {"success": True, "message": "电机正转10秒"}
        
    elif endpoint == "motor/backward":
        MOTOR_PIN1.value(0)
        MOTOR_PIN2.value(1)
        time.sleep(10)  # 运行10秒
        MOTOR_PIN1.value(0)
        MOTOR_PIN2.value(0)
        return {"success": True, "message": "电机反转10秒"}
        
    elif endpoint == "motor/stop":
        MOTOR_PIN1.value(0)
        MOTOR_PIN2.value(0)
        return {"success": True, "message": "电机已停止"}
    
    # LED控制
    elif endpoint == "led/on":
        LED_PIN.value(1)
        return {"success": True, "message": "LED已打开"}
        
    elif endpoint == "led/off":
        LED_PIN.value(0)
        return {"success": True, "message": "LED已关闭"}
    
    # 系统控制
    elif endpoint == "system/reboot":
        import machine
        time.sleep(1)
        machine.reset()
        return {"success": True, "message": "系统正在重启..."}
    
    # 状态
    elif endpoint == "status":
        return {
            "success": True,
            "status": {
                "mode": "emergency",
                "motor": "停止" if MOTOR_PIN1.value() == 0 and MOTOR_PIN2.value() == 0 else "运行中",
                "led": "开启" if LED_PIN.value() == 1 else "关闭"
            },
            "message": "紧急模式状态"
        }
    
    # 未知命令
    else:
        return {"success": False, "message": f"未知命令: {endpoint}"}

def process_emergency_request(request_text):
    """处理紧急模式下的HTTP请求"""
    # 解析HTTP请求
    is_api_request = False
    command = None
    
    # 检查是否是API请求
    if "GET /api/" in request_text:
        is_api_request = True
        # 提取API命令
        cmd_start = request_text.find("/api/") + 5
        cmd_end = request_text.find(" ", cmd_start)
        command = request_text[cmd_start:cmd_end]
    
    # 生成HTTP响应
    if is_api_request:
        # 处理API请求
        result = handle_emergency_api(command)
        
        # 转换为JSON并构建响应
        import json
        json_data = json.dumps(result)
        
        # 确保使用UTF-8编码
        response = "HTTP/1.1 200 OK\r\n"
        response += "Content-Type: application/json; charset=utf-8\r\n"
        response += "Access-Control-Allow-Origin: *\r\n"  # CORS支持
        response += f"Content-Length: {len(json_data)}\r\n"
        response += "\r\n"
        response += json_data
        
    else:
        # 返回紧急模式页面
        html = generate_emergency_html()
        
        # 确保使用UTF-8编码头
        response = "HTTP/1.1 200 OK\r\n"
        response += "Content-Type: text/html; charset=utf-8\r\n"
        response += f"Content-Length: {len(html)}\r\n"
        response += "\r\n"
        response += html
    
    return response

def start_emergency_server(ip_address=None, port=80):
    """启动紧急模式HTTP服务器"""
    print("\n=== 启动紧急模式HTTP服务器 ===")
    
    # 初始化引脚
    init_emergency_pins()
    
    try:
        # 创建服务器套接字
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('', port))
        server_socket.listen(5)
        
        if ip_address:
            print(f"紧急模式服务器已启动 - http://{ip_address}:{port}/")
        else:
            print(f"紧急模式服务器已启动 - 端口: {port}")
        
        # LED闪烁表示紧急模式
        for _ in range(5):
            if LED_PIN:
                LED_PIN.value(1)
                time.sleep(0.1)
                LED_PIN.value(0)
                time.sleep(0.1)
        
        # 处理请求的主循环
        while True:
            try:
                # 等待客户端连接
                conn, addr = server_socket.accept()
                print(f"紧急模式: 客户端连接 {addr}")
                
                # 接收请求
                request = conn.recv(1024).decode()
                
                # 处理请求
                response = process_emergency_request(request)
                
                # 发送响应
                conn.send(response.encode())
                
                # 关闭连接
                conn.close()
                
            except Exception as e:
                print(f"紧急模式: 处理请求失败 - {e}")
                # 尝试关闭连接
                try:
                    if 'conn' in locals():
                        conn.close()
                except:
                    pass
    
    except Exception as e:
        print(f"紧急模式: 服务器启动失败 - {e}")
        return False
    
    finally:
        # 清理资源
        try:
            server_socket.close()
        except:
            pass

if __name__ == "__main__":
    # 直接运行此文件时启动紧急服务器
    start_emergency_server() 