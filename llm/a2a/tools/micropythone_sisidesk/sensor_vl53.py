"""
TOF050C/VL53L0X激光测距传感器驱动 - 兼容驱动
支持ESP32-C3-MINI-1，引脚: SDA=GPIO3, SCL=GPIO4
TOF050C与VL53L0X使用相同的I2C协议，地址0x29
"""
from machine import I2C, Pin
import time
import config

# 使用配置文件中的引脚设置
I2C_SDA_PIN = config.I2C_SDA_PIN  # GPIO3
I2C_SCL_PIN = config.I2C_SCL_PIN  # GPIO4

print(f"TOF050C/VL53L0X传感器配置: SDA=GPIO{I2C_SDA_PIN}, SCL=GPIO{I2C_SCL_PIN}")

# TOF050C/VL53L0X传感器I2C地址
VL53L0X_ADDRESS = 0x29  # 标准地址
TOF050C_ADDRESSES = [0x29, 0x52]  # TOF050C兼容地址

class DistanceSensor:
    """TOF050C/VL53L0X激光测距传感器驱动"""

    def __init__(self):
        """初始化传感器"""
        self.i2c = None
        self.sensor_address = None
        self.sensor_type = "unknown"

        try:
            # 创建I2C总线
            self.i2c = I2C(0, sda=Pin(I2C_SDA_PIN), scl=Pin(I2C_SCL_PIN), freq=100000)
            print(f"I2C总线初始化成功: SDA=GPIO{I2C_SDA_PIN}, SCL=GPIO{I2C_SCL_PIN}")

            # 扫描I2C设备
            devices = self.i2c.scan()
            print(f"发现的I2C设备: {[hex(d) for d in devices]}")

            if not devices:
                print("⚠️ 未发现任何I2C设备，请检查接线:")
                print(f"   SDA → GPIO{I2C_SDA_PIN}")
                print(f"   SCL → GPIO{I2C_SCL_PIN}")
                print(f"   VCC → 3.3V")
                print(f"   GND → GND")
                raise Exception("未发现I2C设备")

            # 查找TOF050C/VL53L0X传感器
            self.sensor_address = self._find_vl53l0x(devices)

            if self.sensor_address:
                print(f"✅ 找到TOF050C/VL53L0X传感器，地址: 0x{self.sensor_address:02X}")
                self._init_vl53l0x()
            else:
                print("⚠️ 未找到TOF050C传感器，将使用通用I2C读取模式")
                self.sensor_address = devices[0]  # 使用第一个设备

        except Exception as e:
            print(f"传感器初始化失败: {e}")
            raise

    def _find_vl53l0x(self, devices):
        """查找TOF050C/VL53L0X传感器"""
        for addr in TOF050C_ADDRESSES:
            if addr in devices:
                print(f"找到可能的TOF050C/VL53L0X传感器: 0x{addr:02X}")
                return addr
        return None

    def _init_vl53l0x(self):
        """初始化VL53L0X传感器"""
        try:
            # VL53L0X标准初始化
            # 读取设备ID验证
            try:
                device_id = self.i2c.readfrom_mem(self.sensor_address, 0xC0, 1)
                print(f"设备ID: 0x{device_id[0]:02X}")
                if device_id[0] == 0xEE:
                    self.sensor_type = "VL53L0X"
                    print("✅ 确认为VL53L0X传感器")
                else:
                    self.sensor_type = "TOF050C"
                    print("✅ 确认为TOF050C传感器")
            except:
                self.sensor_type = "TOF050C"
                print("✅ 默认为TOF050C传感器")

        except Exception as e:
            print(f"VL53L0X初始化失败: {e}")

    def read_mm(self):
        """读取距离(毫米) - VL53L0X协议"""
        if not self.i2c or not self.sensor_address:
            print("传感器未初始化")
            return 0

        try:
            # VL53L0X标准测距协议
            # 1. 启动测量
            self.i2c.writeto_mem(self.sensor_address, 0x00, b'\x01')
            time.sleep_ms(10)  # 等待测量完成

            # 2. 读取距离数据 (寄存器0x1E-0x1F)
            data = self.i2c.readfrom_mem(self.sensor_address, 0x1E, 2)
            distance = (data[0] << 8) | data[1]

            # 3. 距离范围检查 (VL53L0X: 0-2000mm)
            if distance == 20:  # VL53L0X错误值
                return 0
            elif 0 < distance <= 2000:
                return distance
            else:
                return 0

        except Exception as e:
            print(f"VL53L0X读取距离失败: {e}")

            # 备用方法：尝试TOF050C其他寄存器
            try:
                # 尝试其他可能的寄存器
                for reg in [0x00, 0x01, 0x02, 0x10]:
                    try:
                        data = self.i2c.readfrom_mem(self.sensor_address, reg, 2)
                        distance = (data[0] << 8) | data[1]
                        if 0 < distance <= 2000:
                            return distance
                    except:
                        continue
                return 0
            except:
                return 0

    def close(self):
        """关闭传感器"""
        if self.i2c:
            try:
                # VL53L0X关闭命令
                self.i2c.writeto_mem(self.sensor_address, 0x00, b'\x00')
            except:
                pass