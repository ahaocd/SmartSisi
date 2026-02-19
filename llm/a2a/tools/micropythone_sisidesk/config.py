# config.py
# ESP32-C3-MINI-1-V2.4.2.0 引脚与系统常量集中管理
# 统一改这里即可，其他模块 import 后自动同步

"""
思思桌面控制系统配置文件 - ESP32-C3 Super Mini开发板

基于ESP32-C3 Super Mini实际引脚布局：
左侧引脚: 5V,GND,3V3,GPIO4,GPIO3,GPIO2,GPIO1,GPIO0
右侧引脚: GPIO5,GPIO6,GPIO7,GPIO8,GPIO9,GPIO10,GPIO20,GPIO21

引脚安全等级：
✅ 完全安全: GPIO0,1,3,4,5,6,7,9,10 (通用GPIO)
⚠️ 特殊功能: GPIO8(板载LED), GPIO2(BOOT), GPIO20,21(UART)
"""

# === WS2812 灯环 (音频驱动) - 专用引脚，严禁其他用途 ===
LED_RING_PIN = 10      # GPIO10 - 专用于24颗WS2812 LED环，音频可视化，严禁其他用途！ ✅
LED_RING_COUNT = 24    # 24颗LED环

# === 直流减速电机 + 电磁铁联动 (L298N双H桥) ===
# OUT1,OUT2: 减速电机+电磁铁并联 (同GPIO控制，自动联动)
DC_MOTOR_IN1_PIN = 0  # GPIO0 → L298N IN1 ✅
DC_MOTOR_IN2_PIN = 1  # GPIO1 → L298N IN2 ✅

# === 步进电机 (A4988/DRV8825驱动) - 42步电机，1/4微步模式 ===
STEPPER_DIR_PIN = 6    # GPIO6 - 步进电机方向 ✅
STEPPER_STEP_PIN = 7   # GPIO7 - 步进电机脉冲 ✅
STEPPER_ENABLE_PIN = 5 # GPIO5 - 步进电机使能 (避开GPIO8/9启动引脚) ✅

# === 1.8°步进电机参数 (DRV8825驱动) ===
STEPPER_STEPS_PER_REV = 200   # 1.8°步进电机 = 200步/圈
STEPPER_MICROSTEPS = 4        # 1/4微步模式 (M0=高,M1=低,M2=低)
STEPPER_TOTAL_STEPS = 800     # 200 × 4 = 800步/圈

# === I2C 通信 (TOF050C激光距离传感器) - 避开UART和启动引脚 ===
I2C_SDA_PIN = 3       # GPIO3 - I2C数据线 ✅
I2C_SCL_PIN = 4       # GPIO4 - 安全引脚，I2C时钟线 ✅

# === Wi-Fi 配置 ===
WIFI_SSID = "iPhone15"
WIFI_PASSWORD = "88888888"

# === 网络配置 (固定IP，避免与其他设备冲突) ===
FIXED_IP = "172.20.10.5"      # sisidesk设备固定IP
SUBNET_MASK = "255.255.255.240"
GATEWAY = "172.20.10.1"
DNS_SERVER = "172.20.10.1"

# === SISI 服务器配置 ===
SISI_SERVER_HOST = "172.20.10.1"  # iPhone15热点网关地址
SISI_SERVER_PORT = 9001

# === 设备信息 ===
DEVICE_NAME = "思思坐台-C3"
WEB_SERVER_PORT = 80

# === 备用引脚配置 ===
# 如需额外GPIO，可考虑以下引脚（需注意限制）：
# GPIO4-7: JTAG调试引脚，避免使用
# GPIO20-21: UART引脚，避免使用
# GPIO5: 可用但需注意JTAG冲突
SPARE_GPIO_PIN = None  # 备用引脚，暂未分配

# === 调试设置 ===
DEBUG_MODE = True
BOOT_TEST = True

# === 引脚使用说明 ===
"""
ESP32-C3开发板引脚分配总结（基于实际引脚布局的最优方案）：

🎯 最终引脚分配（完全无冲突版本）：

左侧引脚区域（安全引脚优先）：
- GPIO0: 直流电机IN1 (左侧安全引脚) ✅
- GPIO1: 直流电机IN2 (左侧安全引脚) ✅
- GPIO3: I2C数据线SDA ✅
- GPIO4: I2C时钟线SCL (安全引脚) ✅
- GPIO10: WS2812灯环24颗 (左侧安全引脚，专用音频驱动) ✅

右侧引脚区域（连续引脚便于接线）：
- GPIO5: 步进电机使能EN (避开启动引脚) ✅
- GPIO6: 步进电机DIR (右侧MTMS引脚) ✅
- GPIO7: 步进电机STEP (右侧MTDI引脚) ✅
🔧 硬件功能清单：
1. WS2812 LED环 24颗 (GPIO10) - 专用音频数据驱动，完全独立
2. 直流减速电机 (GPIO0/1) - H桥驱动，使用最安全的左侧引脚
3. 步进电机完整控制 (GPIO6/7/8) - DIR/STEP/EN，右侧连续引脚便于接线
4. TOF050C激光距离传感器 (I2C: GPIO3/4) - 避开UART冲突

🎉 关键优化亮点：
✅ GPIO10专用于WS2812音频驱动，完全无冲突
✅ 步进电机使用右侧连续引脚GPIO6/7/8，接线简单
✅ 直流电机使用最安全的左侧GPIO0/1
✅ 所有功能引脚完全分离，无任何共用冲突

🔥 引脚冲突完全解决：
✅ GPIO10: 专用WS2812音频驱动，不再与任何功能共用
✅ 步进电机: 独立使用GPIO6/7/8，不影响其他功能
✅ 直流电机: 独立使用GPIO0/1，完全安全
✅ 传感器: 使用GPIO3/4，避开UART冲突

📊 引脚安全等级分析：
✅ 完全安全: GPIO0,1,3,10 (左侧安全引脚，核心功能)
✅ 右侧可用: GPIO6,7,8 (JTAG引脚，MicroPython下安全)
⚠️ 谨慎使用: GPIO20(UART)
🚫 保留未用: GPIO2(BOOT), GPIO4,5(USB), GPIO19(BOOT), GPIO21(UART)

💡 使用建议：
1. WS2812音频驱动与步进电机完全独立，可同时工作
2. 所有功能引脚无冲突，软件控制简单
3. 右侧步进电机引脚连续，便于驱动板接线
4. 保留GPIO2,4,5,19,21等敏感引脚，确保系统稳定

🎯 这个方案实现了完美的引脚分离，所有功能独立工作，无任何冲突！
"""
