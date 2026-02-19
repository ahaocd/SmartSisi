#!/usr/bin/env python
"""
实际发布测试 - 测试图片上传和SEO元数据
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

def test_real_publish():
    """使用真实数据测试发布"""
    
    # 读取真实的笔记数据
    note_file = "note_results/6c8ca5b1-c112-4917-a19e-0fa5db732585.json"
    
    if not os.path.exists(note_file):
        print(f"笔记文件不存在: {note_file}")
        return
    
    with open(note_file, 'r', encoding='utf-8') as f:
        note_data = json.load(f)
    
    content = note_data.get('markdown', '')
    title = "测试文章 - 图片和SEO功能验证"
    
    print(f"原始内容长度: {len(content)}")
    print(f"原始内容包含图片数: {content.count('![')}")
    print(f"原始内容包含SEO块: {'---SEO-METADATA---' in content}")
    
    # 导入必要模块
    from app.routers.wordpress import extract_seo_metadata, convert_image_urls, remove_screenshot_placeholders
    from app.services.wordpress_publisher import create_publisher_from_env
    import markdown
    
    # 1. 提取SEO
    print("\n" + "=" * 50)
    print("步骤1: 提取SEO元数据")
    content, seo_data = extract_seo_metadata(content)
    print(f"SEO标题: {seo_data.get('seo_title', 'N/A')}")
    print(f"SEO描述: {seo_data.get('seo_description', 'N/A')[:50]}...")
    print(f"焦点关键词: {seo_data.get('focus_keyword', 'N/A')}")
    print(f"清理后内容包含SEO块: {'---SEO-METADATA---' in content}")
    
    # 2. 转换图片URL
    print("\n" + "=" * 50)
    print("步骤2: 转换图片URL")
    backend_url = "http://localhost:8483"
    content = convert_image_urls(content, backend_url)
    
    # 3. 移除截图占位符
    print("\n" + "=" * 50)
    print("步骤3: 移除截图占位符")
    content = remove_screenshot_placeholders(content)
    
    # 4. 创建发布器并处理图片
    print("\n" + "=" * 50)
    print("步骤4: 上传图片到WordPress")
    publisher = create_publisher_from_env()
    
    # 处理本地图片
    content = publisher.process_local_images(content)
    
    # 5. 转换为HTML
    print("\n" + "=" * 50)
    print("步骤5: 转换为HTML")
    html_content = markdown.markdown(
        content,
        extensions=[
            'markdown.extensions.tables',
            'markdown.extensions.fenced_code',
            'markdown.extensions.nl2br',
        ]
    )
    
    print(f"HTML内容长度: {len(html_content)}")
    
    # 检查HTML中的图片
    import re
    img_urls = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html_content)
    if not img_urls:
        img_urls = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', content)
    
    print(f"内容中的图片URL:")
    for url in img_urls[:5]:
        print(f"  - {url[:80]}...")
    
    # 6. 发布文章（草稿模式）
    print("\n" + "=" * 50)
    print("步骤6: 发布文章（草稿模式）")
    
    from app.services.wordpress_publisher import ArticleCategory
    
    result = publisher.publish_to_wordpress(
        title=title,
        content=html_content,
        category=ArticleCategory.TUTORIAL,
        status="draft",  # 草稿模式，不实际发布
        seo_data=seo_data
    )
    
    print(f"\n发布结果:")
    print(f"  成功: {result.get('success')}")
    print(f"  文章ID: {result.get('post_id')}")
    print(f"  文章URL: {result.get('post_url')}")
    if result.get('error'):
        print(f"  错误: {result.get('error')}")


if __name__ == "__main__":
    print("=" * 60)
    print("WordPress 实际发布测试")
    print("=" * 60)
    test_real_publish()
