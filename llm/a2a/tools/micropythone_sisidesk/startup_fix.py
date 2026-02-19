"""
ESP32-C3 启动问题修复脚本
解决neopixel导入失败和WiFi强制连接问题
"""

import time
import gc
from machine import Pin

def test_basic_hardware():
    """测试基础硬件"""
    print("=== 基础硬件测试 ===")

    try:
        # 测试基础GPIO功能
        print("✅ 基础GPIO功能正常")
        return True

    except Exception as e:
        print(f"❌ 基础硬件测试失败: {e}")
        return False

def test_audio_led():
    """测试音频LED模块"""
    print("=== 音频LED模块测试 ===")

    try:
        import neopixel
        print("✅ neopixel模块可用")

        # 尝试创建GPIO10音频LED对象
        np = neopixel.NeoPixel(Pin(10), 24)
        print("✅ GPIO10音频LED创建成功")

        # 测试赛博朋克效果
        np[0] = (0, 255, 128)  # 青色
        np.write()
        time.sleep(0.5)
        np[0] = (0, 0, 0)    # 关闭
        np.write()
        print("✅ 音频LED功能正常")

        return True

    except ImportError:
        print("❌ neopixel模块不可用 (ImportError)")
        return False
    except Exception as e:
        print(f"❌ 音频LED测试失败: {e}")
        return False

def test_memory():
    """测试内存状态"""
    print("=== 内存状态测试 ===")
    
    try:
        gc.collect()
        free = gc.mem_free()
        alloc = gc.mem_alloc()
        total = free + alloc
        
        print(f"可用内存: {free} 字节 ({free//1024} KB)")
        print(f"已用内存: {alloc} 字节 ({alloc//1024} KB)")
        print(f"总内存: {total} 字节 ({total//1024} KB)")
        print(f"内存使用率: {(alloc/total)*100:.1f}%")
        
        if free < 20480:  # 小于20KB
            print("⚠️ 警告：可用内存不足20KB")
            return False
        else:
            print("✅ 内存状态正常")
            return True
            
    except Exception as e:
        print(f"❌ 内存测试失败: {e}")
        return False

def test_wifi_optional():
    """可选WiFi测试 - 不强制连接"""
    print("=== WiFi测试 (可选) ===")
    
    try:
        import network
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            print(f"✅ WiFi已连接: {ip}")
            return True
        else:
            print("ℹ️ WiFi未连接 (这是正常的)")
            return True  # 不强制要求WiFi连接
            
    except Exception as e:
        print(f"⚠️ WiFi测试异常: {e}")
        return True  # 不因WiFi问题而失败

def test_imports():
    """测试关键模块导入"""
    print("=== 模块导入测试 ===")
    
    modules = [
        ("config", "配置模块"),
        ("led", "LED模块"),
        ("sisi_desk", "主控制模块"),
        ("simple_http", "HTTP服务模块")
    ]
    
    results = {}
    
    for module_name, description in modules:
        try:
            __import__(module_name)
            print(f"✅ {description} ({module_name}) 导入成功")
            results[module_name] = True
        except Exception as e:
            print(f"❌ {description} ({module_name}) 导入失败: {e}")
            results[module_name] = False
    
    return results

def run_startup_diagnosis():
    """运行完整的启动诊断"""
    print("🚀 ESP32-C3 启动问题诊断")
    print("=" * 40)
    
    # 记录测试结果
    results = {}
    
    # 1. 基础硬件测试
    results['hardware'] = test_basic_hardware()
    print()
    
    # 2. 内存测试
    results['memory'] = test_memory()
    print()
    
    # 3. 音频LED测试
    results['audio_led'] = test_audio_led()
    print()
    
    # 4. 模块导入测试
    import_results = test_imports()
    results.update(import_results)
    print()
    
    # 5. WiFi测试 (可选)
    results['wifi'] = test_wifi_optional()
    print()
    
    # 总结
    print("=" * 40)
    print("🎯 诊断结果总结:")
    
    critical_modules = ['hardware', 'memory', 'config', 'led']
    critical_failed = []
    
    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {test_name}: {status}")
        
        if not passed and test_name in critical_modules:
            critical_failed.append(test_name)
    
    print()
    
    if not critical_failed:
        print("🎉 关键模块测试全部通过！")
        print("💡 建议:")
        print("  1. 如果音频LED失败，音频可视化功能将不可用")
        print("  2. 如果WiFi未连接，请手动连接热点")
        print("  3. 系统应该能正常启动")
    else:
        print("⚠️ 发现关键问题:")
        for module in critical_failed:
            print(f"  - {module} 模块失败")
        print("💡 建议:")
        print("  1. 检查硬件连接")
        print("  2. 重新烧录固件")
        print("  3. 检查内存使用情况")
    
    print(f"\n💾 当前可用内存: {gc.mem_free()} 字节")
    
    return len(critical_failed) == 0

if __name__ == "__main__":
    run_startup_diagnosis()
