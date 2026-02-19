"""
sisi_web.py - 思思坐台Web服务器和API处理
包含HTTP服务器、API路由、请求处理等功能
从sisi_desk.py拆分出来，减少内存占用
"""

import time
import json
import socket
import network
from sisi_core import SisiCore, log, get_recent_logs

class SisiWebServer:
    """思思坐台Web服务器类"""
    
    def __init__(self):
        """初始化Web服务器"""
        log("INFO", "初始化思思坐台Web服务器...")
        
        # 核心硬件控制
        self.core = SisiCore()
        
        # 网络相关
        self.ip_address = None
        self.server_socket = None
        self.running = False
        
        # 获取IP地址
        self._get_ip_address()
    
    def _get_ip_address(self):
        """获取IP地址"""
        try:
            wlan = network.WLAN(network.STA_IF)
            if wlan.isconnected():
                self.ip_address = wlan.ifconfig()[0]
                log("INFO", f"WiFi已连接，IP: {self.ip_address}")
            else:
                log("WARNING", "WiFi未连接")
        except Exception as e:
            log("ERROR", f"获取IP地址失败: {e}")
    
    def start_web_server(self, port=80):
        """启动Web服务器"""
        try:
            if not self.ip_address:
                log("ERROR", "无IP地址，无法启动Web服务器")
                return False
            
            # 创建socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', port))
            self.server_socket.listen(1)
            self.server_socket.settimeout(1.0)
            
            log("INFO", f"Web服务器已启动 - http://{self.ip_address}:{port}/")
            return True
            
        except Exception as e:
            log("ERROR", f"启动Web服务器失败: {e}")
            return False
    
    def run_web_server(self):
        """运行Web服务器主循环"""
        if not self.server_socket:
            log("ERROR", "Web服务器未启动")
            return
        
        self.running = True
        log("INFO", "开始处理Web请求...")
        
        while self.running:
            try:
                # 等待客户端连接
                conn, addr = self.server_socket.accept()
                conn.settimeout(3.0)
                log("INFO", f"客户端连接: {addr}")
                
                # 处理请求
                self._handle_request(conn)
                
            except OSError:
                # 超时，继续循环
                continue
            except Exception as e:
                log("ERROR", f"请求处理异常: {e}")
                continue
    
    def _handle_request(self, conn):
        """处理HTTP请求"""
        try:
            # 接收请求
            request = conn.recv(1024).decode('utf-8')
            if not request:
                conn.close()
                return
            
            # 解析请求
            lines = request.split('\n')
            if not lines:
                conn.close()
                return
            
            request_line = lines[0]
            parts = request_line.split(' ')
            if len(parts) < 2:
                conn.close()
                return
            
            method = parts[0]
            path = parts[1]
            
            log("INFO", f"请求: {method} {path}")
            
            # 路由处理
            response = self._route_request(path)
            
            # 发送响应
            self._send_response(conn, response)
            
        except Exception as e:
            log("ERROR", f"请求处理失败: {e}")
            try:
                conn.close()
            except:
                pass
    
    def _route_request(self, path):
        """路由处理"""
        try:
            # API路由
            if path.startswith('/api/'):
                return self._handle_api(path)
            
            # 默认返回主页
            else:
                return self._get_main_page()
                
        except Exception as e:
            log("ERROR", f"路由处理失败: {e}")
            return {
                'type': 'json',
                'content': json.dumps({
                    'status': 'error',
                    'error': str(e)
                })
            }
    
    def _handle_api(self, path):
        """处理API请求"""
        try:
            # LED控制 - 只保留关闭和音频特效
            if path == '/api/led/off':
                success = self.core.led_off()
                return self._json_response(success, "音频LED关闭" if success else "LED关闭失败")

            # 赛博朋克音频LED效果 - 唯一的音频接口
            elif path == '/api/led/audio':
                result = self.core.cyberpunk_audio_visualizer(audio_data={'intensity': 180})
                return {
                    'type': 'json',
                    'content': json.dumps(result)
                }

            # LED测试接口
            elif path == '/api/led/test':
                result = self.core.led_test()
                return {
                    'type': 'json',
                    'content': json.dumps(result)
                }

            # 传感器控制
            elif path == '/api/sensor/distance':
                distance = self.core.get_distance()
                return self._json_response(True, f"距离: {distance}mm", {"distance": distance})

            elif path == '/api/sensor/test':
                result = self.core.sensor_test()
                return {
                    'type': 'json',
                    'content': json.dumps(result)
                }
            
            # 电机控制
            elif path == '/api/motor/forward':
                success = self.core.motor_forward(10)  # 正转10秒
                return self._json_response(success, "电机正转10秒" if success else "电机正转失败")

            elif path == '/api/motor/backward':
                success = self.core.motor_backward(10)  # 反转10秒
                return self._json_response(success, "电机反转10秒" if success else "电机反转失败")
            
            elif path == '/api/motor/stop':
                success = self.core.motor_stop()
                return self._json_response(success, "电机停止" if success else "电机停止失败")

            # 电磁铁控制 (复用电机引脚)
            elif path == '/api/electromagnet/on':
                success = self.core.electromagnet_on()
                return self._json_response(success, "电磁铁开启" if success else "电磁铁开启失败")

            elif path == '/api/electromagnet/off':
                success = self.core.electromagnet_off()
                return self._json_response(success, "电磁铁关闭" if success else "电磁铁关闭失败")

            # 步进电机控制
            elif path == '/api/stepper/90':
                success = self.core.stepper_90()
                return self._json_response(success, "步进电机90度" if success else "步进电机失败")

            elif path == '/api/stepper/180':
                success = self.core.stepper_180()
                return self._json_response(success, "步进电机180度" if success else "步进电机失败")

            elif path == '/api/stepper/360':
                success = self.core.stepper_360()
                return self._json_response(success, "步进电机360度" if success else "步进电机失败")

            elif path == '/api/stepper/stop':
                success = self.core.stepper_stop()
                return self._json_response(success, "步进电机停止" if success else "步进电机失败")

            elif path == '/api/stepper/swing':
                success = self.core.stepper_swing()
                return self._json_response(success, "步进电机摆动" if success else "步进电机失败")
            
            # 状态查询
            elif path == '/api/status':
                status = self.core.get_status()
                return {
                    'type': 'json',
                    'content': json.dumps({
                        'status': 'success',
                        'data': {
                            'wifi': {'ip': self.ip_address},
                            'memory': f"{status['memory']['free']//1024}KB",
                            'hardware': status['hardware_initialized']
                        }
                    })
                }
            
            # 距离传感器
            elif path == '/api/distance':
                distance = self.core.get_distance()
                return self._json_response(distance is not None, f"距离: {distance}mm" if distance else "传感器读取失败")
            
            # 日志
            elif path == '/api/logs':
                logs = get_recent_logs()
                return {
                    'type': 'json',
                    'content': json.dumps({
                        'status': 'success',
                        'data': {'logs': logs}
                    })
                }
            
            # 测试
            elif path == '/api/test':
                return self._json_response(True, "系统测试正常")
            
            # 音频可视化 - 赛博朋克旋律化 (支持真实音频数据)
            elif path.startswith('/api/audio/cyberpunk'):
                # 从URL参数获取音频强度
                intensity = 180  # 默认强度
                if '?' in path:
                    params = path.split('?')[1]
                    for param in params.split('&'):
                        if param.startswith('intensity='):
                            try:
                                intensity = int(param.split('=')[1])
                                intensity = max(30, min(255, intensity))  # 限制范围
                            except:
                                pass

                result = self.core.cyberpunk_audio_visualizer(audio_data={'intensity': intensity})
                return {
                    'type': 'json',
                    'content': json.dumps(result)
                }

            # 新增：8频段音频频谱可视化 - 流光溢彩效果
            elif path.startswith('/api/audio/spectrum'):
                # 从URL参数获取8频段数据
                spectrum_data = [128] * 8  # 默认值
                if '?' in path:
                    params = path.split('?')[1]
                    for param in params.split('&'):
                        if param.startswith('data='):
                            try:
                                data_str = param.split('=')[1]
                                spectrum_values = [int(x) for x in data_str.split(',')]
                                if len(spectrum_values) >= 8:
                                    spectrum_data = spectrum_values[:8]
                            except:
                                pass

                result = self.core.spectrum_audio_visualizer(spectrum_data)
                return {
                    'type': 'json',
                    'content': json.dumps(result)
                }

            elif path == '/api/audio/beat':
                # 从URL参数获取强度
                intensity = 128  # 默认强度
                if '?' in path:
                    params = path.split('?')[1]
                    for param in params.split('&'):
                        if param.startswith('intensity='):
                            try:
                                intensity = int(param.split('=')[1])
                            except:
                                pass

                result = self.core.audio_beat_drive(intensity)
                return {
                    'type': 'json',
                    'content': json.dumps(result)
                }

            elif path.startswith('/api/audio/realtime'):
                # 实时音频数据处理 - 唯一的音频接口
                audio_data = {'intensity': 150}  # 示例数据，实际从POST获取
                result = self.core.process_realtime_audio(audio_data)
                return {
                    'type': 'json',
                    'content': json.dumps(result)
                }
            
            else:
                return self._json_response(False, "未知API")
                
        except Exception as e:
            log("ERROR", f"API处理失败: {e}")
            return self._json_response(False, f"API错误: {e}")
    
    def _json_response(self, success, message):
        """生成JSON响应"""
        return {
            'type': 'json',
            'content': json.dumps({
                'status': 'success' if success else 'error',
                'message': message
            })
        }
    
    def _get_main_page(self):
        """获取主页HTML"""
        try:
            from lite_ui import get_lite_html
            html = get_lite_html()
            return {
                'type': 'html',
                'content': html
            }
        except Exception as e:
            log("ERROR", f"获取主页失败: {e}")
            return {
                'type': 'html',
                'content': '<html><body><h1>思思桌面</h1><p>系统错误</p></body></html>'
            }
    
    def _send_response(self, conn, response):
        """发送HTTP响应"""
        try:
            if response['type'] == 'json':
                conn.send(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n')
                conn.send(response['content'].encode('utf-8'))
            else:
                conn.send(b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n')
                conn.send(response['content'].encode('utf-8'))
            
            conn.close()
            
        except Exception as e:
            log("ERROR", f"发送响应失败: {e}")
            try:
                conn.close()
            except:
                pass
    
    def stop(self):
        """停止Web服务器"""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
                log("INFO", "Web服务器已停止")
            except:
                pass

# 主程序入口
def main():
    """主程序入口"""
    log("INFO", "启动思思坐台Web服务器...")
    
    server = SisiWebServer()
    
    if server.start_web_server():
        try:
            server.run_web_server()
        except KeyboardInterrupt:
            log("INFO", "用户中断")
        except Exception as e:
            log("ERROR", f"服务器运行异常: {e}")
        finally:
            server.stop()
    else:
        log("ERROR", "Web服务器启动失败")

if __name__ == "__main__":
    main()
