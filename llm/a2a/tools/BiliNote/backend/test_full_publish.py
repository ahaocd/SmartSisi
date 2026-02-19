#!/usr/bin/env python
"""完整测试：生成笔记 + 发布到WordPress"""

import os
import sys
import re
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

def test_full_flow():
    """测试完整流程"""
    import markdown
    from app.services.note import NoteGenerator
    from app.services.wordpress_publisher import create_publisher_from_env
    from app.schema.note import DownloadQuality
    
    video_url = "https://www.youtube.com/watch?v=P3E2Ff8DeFo"
    
    print("=" * 60)
    print("完整发布测试")
    print("=" * 60)
    print(f"视频: {video_url}")
    
    # 1. 生成笔记
    print("\n[1/6] 生成笔记...")
    note = NoteGenerator().generate(
        video_url=video_url,
        platform="youtube",
        quality=DownloadQuality("medium"),
        task_id="test-full-publish",
        model_name="MiniMaxAI/MiniMax-M1-80k",
        provider_id="minimax",
        link=False,
        _format=["screenshot", "seo"],
        style="detailed",
        extras="",
        screenshot=True,
    )
    
    if not note or not note.markdown:
        print("✗ 笔记生成失败!")
        return
    
    print(f"✓ 笔记生成成功!")
    print(f"  原始标题: {note.audio_meta.title if note.audio_meta else 'N/A'}")
    
    # 2. 处理内容
    print("\n[2/6] 处理内容...")
    content = note.markdown
    
    # 清理Markdown
    content = re.sub(r'^```(?:markdown)?\s*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'\n```\s*$', '', content, flags=re.MULTILINE)
    
    # 3. 提取SEO
    print("\n[3/6] 提取SEO元数据...")
    seo_data = {'seo_title': '', 'seo_description': '', 'focus_keyword': '', 'keywords': ''}
    seo_pattern = r'---SEO-METADATA---\s*\n(.*?)\n---END-SEO---'
    seo_match = re.search(seo_pattern, content, re.DOTALL)
    if seo_match:
        seo_block = seo_match.group(1)
        for line in seo_block.strip().split('\n'):
            line = line.strip()
            if line.startswith('seo_title:'):
                seo_data['seo_title'] = line.replace('seo_title:', '', 1).strip()
            elif line.startswith('seo_description:'):
                seo_data['seo_description'] = line.replace('seo_description:', '', 1).strip()
            elif line.startswith('focus_keyword:'):
                seo_data['focus_keyword'] = line.replace('focus_keyword:', '', 1).strip()
            elif line.startswith('keywords:'):
                seo_data['keywords'] = line.replace('keywords:', '', 1).strip()
        # 移除SEO块
        content = re.sub(r'\n*---\s*\n+---SEO-METADATA---.*?---END-SEO---\s*$', '', content, flags=re.DOTALL)
        content = re.sub(r'\n*---SEO-METADATA---.*?---END-SEO---\s*$', '', content, flags=re.DOTALL)
        content = content.rstrip()
        print(f"✓ SEO提取成功!")
        print(f"  SEO标题: {seo_data.get('seo_title', 'N/A')}")
        print(f"  SEO描述: {seo_data.get('seo_description', 'N/A')[:50]}...")
        print(f"  焦点关键词: {seo_data.get('focus_keyword', 'N/A')}")
    else:
        print("  未找到SEO数据")
    
    # 检查SEO是否还在内容中
    if '---SEO-METADATA---' in content:
        print("⚠ 警告: SEO块未完全移除!")
    else:
        print("✓ SEO块已从内容中移除")
    
    # 4. 上传图片
    print("\n[4/6] 上传图片到WordPress...")
    publisher = create_publisher_from_env()
    content = publisher.process_local_images(content)
    
    # 检查图片URL
    img_pattern = r'!\[[^\]]*\]\(([^)]+)\)'
    images = re.findall(img_pattern, content)
    print(f"  内容中的图片数: {len(images)}")
    for i, img in enumerate(images[:3]):
        print(f"  [{i+1}] {img[:60]}...")
    
    # 5. 分类和标题
    print("\n[5/6] 分类和标题优化...")
    title = note.audio_meta.title if note.audio_meta else "未命名文章"
    category = publisher.classify_article(title, content)
    
    if seo_data.get('seo_title'):
        optimized_title = seo_data['seo_title']
        print(f"  使用SEO标题: {optimized_title}")
    else:
        optimized_title = publisher.optimize_title(title, content)
        print(f"  LLM优化标题: {optimized_title}")
    
    print(f"  分类: {category.value}")
    
    # 6. 发布
    print("\n[6/6] 发布到WordPress...")
    html_content = markdown.markdown(
        content,
        extensions=['markdown.extensions.tables', 'markdown.extensions.fenced_code', 'markdown.extensions.nl2br']
    )
    
    result = publisher.publish_to_wordpress(
        title=optimized_title,
        content=html_content,
        category=category,
        status="publish",
        seo_data=seo_data
    )
    
    print("\n" + "=" * 60)
    print("发布结果")
    print("=" * 60)
    print(f"成功: {result.get('success')}")
    print(f"文章ID: {result.get('post_id')}")
    print(f"文章URL: {result.get('post_url')}")
    print(f"标题: {optimized_title}")
    if result.get('error'):
        print(f"错误: {result.get('error')}")
    
    return result

if __name__ == "__main__":
    test_full_flow()
