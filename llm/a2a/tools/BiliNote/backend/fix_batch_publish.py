#!/usr/bin/env python
"""修复批量发布代码"""

import re

# 读取文件
with open('app/routers/note.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 查找并替换代码
old_code = '''            # 分类判断
            category = publisher.classify_article(title, content)
            
            # 优化标题
            optimized_title = publisher.optimize_title(title, content)
            
            # 转换为 HTML
            html_content = markdown.markdown(
                content,
                extensions=['markdown.extensions.tables', 'markdown.extensions.fenced_code', 'markdown.extensions.nl2br']
            )
            
            # 发布
            publish_status = "publish" if auto_publish else "draft"
            result = publisher.publish_to_wordpress(
                title=optimized_title,
                content=html_content,
                category=category,
                status=publish_status
            )'''

new_code = '''            # 提取SEO元数据
            seo_data = {'seo_title': '', 'seo_description': '', 'focus_keyword': '', 'keywords': ''}
            seo_pattern = r'---SEO-METADATA---\\s*\\n(.*?)\\n---END-SEO---'
            seo_match = re.search(seo_pattern, content, re.DOTALL)
            if seo_match:
                seo_block = seo_match.group(1)
                for line in seo_block.strip().split('\\n'):
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
                content = re.sub(r'\\n*---\\s*\\n+---SEO-METADATA---.*?---END-SEO---\\s*$', '', content, flags=re.DOTALL)
                content = re.sub(r'\\n*---SEO-METADATA---.*?---END-SEO---\\s*$', '', content, flags=re.DOTALL)
                content = content.rstrip()
                logger.info(f"[批量 {batch_id}] 提取SEO: {seo_data.get('seo_title', 'N/A')}")

            # 上传本地图片到WordPress
            content = publisher.process_local_images(content)

            # 分类判断
            category = publisher.classify_article(title, content)

            # 使用SEO标题或优化标题
            if seo_data.get('seo_title'):
                optimized_title = seo_data['seo_title']
            else:
                optimized_title = publisher.optimize_title(title, content)

            # 转换为 HTML
            html_content = markdown.markdown(
                content,
                extensions=['markdown.extensions.tables', 'markdown.extensions.fenced_code', 'markdown.extensions.nl2br']
            )

            # 发布
            publish_status = "publish" if auto_publish else "draft"
            result = publisher.publish_to_wordpress(
                title=optimized_title,
                content=html_content,
                category=category,
                status=publish_status,
                seo_data=seo_data
            )'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('app/routers/note.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("✓ 修复成功！")
else:
    print("✗ 未找到目标代码，尝试其他方式...")
    # 尝试用正则匹配
    pattern = r'# 分类判断\s+category = publisher\.classify_article.*?status=publish_status\s*\)'
    if re.search(pattern, content, re.DOTALL):
        print("找到代码块，正在替换...")
    else:
        print("未找到匹配的代码块")
