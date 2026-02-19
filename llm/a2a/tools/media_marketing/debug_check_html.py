#!/usr/bin/env python3
"""
调试脚本：检查抖音视频页面HTML中评论的真实DOM结构
"""
import asyncio
import aiohttp
import json
import re

async def main():
    # 连接mcp-chrome
    mcp_url = "http://127.0.0.1:12306/mcp"

    async with aiohttp.ClientSession() as session:
        # 1. 获取session
        async with session.post(f"{mcp_url}/session/init") as resp:
            data = await resp.json()
            session_id = data.get('sessionId')
            print(f"Session: {session_id}")

        # 2. 获取当前页面HTML
        async with session.post(
            f"{mcp_url}/call",
            json={
                "sessionId": session_id,
                "method": "chrome_get_web_content",
                "params": {"selector": "body", "htmlContent": True}
            }
        ) as resp:
            result = await resp.json()

        # 解析HTML
        html_content = ""
        if isinstance(result, dict) and 'content' in result:
            text_str = result['content'][0].get('text', '')
            if text_str.startswith('{'):
                data = json.loads(text_str)
                html_content = data.get('htmlContent', '')

        print(f"HTML长度: {len(html_content)}")

        # 保存HTML到文件
        with open("debug_video_page.html", "w", encoding="utf-8") as f:
            f.write(html_content)
        print("HTML已保存到 debug_video_page.html")

        # 3. 查找评论相关的属性
        print("\n=== 搜索评论相关属性 ===")

        # 搜索所有data-e2e属性
        data_e2e_attrs = re.findall(r'data-e2e="([^"]+)"', html_content)
        unique_attrs = sorted(set(data_e2e_attrs))
        print(f"找到 {len(unique_attrs)} 个唯一的 data-e2e 属性:")
        for attr in unique_attrs:
            if 'comment' in attr.lower():
                print(f"  🔥 {attr}")
            else:
                print(f"     {attr}")

        # 搜索class中包含comment的
        print("\n=== 搜索 class 包含 'comment' ===")
        comment_classes = re.findall(r'class="([^"]*comment[^"]*)"', html_content, re.IGNORECASE)
        unique_classes = sorted(set(comment_classes[:20]))
        for cls in unique_classes:
            print(f"  {cls[:100]}")

        # 搜索用户链接
        print("\n=== 搜索用户主页链接 ===")
        user_links = re.findall(r'href="(/user/[^"]+)"', html_content)
        print(f"找到 {len(user_links)} 个用户链接")
        for link in user_links[:10]:
            print(f"  {link}")

        # 搜索潜在的评论文本模式
        print("\n=== 搜索评论文本容器 ===")
        # 查找包含中文文本的span/div
        text_patterns = re.findall(
            r'<(span|div)[^>]*class="[^"]*"[^>]*>([^<]{10,100})</\1>',
            html_content
        )
        print(f"找到 {len(text_patterns)} 个文本容器（显示前10个）:")
        for tag, text in text_patterns[:10]:
            print(f"  <{tag}>: {text[:60]}...")

if __name__ == "__main__":
    asyncio.run(main())
