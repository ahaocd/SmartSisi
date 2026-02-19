#!/usr/bin/env python3
"""
测试发布已生成的文章
"""

import json
import requests
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def publish_generated_article():
    """发布已生成的文章"""
    
    # 读取生成的文章
    with open("note_results/6c8ca5b1-c112-4917-a19e-0fa5db732585_markdown.md", "r", encoding="utf-8") as f:
        markdown_content = f.read()
    
    # 转换为HTML（简单转换）
    import markdown
    html_content = markdown.markdown(
        markdown_content,
        extensions=[
            'markdown.extensions.tables',
            'markdown.extensions.fenced_code',
            'markdown.extensions.nl2br',
        ]
    )
    
    # WordPress配置
    WORDPRESS_URL = "https://www.xasia.cc"
    WORDPRESS_USER = "67859543"
    WORDPRESS_APP_PASSWORD = "XqXt bHFX rwL3 M5kc rDqd HXD2"
    API_BASE = f"{WORDPRESS_URL}/wp-json/wp/v2"
    
    # 文章数据
    post_data = {
        "title": "绕过Google账号注册二维码验证的完整解决方案",
        "content": html_content,
        "status": "publish",  # 直接发布
        "categories": [8],  # 使用指南分类
    }
    
    session = requests.Session()
    session.trust_env = False
    
    try:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        logger.info("开始发布文章...")
        response = session.post(
            f"{API_BASE}/posts",
            json=post_data,
            auth=(WORDPRESS_USER, WORDPRESS_APP_PASSWORD),
            headers=headers,
            timeout=30
        )
        
        logger.info(f"发布状态码: {response.status_code}")
        
        if response.status_code == 201:
            result = response.json()
            logger.info(f"✅ 文章发布成功！")
            logger.info(f"文章ID: {result.get('id')}")
            logger.info(f"文章链接: {result.get('link')}")
            logger.info(f"文章标题: {result.get('title', {}).get('rendered', '')}")
            return True
        else:
            logger.error(f"发布失败: {response.status_code}")
            logger.error(f"错误信息: {response.text[:500]}")
            return False
            
    except Exception as e:
        logger.error(f"发布异常: {e}")
        return False

if __name__ == "__main__":
    publish_generated_article()