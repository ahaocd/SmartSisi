#!/usr/bin/env python3
"""
测试WordPress发布功能
"""

import json
import requests
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# WordPress配置
WORDPRESS_URL = "https://xasia.cc"
WORDPRESS_USER = "67859543"
WORDPRESS_APP_PASSWORD = "XqXt bHFX rwL3 M5kc rDqd HXD2"
API_BASE = f"{WORDPRESS_URL}/wp-json/wp/v2"
AUTH = (WORDPRESS_USER, WORDPRESS_APP_PASSWORD)

def test_wordpress_connection():
    """测试WordPress连接"""
    logger.info("测试WordPress连接...")
    
    session = requests.Session()
    session.trust_env = False
    
    try:
        # 测试获取文章列表
        response = session.get(
            f"{API_BASE}/posts",
            auth=AUTH,
            timeout=10,
            params={"per_page": 1}
        )
        
        logger.info(f"连接测试状态码: {response.status_code}")
        logger.info(f"连接测试响应: {response.text[:200]}")
        
        if response.status_code == 200:
            posts = response.json()
            logger.info(f"成功获取文章列表，类型: {type(posts)}")
            if isinstance(posts, list):
                logger.info(f"文章数量: {len(posts)}")
            return True
        else:
            logger.error(f"连接失败: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"连接异常: {e}")
        return False

def test_publish_article():
    """测试发布文章"""
    logger.info("测试发布文章...")
    
    # 文章数据
    post_data = {
        "title": "绕过Google账号注册二维码验证的完整解决方案",
        "content": """<h1>绕过Google账号注册二维码验证的完整解决方案</h1>

<h2>问题背景：Google账号注册的新限制</h2>

<p>近年来，Google加强了账号注册的安全验证机制，特别是在某些地区的用户会遇到一个棘手问题——<strong>二维码设备验证</strong>。这种验证方式会让用户扫描二维码绑定设备，但对大多数人而言几乎无法完成操作。</p>

<h3>风控升级解析</h3>

<p>Google的风控系统经历了多重升级：</p>

<ol>
<li><strong>IP地域检测</strong>：早期主要通过IP地址判断用户所在地区，大陆IP直接限制注册</li>
<li><strong>设备指纹识别</strong>：现在新增了对物理设备的检测，记录设备的历史行为特征</li>
<li><strong>行为模式分析</strong>：频繁注册或登录多个账号的行为会被标记为异常</li>
</ol>

<h2>完整解决方案：创建纯净虚拟环境</h2>

<h3>方法一：使用全新物理设备（最简方案）</h3>

<p>如果你有一台<strong>从未</strong>或<strong>极少</strong>用于Google账号操作的设备：</p>

<ol>
<li>确保设备网络使用干净的代理IP（推荐美国节点）</li>
<li>清除浏览器所有历史记录和Cookies</li>
<li>使用隐私模式或无痕窗口进行注册</li>
</ol>""",
        "status": "draft",
        "categories": [8],  # 使用指南分类
    }
    
    session = requests.Session()
    session.trust_env = False
    
    try:
        logger.info(f"发布数据: {post_data}")
        
        response = session.post(
            f"{API_BASE}/posts",
            json=post_data,
            auth=AUTH,
            timeout=30,
            headers={"Content-Type": "application/json"}
        )
        
        logger.info(f"发布响应状态码: {response.status_code}")
        logger.info(f"发布响应内容: {response.text[:500]}")
        
        if response.status_code in [200, 201]:
            try:
                result = response.json()
                logger.info(f"发布成功！文章ID: {result.get('id')}")
                logger.info(f"文章链接: {result.get('link')}")
                return True
            except Exception as json_error:
                logger.error(f"JSON解析失败: {json_error}")
                return False
        else:
            logger.error(f"发布失败: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"发布异常: {e}")
        return False

def main():
    """主函数"""
    logger.info("开始WordPress发布测试")
    
    # 1. 测试连接
    if not test_wordpress_connection():
        logger.error("WordPress连接失败，停止测试")
        return
    
    # 2. 测试发布
    if test_publish_article():
        logger.info("WordPress发布测试成功！")
    else:
        logger.error("WordPress发布测试失败！")

if __name__ == "__main__":
    main()