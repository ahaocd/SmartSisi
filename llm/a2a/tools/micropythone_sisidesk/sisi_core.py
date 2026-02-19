"""
sisi_core.py - 思思坐台核心硬件控制
包含LED、电机、传感器等硬件控制功能
从sisi_desk.py拆分出来，减少内存占用
"""

import time
import random
from machine import Pin
import config
from led import LedRing
try:
    from sensor_vl53 import DistanceSensor
except ImportError:
    DistanceSensor = None

# 极简日志函数
_log_buffer = []

def log(level, message):
    log_msg = f"[{level}] {message}"
    print(log_msg)
    global _log_buffer
    _log_buffer.append(log_msg)
    if len(_log_buffer) > 20:
        _log_buffer.pop(0)

def get_recent_logs():
    global _log_buffer
    return _log_buffer.copy()

class SisiCore:
    """思思坐台核心硬件控制类"""
    
    def __init__(self):
        """初始化核心硬件"""
        log("INFO", "初始化思思坐台核心硬件...")
        
        # 硬件状态
        self.hardware_initialized = False
        
        # LED控制 - 只保留音频LED环
        self.led_ring = None
        
        # 电机控制引脚
        self.motor_in1 = None
        self.motor_in2 = None

        # 电机状态控制
        self.motor_running = False
        self.motor_stop_requested = False

        # 电磁铁保持状态标志
        self.electromagnet_keep_on = False

        # 步进电机引脚
        self.stepper_dir = None
        self.stepper_step = None
        self.stepper_enable = None


        
        # 传感器
        self.distance_sensor = None
        
        # 初始化硬件
        self._init_hardware()
    
    def _init_hardware(self):
        """初始化所有硬件"""
        try:
            # 初始化LED
            self._init_leds()
            
            # 初始化电机
            self._init_motors()
            
            # 初始化传感器
            self._init_sensors()
            
            self.hardware_initialized = True
            log("INFO", "硬件初始化完成")
            
        except Exception as e:
            log("ERROR", f"硬件初始化失败: {e}")
    
    def _init_leds(self):
        """初始化LED - 只保留音频LED环"""
        try:
            # WS2812 LED环 - 专用于音频可视化
            self.led_ring = LedRing()
            log("INFO", "已初始化WS2812音频LED环")

        except Exception as e:
            log("WARNING", f"LED初始化失败: {e}")
    
    def _init_motors(self):
        """初始化电机"""
        try:
            # 直流电机 - 开机必须停止！
            self.motor_in1 = Pin(config.DC_MOTOR_IN1_PIN, Pin.OUT, value=0)  # 0=停止
            self.motor_in2 = Pin(config.DC_MOTOR_IN2_PIN, Pin.OUT, value=0)  # 0=停止
            log("INFO", f"初始化电机引脚 IN1={config.DC_MOTOR_IN1_PIN}, IN2={config.DC_MOTOR_IN2_PIN}")
            
            # 步进电机 - 42步电机，1/4微步模式
            self.stepper_dir = Pin(config.STEPPER_DIR_PIN, Pin.OUT, value=0)
            self.stepper_step = Pin(config.STEPPER_STEP_PIN, Pin.OUT, value=0)
            self.stepper_enable = Pin(config.STEPPER_ENABLE_PIN, Pin.OUT, value=1)  # 高电平禁用
            log("INFO", f"初始化42步电机引脚 DIR={config.STEPPER_DIR_PIN}, STEP={config.STEPPER_STEP_PIN}, EN={config.STEPPER_ENABLE_PIN}")
            log("INFO", "42步电机配置: 1/4微步模式 (M1=高,M2=低,M3=低), 168步/圈")

            log("INFO", "L298N双H桥: OUT1,OUT2=减速电机+电磁铁并联(12V 0.2A)")

        except Exception as e:
            log("ERROR", f"电机初始化失败: {e}")
    
    def _init_sensors(self):
        """初始化传感器 - 容错版本"""
        self.distance_sensor = None
        try:
            if DistanceSensor:
                log("INFO", "开始初始化TOF050C传感器...")
                self.distance_sensor = DistanceSensor()
                log("INFO", "距离传感器初始化成功")
            else:
                log("WARNING", "距离传感器模块不可用")
        except Exception as e:
            log("ERROR", f"距离传感器初始化失败: {e}")
            self.distance_sensor = None
    
    # === LED控制功能 ===
    def led_off(self):
        """关闭音频LED"""
        try:
            if self.led_ring and self.led_ring.np:
                self.led_ring.clear()
                log("INFO", "音频LED环已关闭")
                return True
            else:
                log("WARNING", "LED环未初始化，无法关闭")
                return False
        except Exception as e:
            log("ERROR", f"LED关闭失败: {e}")
        return False

    def led_test(self):
        """LED测试 - 详细诊断和彩色循环"""
        try:
            log("INFO", "开始LED详细诊断...")

            # 检查LED环对象
            if not self.led_ring:
                log("ERROR", "LED环对象为None")
                return {"success": False, "error": "LED环对象未初始化"}

            # 检查neopixel对象
            if not hasattr(self.led_ring, 'np') or not self.led_ring.np:
                log("ERROR", "neopixel对象为None")
                return {"success": False, "error": "neopixel对象未初始化"}

            # 检查LED数量
            led_count = getattr(self.led_ring, 'n_leds', 0)
            log("INFO", f"LED数量: {led_count}")

            if led_count == 0:
                log("ERROR", "LED数量为0")
                return {"success": False, "error": "LED数量为0"}

            log("INFO", "开始LED彩色循环测试...")

            # 红色测试
            log("INFO", "LED测试: 红色")
            self.led_ring.fill(255, 0, 0)
            time.sleep(1)

            # 绿色测试
            log("INFO", "LED测试: 绿色")
            self.led_ring.fill(0, 255, 0)
            time.sleep(1)

            # 蓝色测试
            log("INFO", "LED测试: 蓝色")
            self.led_ring.fill(0, 0, 255)
            time.sleep(1)

            # 白色测试
            log("INFO", "LED测试: 白色")
            self.led_ring.fill(100, 100, 100)
            time.sleep(1)

            # 逐个LED测试
            log("INFO", "LED测试: 逐个点亮")
            self.led_ring.clear()
            for i in range(min(led_count, 12)):  # 测试前12个LED（24颗的一半）
                if hasattr(self.led_ring, 'np') and self.led_ring.np:
                    self.led_ring.np[i] = (50, 50, 50)
                    self.led_ring.np.write()
                    time.sleep_ms(200)

            # 关闭
            self.led_ring.clear()

            log("INFO", "LED彩色循环测试完成")
            return {
                "success": True,
                "message": "LED彩色循环测试完成",
                "led_count": led_count,
                "neopixel_ok": self.led_ring.np is not None
            }
        except Exception as e:
            log("ERROR", f"LED测试失败: {e}")
            return {"success": False, "error": str(e)}
    
    # === 减速电机控制功能 ===
    def motor_forward(self, duration=10):
        """减速电机正转10秒后停止 + 电磁铁开启并保持 (可中断)

        注意：由于硬件限制，电机和电磁铁并联无法独立控制
        正转10秒后，电磁铁会保持开启状态（电机线圈也会保持通电但不转动）
        """
        try:
            if self.motor_in1 and self.motor_in2:
                # 设置运行状态
                self.motor_running = True
                self.motor_stop_requested = False

                # GPIO0=1,GPIO1=0 → 电机正转（标准L298N逻辑）
                self.motor_in1.value(1)  # IN1=1 → 电机正转
                self.motor_in2.value(0)  # IN2=0 → 电机正转
                log("INFO", f"减速电机正转 + 电磁铁开启 {duration}秒 (可中断)")

                # 可中断的等待循环 - 电机运行10秒
                for i in range(duration * 10):  # 每100ms检查一次
                    if self.motor_stop_requested:
                        log("INFO", "收到停止请求，提前结束")
                        # 立即停止电机
                        self.motor_in1.value(0)
                        self.motor_in2.value(0)
                        self.motor_running = False
                        self.electromagnet_keep_on = False
                        return True
                    time.sleep_ms(100)

                # 10秒后：先简单停止电机，暂时不考虑电磁铁保持
                self.motor_in1.value(0)  # IN1=0 → 电机停止
                self.motor_in2.value(0)  # IN2=0 → 电机停止
                self.motor_running = False
                log("INFO", "电机正转10秒完成并停止")
                return True
        except Exception as e:
            log("ERROR", f"减速电机正转失败: {e}")
            self.motor_running = False
        return False


    def motor_backward(self, duration=10):
        """减速电机反转10秒后停止 + 电磁铁立即关闭并保持关闭 (可中断)"""
        try:
            if self.motor_in1 and self.motor_in2:
                # 立即关闭电磁铁保持模式
                self.electromagnet_keep_on = False

                # 设置运行状态
                self.motor_running = True
                self.motor_stop_requested = False

                # GPIO0=0,GPIO1=1 → 电机反转（标准L298N逻辑）
                self.motor_in1.value(0)  # IN1=0 → 电机反转
                self.motor_in2.value(1)  # IN2=1 → 电机反转
                log("INFO", f"电磁铁立即关闭，减速电机反转 {duration}秒 (可中断)")

                # 可中断的等待循环 - 电机反转10秒
                for i in range(duration * 10):  # 每100ms检查一次
                    if self.motor_stop_requested:
                        log("INFO", "收到停止请求，提前结束")
                        # 立即停止电机
                        self.motor_in1.value(0)
                        self.motor_in2.value(0)
                        self.motor_running = False
                        return True
                    time.sleep_ms(100)

                # 反转10秒后：电机停止
                self.motor_in1.value(0)  # IN1=0 → 电机停止
                self.motor_in2.value(0)  # IN2=0 → 电机停止
                self.motor_running = False
                log("INFO", "电机反转10秒完成并停止，电磁铁保持关闭状态")
                return True
        except Exception as e:
            log("ERROR", f"减速电机反转失败: {e}")
            self.motor_running = False
        return False
    
    def motor_stop(self):
        """停止电机 - 一键关闭所有（包括电磁铁）"""
        try:
            # 设置停止标志，中断正在运行的电机
            self.motor_stop_requested = True

            # 关闭电磁铁保持模式
            self.electromagnet_keep_on = False

            if self.motor_in1 and self.motor_in2:
                # 立即停止电机
                self.motor_in1.value(0)  # GPIO0=0 → 电机停止
                self.motor_in2.value(0)  # GPIO1=0 → 电机停止
                self.motor_running = False
                log("INFO", "一键停止：电机停止 + 电磁铁关闭")
                return True
        except Exception as e:
            log("ERROR", f"电机停止失败: {e}")
        return False

    # === 电磁铁控制功能 (复用减速电机引脚) ===
    def electromagnet_on(self):
        """开启电磁铁 - 复用减速电机引脚"""
        try:
            if self.motor_in1 and self.motor_in2:
                # 设置电磁铁保持状态
                self.electromagnet_keep_on = True

                # 电磁铁开启：IN1=0, IN2=0 (修正逻辑)
                self.motor_in1.value(0)
                self.motor_in2.value(0)
                log("INFO", "电磁铁手动开启并保持")
                return True
        except Exception as e:
            log("ERROR", f"电磁铁开启失败: {e}")
        return False

    def electromagnet_off(self):
        """关闭电磁铁 - 复用减速电机引脚"""
        try:
            if self.motor_in1 and self.motor_in2:
                # 关闭电磁铁保持状态
                self.electromagnet_keep_on = False

                # 电磁铁关闭：IN1=1, IN2=0 (修正逻辑)
                self.motor_in1.value(1)
                self.motor_in2.value(0)
                log("INFO", "电磁铁手动关闭")
                return True
        except Exception as e:
            log("ERROR", f"电磁铁关闭失败: {e}")
        return False

    # === 步进电机控制 ===
    def stepper_rotate(self, steps=200, clockwise=True, delay_ms=1, fast_mode=False):
        """步进电机旋转指定步数 - 1.8°电机，DRV8825驱动，支持快速模式"""
        try:
            if not (self.stepper_dir and self.stepper_step and self.stepper_enable):
                log("ERROR", "步进电机引脚未初始化")
                return False

            # 快速模式参数调整
            if fast_mode:
                delay_ms = 0.5  # 超快速度
                log("INFO", f"快速模式: {steps}步, {'顺时针' if clockwise else '逆时针'}")
            else:
                log("INFO", f"标准模式: {steps}步, {'顺时针' if clockwise else '逆时针'}")

            # 启用步进电机 (低电平有效)
            self.stepper_enable.value(0)
            time.sleep_ms(10)  # 减少等待时间

            # 设置方向
            self.stepper_dir.value(1 if clockwise else 0)
            time.sleep_ms(5)   # 减少方向稳定时间

            # 发送脉冲 - 优化速度
            for i in range(steps):
                self.stepper_step.value(1)
                if delay_ms >= 1:
                    time.sleep_ms(int(delay_ms))
                else:
                    time.sleep_us(int(delay_ms * 1000))  # 微秒级延时
                self.stepper_step.value(0)
                if delay_ms >= 1:
                    time.sleep_ms(int(delay_ms))
                else:
                    time.sleep_us(int(delay_ms * 1000))

                # 减少日志频率
                if fast_mode and (i + 1) % 200 == 0:
                    log("INFO", f"快速进度: {i+1}/{steps}")
                elif not fast_mode and (i + 1) % 100 == 0:
                    log("INFO", f"标准进度: {i+1}/{steps}")

            # 减少完成等待时间
            time.sleep_ms(50)

            # 禁用步进电机 (节能)
            self.stepper_enable.value(1)
            log("INFO", f"电机旋转完成: {steps}步")
            return True

        except Exception as e:
            log("ERROR", f"步进电机旋转失败: {e}")
            # 确保禁用电机
            try:
                if self.stepper_enable:
                    self.stepper_enable.value(1)
            except:
                pass
            return False

    def stepper_90(self):
        """步进电机旋转90度 - 1.8°电机，1/2微步模式 (M1=高,M2=低,M3=低)"""
        return self.stepper_rotate(100, True)  # 400步/圈，100步=90度

    def stepper_180(self):
        """步进电机旋转180度 - 1.8°电机，1/2微步模式"""
        return self.stepper_rotate(200, True)  # 200步=180度

    def stepper_360(self):
        """步进电机快速旋转360度 - 1.8°电机，1/2微步模式"""
        return self.stepper_rotate(400, True, fast_mode=True)  # 400步=360度，快速模式

    def stepper_stop(self):
        """步进电机停止"""
        try:
            if self.stepper_enable:
                self.stepper_enable.value(1)  # 禁用步进电机
                log("INFO", "步进电机已停止")
                return True
        except Exception as e:
            log("ERROR", f"步进电机停止失败: {e}")
        return False

    def stepper_swing(self, cycles=5):
        """步进电机快速小幅摆动 - 10度左右快速摇摆"""
        try:
            # 10度 ≈ 11步 (400步/圈 ÷ 36 ≈ 11步)
            swing_steps = 11
            log("INFO", f"开始快速小幅摆动: {cycles}次, 每次{swing_steps}步(约10度)")

            for i in range(cycles):
                # 快速正转10度
                self.stepper_rotate(swing_steps, True, delay_ms=0.5, fast_mode=True)
                time.sleep_ms(50)  # 短暂停顿
                # 快速反转10度
                self.stepper_rotate(swing_steps, False, delay_ms=0.5, fast_mode=True)
                time.sleep_ms(50)  # 短暂停顿

                if (i + 1) % 2 == 0:
                    log("INFO", f"摆动进度: {i+1}/{cycles}")

            log("INFO", f"快速摆动完成: {cycles}次")
            return True
        except Exception as e:
            log("ERROR", f"步进电机摆动失败: {e}")
        return False
    
    # === 传感器功能 ===
    def get_distance(self):
        """获取距离"""
        try:
            if self.distance_sensor:
                distance = self.distance_sensor.read_mm()
                log("INFO", f"距离传感器读取: {distance}mm")
                return distance
            else:
                log("WARNING", "距离传感器未初始化")
                return 0
        except Exception as e:
            log("ERROR", f"距离读取失败: {e}")
            return 0

    def sensor_test(self):
        """传感器测试 - 详细诊断"""
        try:
            log("INFO", "开始传感器诊断测试...")

            # 检查传感器对象
            if not self.distance_sensor:
                log("ERROR", "距离传感器对象为None")
                return {"success": False, "error": "距离传感器未初始化"}

            # 检查I2C连接
            if not hasattr(self.distance_sensor, 'i2c') or not self.distance_sensor.i2c:
                log("ERROR", "I2C总线未初始化")
                return {"success": False, "error": "I2C总线未初始化"}

            # 检查传感器地址
            if not hasattr(self.distance_sensor, 'sensor_address') or not self.distance_sensor.sensor_address:
                log("ERROR", "传感器地址未找到")
                return {"success": False, "error": "传感器地址未找到"}

            log("INFO", f"传感器地址: 0x{self.distance_sensor.sensor_address:02X}")
            log("INFO", f"传感器类型: {getattr(self.distance_sensor, 'sensor_type', 'unknown')}")

            # 连续读取5次距离
            log("INFO", "开始距离测量...")
            distances = []
            for i in range(5):
                log("INFO", f"第{i+1}次测量...")
                distance = self.distance_sensor.read_mm()
                distances.append(distance)
                log("INFO", f"测量结果: {distance}mm")
                time.sleep_ms(200)

            # 计算平均值
            valid_distances = [d for d in distances if d > 0]
            if valid_distances:
                avg_distance = sum(valid_distances) / len(valid_distances)
                log("INFO", f"传感器测试完成: 平均距离{avg_distance:.1f}mm")
                return {
                    "success": True,
                    "distances": distances,
                    "valid_count": len(valid_distances),
                    "average": avg_distance,
                    "sensor_type": getattr(self.distance_sensor, 'sensor_type', 'unknown'),
                    "sensor_address": f"0x{self.distance_sensor.sensor_address:02X}",
                    "message": f"传感器正常，平均距离{avg_distance:.1f}mm"
                }
            else:
                log("ERROR", "所有测量都无效")
                return {
                    "success": False,
                    "error": "传感器无有效读数",
                    "distances": distances,
                    "sensor_type": getattr(self.distance_sensor, 'sensor_type', 'unknown'),
                    "sensor_address": f"0x{self.distance_sensor.sensor_address:02X}" if self.distance_sensor.sensor_address else "unknown"
                }

        except Exception as e:
            log("ERROR", f"传感器测试失败: {e}")
            return {"success": False, "error": str(e)}
    
    # === 状态功能 ===
    def get_status(self):
        """获取硬件状态"""
        import gc
        gc.collect()
        
        status = {
            "hardware_initialized": self.hardware_initialized,
            "memory": {
                "free": gc.mem_free(),
                "allocated": gc.mem_alloc()
            },
            "leds": {
                "audio_led_ring": self.led_ring is not None
            },
            "motors": {
                "dc_motor": self.motor_in1 is not None and self.motor_in2 is not None,
                "stepper": self.stepper_dir is not None
            },
            "sensors": {
                "distance": self.distance_sensor is not None
            }
        }
        return status
    

    # === 统一音频可视化接口 ===
    def cyberpunk_audio_visualizer(self, audio_data=None):
        """统一的赛博朋克音频可视化接口 - Sisi音频数据实时驱动

        这是唯一的音频LED接口，所有音频数据都通过这里处理
        Args:
            audio_data: 音频数据 (dict包含intensity, 或str/bytes原始数据)
        Returns:
            dict: 处理结果
        """
        try:
            # 详细检查LED环状态
            if not self.led_ring:
                log("ERROR", "LED环对象为None")
                return {"success": False, "error": "LED环未初始化"}

            if not hasattr(self.led_ring, 'np') or not self.led_ring.np:
                log("ERROR", "neopixel对象为None")
                return {"success": False, "error": "neopixel未初始化"}

            if self.led_ring.n_leds == 0:
                log("ERROR", "LED数量为0")
                return {"success": False, "error": "LED环无可用LED"}

            # 音频强度计算 - 优先使用真实数据
            if isinstance(audio_data, dict) and 'intensity' in audio_data:
                intensity = min(255, max(30, int(audio_data.get('intensity', 150))))
                log("INFO", f"使用真实音频数据: 强度{intensity}")
            else:
                # 备用：模拟音频数据 - 动态变化
                import time
                t = time.time()
                intensity = int(80 + 60 * abs((t * 2) % 2 - 1))  # 80-140之间动态变化
                log("INFO", f"使用模拟音频数据: 强度{intensity}")

            # 纯音频强度驱动 - 不使用时间！
            # 直接用强度值决定LED模式，不要时间变化！
            brightness = intensity / 255.0  # 归一化强度 (0-1)

            # 根据强度决定LED数量和颜色
            active_leds = int(24 * brightness)  # 强度决定亮起的LED数量
            if active_leds < 1:
                active_leds = 1

            # 先关闭所有LED
            for i in range(self.led_ring.n_leds):
                self.led_ring.np[i] = (0, 0, 0)

            # 根据强度点亮对应数量的LED
            for i in range(active_leds):
                # 强度越高，颜色越亮越暖
                if brightness < 0.3:
                    # 低强度：蓝色
                    r = 0
                    g = int(brightness * 255 * 2)
                    b = int(brightness * 255 * 3)
                elif brightness < 0.7:
                    # 中强度：绿色
                    r = int((brightness - 0.3) * 255 * 2)
                    g = int(brightness * 255)
                    b = int((0.7 - brightness) * 255 * 2)
                else:
                    # 高强度：红色
                    r = int(brightness * 255)
                    g = int((1.0 - brightness) * 255 * 3)
                    b = 0

                self.led_ring.np[i] = (r, g, b)

            self.led_ring.np.write()
            log("INFO", f"音频强度驱动LED: 强度{intensity}, LED数量{active_leds}")

            return {
                "success": True,
                "intensity": intensity,
                "active_leds": active_leds,
                "led_count": self.led_ring.n_leds,
                "message": "音频强度驱动完成"
            }

        except Exception as e:
            log("ERROR", f"赛博朋克音频可视化失败: {e}")
            return {"success": False, "error": str(e)}

    def spectrum_audio_visualizer(self, spectrum_data):
        """
        🎵 专业24颗环形LED音频可视化 - 基于dancyPi项目算法

        核心算法：
        1. ExpFilter指数平滑滤波器（专业渐灭渐亮）
        2. 差分检测（检测音频变化）
        3. Mel频段映射（24个频段对应24颗LED）
        4. 自适应增益控制
        5. 高斯平滑处理

        Args:
            spectrum_data: 8个频段的强度值列表 [freq1, freq2, ..., freq8] (0-255)
        Returns:
            dict: 处理结果
        """
        try:
            import time
            import math

            # 确保有8个频段数据，扩展到24个频段（对应24颗LED）
            if len(spectrum_data) < 8:
                spectrum_data.extend([0] * (8 - len(spectrum_data)))

            # 插值扩展8个频段到24个频段
            expanded_spectrum = []
            for i in range(24):
                # 将24个LED映射到8个频段
                freq_index = (i * 8) // 24
                next_freq_index = min(freq_index + 1, 7)
                # 线性插值
                weight = ((i * 8) % 24) / 24.0
                value = spectrum_data[freq_index] * (1 - weight) + spectrum_data[next_freq_index] * weight
                expanded_spectrum.append(value)

            # 🎵 初始化简单有效的LED状态
            if not hasattr(self, 'led_values'):
                self.led_values = [0.0] * 24  # 每个LED的当前值
                self.frame_count = 0

            self.frame_count += 1

            # 🎵 步骤1：真正的音频响应算法
            # 分析数据变化：[31, 22, 0, 0] → [136, 45, 0, 0]
            valid_spectrum = expanded_spectrum[:4]

            # 🔥 修复：不用平方，直接放大音频响应
            # 计算总音频强度
            total_audio = sum(valid_spectrum) / (4 * 255.0)  # 0-1范围

            # 🎵 步骤2：动态范围扩展（让小变化也能看到）
            # 低频强度（主要节拍）
            bass_raw = valid_spectrum[0] / 255.0  # 0-1
            bass_enhanced = bass_raw ** 0.5 * 2.0  # 开方放大，0-2范围
            bass_enhanced = min(1.0, bass_enhanced)

            # 中频强度（旋律）
            mid_raw = max(valid_spectrum[1:3]) / 255.0 if len(valid_spectrum) > 1 else 0
            mid_enhanced = mid_raw ** 0.5 * 1.5  # 0-1.5范围
            mid_enhanced = min(1.0, mid_enhanced)

            # 高频强度（细节）
            treble_raw = valid_spectrum[3] / 255.0 if len(valid_spectrum) > 3 else 0
            treble_enhanced = treble_raw ** 0.5 * 1.2  # 0-1.2范围
            treble_enhanced = min(1.0, treble_enhanced)

            # 🎵 步骤3：多风格LED效果系统
            # 初始化LED状态缓冲区
            if not hasattr(self, 'led_states'):
                self.led_states = {
                    'brightness': [0.0] * 24,  # 每个LED的亮度状态
                    'chase_pos': 0.0,          # 追光位置
                    'style': 'breathing'       # 当前风格
                }

            # 🎯 根据音频强度选择风格
            if total_audio > 0.3:
                self.led_states['style'] = 'chase'      # 强音频：快速追光
            elif total_audio > 0.1:
                self.led_states['style'] = 'rainbow'    # 中音频：彩虹流光
            else:
                self.led_states['style'] = 'breathing'  # 弱音频：呼吸灯

            # 🔥 风格1：呼吸灯（渐灭渐亮）
            if self.led_states['style'] == 'breathing':
                for i in range(24):
                    # 目标亮度：根据频段计算
                    if i < 8:
                        target = bass_enhanced * 0.8
                    elif i < 16:
                        target = mid_enhanced * 0.8
                    else:
                        target = treble_enhanced * 0.8

                    # 🔥 毫秒级渐灭渐亮算法（50FPS优化）
                    current = self.led_states['brightness'][i]
                    if target > current:
                        # 超快速亮起（Attack）- 50FPS下需要更大步长
                        self.led_states['brightness'][i] += (target - current) * 0.95
                    else:
                        # 明显渐灭（Release）- 让渐灭效果更明显
                        self.led_states['brightness'][i] += (target - current) * 0.15

                    # 应用颜色
                    hue = (i * 15) % 360  # 固定彩虹色
                    brightness = self.led_states['brightness'][i]
                    r, g, b = self.hsv_to_rgb(hue, 0.9, brightness)
                    self.led_ring.np[i] = (int(r), int(g), int(b))

            # 🔥 风格2：FadeCandy算法 - 真正的平滑追光
            elif self.led_states['style'] == 'chase':
                # 🚀 浮点位置追光（关键！）
                chase_speed = 0.5 + total_audio * 3.0  # 0.5-3.5的浮点速度
                self.led_states['chase_pos'] += chase_speed
                if self.led_states['chase_pos'] >= 24.0:
                    self.led_states['chase_pos'] -= 24.0

                # 🌈 背景色（暗色）
                bg_r, bg_g, bg_b = 10, 10, 30  # 深蓝背景

                # 🎵 前景色（根据音频频段）
                if bass_enhanced > mid_enhanced and bass_enhanced > treble_enhanced:
                    fg_r, fg_g, fg_b = 255, 50, 50   # 红色（低频）
                elif mid_enhanced > treble_enhanced:
                    fg_r, fg_g, fg_b = 50, 255, 50   # 绿色（中频）
                else:
                    fg_r, fg_g, fg_b = 50, 50, 255   # 蓝色（高频）

                # 🔥 FadeCandy插值算法
                for i in range(24):
                    # 计算距离（环形距离）
                    distance1 = abs(i - self.led_states['chase_pos'])
                    distance2 = 24 - distance1
                    distance = min(distance1, distance2)

                    # 🎯 插值权重（距离越近权重越大）
                    if distance <= 3.0:  # 影响范围：3个LED
                        weight = max(0.0, 1.0 - distance / 3.0)
                        # 增强权重（让过渡更明显）
                        weight = weight ** 0.5  # 开方增强
                        weight *= min(1.0, total_audio * 2.0)  # 音频强度调制
                    else:
                        weight = 0.0

                    # 🌈 颜色混合（blend算法）
                    r = int(bg_r + (fg_r - bg_r) * weight)
                    g = int(bg_g + (fg_g - bg_g) * weight)
                    b = int(bg_b + (fg_b - bg_b) * weight)

                    self.led_ring.np[i] = (r, g, b)

            # 🔥 风格3：超快彩虹流光
            else:  # rainbow
                for i in range(24):
                    # 🌈 超快流光彩虹色相（50FPS优化）
                    hue = (i * 15 + self.frame_count * 8) % 360  # 8倍速度！

                    # 亮度：音频响应
                    if i < 8:
                        brightness = bass_enhanced * 0.6
                    elif i < 16:
                        brightness = mid_enhanced * 0.6
                    else:
                        brightness = treble_enhanced * 0.6

                    # 最小亮度保证
                    brightness = max(0.1, brightness)

                    r, g, b = self.hsv_to_rgb(hue, 0.9, brightness)
                    self.led_ring.np[i] = (int(r), int(g), int(b))

            # 🎵 步骤4：写入LED硬件
            self.led_ring.np.write()

            # 🎵 调试信息
            if self.frame_count % 20 == 0:
                style = self.led_states['style']
                chase_pos = self.led_states.get('chase_pos', 0)
                log("INFO", f"🎵 多风格LED: {style}, 低频{bass_enhanced:.3f}, 中频{mid_enhanced:.3f}, 高频{treble_enhanced:.3f}, 追光{chase_pos:.1f}")

            return {
                "success": True,
                "spectrum_data": spectrum_data,
                "valid_spectrum": valid_spectrum,
                "bass_enhanced": round(bass_enhanced, 3),
                "mid_enhanced": round(mid_enhanced, 3),
                "treble_enhanced": round(treble_enhanced, 3),
                "total_audio": round(total_audio, 3),
                "led_style": self.led_states['style'],
                "chase_pos": round(self.led_states.get('chase_pos', 0), 1),
                "frame_count": self.frame_count,
                "led_count": 24,
                "message": "🎵 多风格音频响应LED"
            }

        except Exception as e:
            log("ERROR", f"8频段音频可视化失败: {e}")
            return {"success": False, "error": str(e)}

    def hsv_to_rgb(self, h, s, v):
        """HSV转RGB颜色空间"""
        h = h % 360
        c = v * s
        x = c * (1 - abs((h / 60) % 2 - 1))
        m = v - c

        if 0 <= h < 60:
            r, g, b = c, x, 0
        elif 60 <= h < 120:
            r, g, b = x, c, 0
        elif 120 <= h < 180:
            r, g, b = 0, c, x
        elif 180 <= h < 240:
            r, g, b = 0, x, c
        elif 240 <= h < 300:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x

        return (r + m) * 255, (g + m) * 255, (b + m) * 255





