#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
浏览器指纹随机生成器
每次运行生成不同的浏览器环境，躲避风控
"""

import random

class BrowserFingerprint:
    """浏览器指纹生成器"""
    
    # Chrome版本列表（最新版本）
    CHROME_VERSIONS = [
        "130.0.0.0",
        "131.0.0.0", 
        "132.0.0.0",
        "133.0.0.0",
        "134.0.0.0"
    ]
    
    # 分辨率列表
    RESOLUTIONS = [
        {'width': 1920, 'height': 1080},
        {'width': 1366, 'height': 768},
        {'width': 1536, 'height': 864},
        {'width': 1440, 'height': 900},
        {'width': 2560, 'height': 1440},
    ]
    
    # 操作系统版本
    OS_VERSIONS = [
        "Windows NT 10.0; Win64; x64",
        "Windows NT 11.0; Win64; x64",
    ]
    
    # WebGL Vendor
    WEBGL_VENDORS = [
        "Google Inc. (NVIDIA)",
        "Google Inc. (Intel)",
        "Google Inc. (AMD)",
    ]
    
    # 语言
    LANGUAGES = [
        "zh-CN",
        "zh-CN,zh",
        "en-US,en",
    ]
    
    @classmethod
    def generate(cls):
        """生成随机浏览器指纹"""
        chrome_version = random.choice(cls.CHROME_VERSIONS)
        os_version = random.choice(cls.OS_VERSIONS)
        resolution = random.choice(cls.RESOLUTIONS)
        webgl_vendor = random.choice(cls.WEBGL_VENDORS)
        language = random.choice(cls.LANGUAGES)
        
        # 随机硬件参数
        hardware_concurrency = random.choice([4, 8, 12, 16])
        device_memory = random.choice([4, 8, 16])
        
        # 随机时区偏移
        timezone_offset = random.choice([-480, -420, -360])  # 中国时区
        
        # 随机Canvas噪点
        canvas_noise = random.random()
        
        # User-Agent
        user_agent = f"Mozilla/5.0 ({os_version}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version} Safari/537.36"
        
        # 浏览器启动参数
        args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            f'--window-size={resolution["width"]},{resolution["height"]}',
            f'--lang={language}',
        ]
        
        # 指纹脚本（使用随机参数）
        init_script = f"""
            // 隐藏webdriver
            Object.defineProperty(navigator, 'webdriver', {{
                get: () => undefined
            }});
            
            // 隐藏自动化控制
            delete navigator.__proto__.webdriver;
            
            // 随机化canvas指纹（使用随机噪点）
            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function(type) {{
                if (type === 'image/png') {{
                    const data = originalToDataURL.apply(this, arguments);
                    return data.replace(/^data:image\\/png/, 'data:image/png;noise={canvas_noise}');
                }}
                return originalToDataURL.apply(this, arguments);
            }};
            
            // 随机化WebGL指纹
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {{
                if (parameter === 37445) {{
                    return '{webgl_vendor}';
                }}
                if (parameter === 37446) {{
                    return 'ANGLE (NVIDIA GeForce GTX ' + Math.floor(Math.random() * 2000 + 1000) + ' Direct3D11 vs_5_0 ps_5_0)';
                }}
                return getParameter.apply(this, arguments);
            }};
            
            // 随机化硬件并发
            Object.defineProperty(navigator, 'hardwareConcurrency', {{
                get: () => {hardware_concurrency}
            }});
            
            // 随机化deviceMemory
            Object.defineProperty(navigator, 'deviceMemory', {{
                get: () => {device_memory}
            }});
            
            // 随机化屏幕分辨率
            Object.defineProperty(screen, 'width', {{
                get: () => {resolution["width"]}
            }});
            Object.defineProperty(screen, 'height', {{
                get: () => {resolution["height"]}
            }});
            Object.defineProperty(screen, 'availWidth', {{
                get: () => {resolution["width"]}
            }});
            Object.defineProperty(screen, 'availHeight', {{
                get: () => {resolution["height"] - 40}
            }});
            
            // 随机化时区
            Date.prototype.getTimezoneOffset = function() {{
                return {timezone_offset};
            }};
            
            // 伪造Chrome插件
            Object.defineProperty(navigator, 'plugins', {{
                get: () => [
                    {{
                        name: 'Chrome PDF Plugin',
                        filename: 'internal-pdf-viewer',
                        description: 'Portable Document Format'
                    }},
                    {{
                        name: 'Chrome PDF Viewer',
                        filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                        description: ''
                    }},
                    {{
                        name: 'Native Client',
                        filename: 'internal-nacl-plugin',
                        description: ''
                    }}
                ]
            }});
            
            // 伪造navigator.languages
            Object.defineProperty(navigator, 'languages', {{
                get: () => ['{language}', 'zh', 'en']
            }});
            
            // 伪造permission
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({{ state: Notification.permission }}) :
                    originalQuery(parameters)
            );
            
            // 添加Chrome运行时对象
            window.chrome = {{
                runtime: {{}}
            }};
        """
        
        return {
            'user_agent': user_agent,
            'viewport': resolution,
            'args': args,
            'init_script': init_script,
            'chrome_version': chrome_version,
            'hardware_concurrency': hardware_concurrency,
            'device_memory': device_memory,
            'canvas_noise': canvas_noise,
        }

if __name__ == "__main__":
    # 测试
    for i in range(3):
        print(f"\n=== 指纹 {i+1} ===")
        fp = BrowserFingerprint.generate()
        print(f"Chrome版本: {fp['chrome_version']}")
        print(f"分辨率: {fp['viewport']}")
        print(f"User-Agent: {fp['user_agent'][:80]}...")


