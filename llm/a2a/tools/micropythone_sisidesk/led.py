"""
led.py - 极简LED控制
只保留GPIO10的24颗WS2812 LED环，专用于音频可视化
"""
from machine import Pin
import time
import config

try:
    import neopixel
    _HAS_NEOPIXEL = True
    print("neopixel模块加载成功")
except ImportError:
    _HAS_NEOPIXEL = False
    print("警告: neopixel模块不可用")
except Exception as e:
    _HAS_NEOPIXEL = False
    print(f"警告: neopixel模块加载失败 ({e})")

class LedRing:
    """WS2812 LED环 - 专用于音频可视化"""

    def __init__(self, num_leds=config.LED_RING_COUNT, pin=config.LED_RING_PIN):
        """初始化WS2812 LED环 - 安全版本"""
        if not _HAS_NEOPIXEL:
            print("⚠️ neopixel模块不可用，LED环功能禁用")
            self.n_leds = 0
            self.np = None
            return

        try:
            self.n_leds = num_leds

            # GPIO10特殊处理 - 延迟初始化避免硬件冲突
            if pin == 10:
                print(f"🔧 GPIO10特殊初始化: 延迟500ms避免硬件冲突...")
                time.sleep(0.5)

                # 分步初始化GPIO10
                led_pin = Pin(pin, Pin.OUT, value=0)
                time.sleep(0.1)

                # 低频率初始化neopixel
                self.np = neopixel.NeoPixel(led_pin, num_leds, timing=1)
                time.sleep(0.1)
            else:
                # 普通GPIO初始化
                led_pin = Pin(pin, Pin.OUT)
                self.np = neopixel.NeoPixel(led_pin, num_leds)

            self.clear()
            print(f"✅ WS2812初始化成功: GPIO{pin}, {num_leds}颗LED")

        except Exception as e:
            print(f"❌ WS2812初始化失败: {e}")
            print(f"🔧 尝试GPIO10降级模式...")

            # GPIO10降级模式 - 简单LED控制
            try:
                if pin == 10:
                    self.fallback_pin = Pin(pin, Pin.OUT, value=0)
                    self.n_leds = 1  # 降级为单LED模式
                    self.np = None
                    print(f"⚠️ GPIO10降级为单LED模式")
                else:
                    self.n_leds = 0
                    self.np = None
            except:
                self.n_leds = 0
                self.np = None

    def clear(self):
        """清除所有LED - 安全版本"""
        if not self.np or self.n_leds == 0:
            return
        try:
            for i in range(self.n_leds):
                self.np[i] = (0, 0, 0)
            self.np.write()
        except:
            pass

    def fill(self, r, g, b):
        """填充所有LED为指定颜色 - 安全版本"""
        if not self.np or self.n_leds == 0:
            return
        try:
            for i in range(self.n_leds):
                self.np[i] = (r, g, b)
            self.np.write()
        except:
            pass

    def rainbow(self, wait=0.05):
        """彩虹效果"""
        for j in range(256):
            for i in range(self.n_leds):
                idx = (i * 256 // self.n_leds + j) & 255
                self.np[i] = self._wheel(idx)
            self.np.write()
            time.sleep(wait)

    @staticmethod
    def _wheel(pos):
        """颜色循环算法"""
        if pos < 85:
            return pos * 3, 255 - pos * 3, 0
        elif pos < 170:
            pos -= 85
            return 255 - pos * 3, 0, pos * 3
        else:
            pos -= 170
            return 0, pos * 3, 255 - pos * 3


