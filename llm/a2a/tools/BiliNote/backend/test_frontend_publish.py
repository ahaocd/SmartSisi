#!/usr/bin/env python3
"""
测试前端发布功能
"""

import json
import requests
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_frontend_publish():
    """测试前端发布API"""
    
    # 模拟前端发送的数据
    publish_data = {
        "title": "绕过Google账号注册二维码验证的完整解决方案",
        "content": """# 绕过Google账号注册二维码验证的完整解决方案

## 问题背景：Google账号注册的新限制

近年来，Google加强了账号注册的安全验证机制，特别是在某些地区的用户会遇到一个棘手问题——**二维码设备验证**。这种验证方式会让用户扫描二维码绑定设备，但对大多数人而言几乎无法完成操作。

### 风控升级解析

Google的风控系统经历了多重升级：

1. **IP地域检测**：早期主要通过IP地址判断用户所在地区，大陆IP直接限制注册
2. **设备指纹识别**：现在新增了对物理设备的检测，记录设备的历史行为特征
3. **行为模式分析**：频繁注册或登录多个账号的行为会被标记为异常

## 完整解决方案：创建纯净虚拟环境

### 方法一：使用全新物理设备（最简方案）

如果你有一台**从未**或**极少**用于Google账号操作的设备：

1. 确保设备网络使用干净的代理IP（推荐美国节点）
2. 清除浏览器所有历史记录和Cookies
3. 使用隐私模式或无痕窗口进行注册""",
        "status": "publish"
    }
    
    try:
        logger.info("测试前端发布API...")
        
        response = requests.post(
            "http://localhost:8483/api/wordpress/publish/single",
            json=publish_data,
            timeout=30
        )
        
        logger.info(f"API响应状态码: {response.status_code}")
        logger.info(f"API响应内容: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                logger.info(f"✅ 前端发布测试成功！")
                logger.info(f"文章ID: {result.get('post_id')}")
                logger.info(f"文章链接: {result.get('post_url')}")
                logger.info(f"文章标题: {result.get('title')}")
                logger.info(f"文章分类: {result.get('category')}")
                return True
            else:
                logger.error(f"❌ 发布失败: {result.get('error')}")
                return False
        else:
            logger.error(f"❌ API调用失败: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ 测试异常: {e}")
        return False

if __name__ == "__main__":
    test_frontend_publish()