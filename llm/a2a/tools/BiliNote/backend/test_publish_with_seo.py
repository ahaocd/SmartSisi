#!/usr/bin/env python3
"""
测试带SEO数据的WordPress发布
"""

import json
import requests
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_publish_with_seo():
    """测试带SEO数据的发布"""
    
    # 读取生成的文章（带图片和SEO数据）
    with open("note_results/6c8ca5b1-c112-4917-a19e-0fa5db732585.json", "r", encoding="utf-8") as f:
        article_data = json.load(f)
    
    markdown_content = article_data.get("markdown", "")
    
    # 发布请求数据
    publish_data = {
        "title": "绕过Google账号注册二维码验证的完整解决方案",
        "content": markdown_content,
        "status": "publish",
        "backend_url": "http://localhost:8483"  # 用于图片URL转换
    }
    
    try:
        logger.info("测试带SEO数据的发布...")
        
        response = requests.post(
            "http://localhost:8483/api/wordpress/publish/single",
            json=publish_data,
            timeout=60
        )
        
        logger.info(f"API响应状态码: {response.status_code}")
        result = response.json()
        logger.info(f"API响应内容: {json.dumps(result, ensure_ascii=False, indent=2)}")
        
        if result.get("success"):
            logger.info(f"✅ 发布成功！")
            logger.info(f"文章ID: {result.get('post_id')}")
            logger.info(f"文章链接: {result.get('post_url')}")
            logger.info(f"SEO数据: {result.get('seo_data')}")
            return True
        else:
            logger.error(f"❌ 发布失败: {result.get('error')}")
            return False
            
    except Exception as e:
        logger.error(f"❌ 测试异常: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    test_publish_with_seo()
