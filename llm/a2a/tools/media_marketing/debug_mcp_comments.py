"""
MCP调试工具 - 真实抓取抖音视频页面评论区结构
"""
import asyncio
import aiohttp
import json
import base64
from pathlib import Path

async def debug_video_page():
    """打开抖音视频页面，截图+抓取DOM结构"""

    MCP_URL = 'http://127.0.0.1:12306/mcp'
    session_id = None
    tab_id = None

    # 1. 初始化MCP session
    print('🔧 初始化MCP session...')
    async with aiohttp.ClientSession(trust_env=False) as session:
        payload = {
            'jsonrpc': '2.0',
            'method': 'initialize',
            'params': {
                'protocolVersion': '2024-11-05',
                'capabilities': {},
                'clientInfo': {'name': 'DebugTool', 'version': '1.0'}
            },
            'id': 1
        }
        headers = {'Accept': 'application/json, text/event-stream'}

        async with session.post(MCP_URL, json=payload, headers=headers) as resp:
            session_id = resp.headers.get('mcp-session-id')
            print(f'✅ Session ID: {session_id[:8]}...')

        # 2. 打开测试视频页面
        video_url = 'https://www.douyin.com/video/7451545751861087515'
        print(f'📺 打开视频: {video_url}')

        payload = {
            'jsonrpc': '2.0',
            'method': 'tools/call',
            'params': {
                'name': 'chrome_navigate',
                'arguments': {'url': video_url}
            },
            'id': 2
        }
        headers = {
            'mcp-session-id': session_id,
            'Accept': 'application/json, text/event-stream'
        }

        async with session.post(MCP_URL, json=payload, headers=headers) as resp:
            text = await resp.text()
            try:
                result = json.loads(text)
                tab_id = result.get('result', {}).get('tabId')
                print(f'✅ Tab ID: {tab_id}')
            except:
                print('⚠️ 解析tabId失败，使用SSE解析')
                lines = text.split('\n')
                for line in lines:
                    if line.startswith('data: '):
                        try:
                            data = json.loads(line[6:])
                            tab_id = data.get('result', {}).get('tabId')
                            if tab_id:
                                print(f'✅ Tab ID: {tab_id}')
                                break
                        except:
                            pass

        # 3. 等待页面加载
        print('⏳ 等待10秒加载完整页面...')
        await asyncio.sleep(10)

        # 4. 滚动到评论区
        print('📜 滚动页面加载评论...')
        for i in range(5):
            payload = {
                'jsonrpc': '2.0',
                'method': 'tools/call',
                'params': {
                    'name': 'chrome_keyboard',
                    'arguments': {'tabId': tab_id, 'keys': ['PageDown']}
                },
                'id': 3 + i
            }
            async with session.post(MCP_URL, json=payload, headers=headers) as resp:
                await resp.text()
            await asyncio.sleep(2)

        print('✅ 滚动完成')

        # 5. 截图
        print('📸 截取当前页面...')
        payload = {
            'jsonrpc': '2.0',
            'method': 'tools/call',
            'params': {
                'name': 'chrome_screenshot',
                'arguments': {
                    'tabId': tab_id,
                    'fullPage': True,
                    'storeBase64': True
                }
            },
            'id': 100
        }

        async with session.post(MCP_URL, json=payload, headers=headers) as resp:
            text = await resp.text()
            try:
                result = json.loads(text)
                content = result.get('result', {}).get('content', [])
                if content:
                    text_data = content[0].get('text', '')
                    data_obj = json.loads(text_data)
                    screenshot_b64 = data_obj.get('base64Data') or data_obj.get('base64')

                    # 保存截图
                    img_bytes = base64.b64decode(screenshot_b64)
                    screenshot_path = Path('debug_full_page.png')
                    screenshot_path.write_bytes(img_bytes)
                    print(f'✅ 截图已保存: {screenshot_path.absolute()}')
            except Exception as e:
                print(f'❌ 截图失败: {e}')

        # 6. 获取完整HTML
        print('📄 获取页面HTML...')
        payload = {
            'jsonrpc': '2.0',
            'method': 'tools/call',
            'params': {
                'name': 'chrome_get_web_content',
                'arguments': {
                    'tabId': tab_id,
                    'selector': 'body',
                    'htmlContent': True
                }
            },
            'id': 101
        }

        async with session.post(MCP_URL, json=payload, headers=headers) as resp:
            text = await resp.text()
            try:
                result = json.loads(text)
                content_list = result.get('result', {}).get('content', [])
                if content_list:
                    text_str = content_list[0].get('text', '')
                    parsed_data = json.loads(text_str)
                    html_content = parsed_data.get('htmlContent', '')

                    # 保存HTML
                    html_path = Path('debug_full_html_with_comments.html')
                    html_path.write_text(html_content, encoding='utf-8')
                    print(f'✅ HTML已保存: {html_path.absolute()} ({len(html_content)} 字符)')

                    # 分析评论区结构
                    import re
                    comment_items = re.findall(r'data-e2e="comment-item"', html_content)
                    comment_list = re.findall(r'data-e2e="comment-list"', html_content)
                    comment_text = re.findall(r'data-e2e="comment-text"', html_content)

                    print(f'\n📊 评论区DOM分析:')
                    print(f'   - comment-item: {len(comment_items)} 个')
                    print(f'   - comment-list: {len(comment_list)} 个')
                    print(f'   - comment-text: {len(comment_text)} 个')

            except Exception as e:
                print(f'❌ 获取HTML失败: {e}')

        # 7. 执行JS检测评论区
        print('\n🔍 执行JS检测评论区结构...')
        detect_js = """
        (() => {
            const result = {
                comment_items: document.querySelectorAll('[data-e2e="comment-item"]').length,
                comment_list: document.querySelectorAll('[data-e2e="comment-list"]').length,
                comment_area_classes: [],
                all_data_e2e: []
            };

            // 收集所有 data-e2e 属性
            document.querySelectorAll('[data-e2e]').forEach(el => {
                const e2e = el.getAttribute('data-e2e');
                if (e2e.includes('comment')) {
                    result.all_data_e2e.push(e2e);
                }
            });

            // 去重
            result.all_data_e2e = [...new Set(result.all_data_e2e)];

            return result;
        })()
        """

        payload = {
            'jsonrpc': '2.0',
            'method': 'tools/call',
            'params': {
                'name': 'chrome_inject_script',
                'arguments': {
                    'tabId': tab_id,
                    'script': detect_js
                }
            },
            'id': 102
        }

        async with session.post(MCP_URL, json=payload, headers=headers) as resp:
            text = await resp.text()
            try:
                result = json.loads(text)
                content = result.get('result', {}).get('content', [])
                if content:
                    text_str = content[0].get('text', '{}')
                    js_result = json.loads(text_str)

                    print('\n📋 JS检测结果:')
                    print(f'   comment_items: {js_result.get("comment_items", 0)}')
                    print(f'   comment_list: {js_result.get("comment_list", 0)}')
                    print(f'   所有评论相关data-e2e: {js_result.get("all_data_e2e", [])}')
            except Exception as e:
                print(f'❌ JS执行失败: {e}')

        print('\n✅ 调试完成！')
        print('📁 生成的文件:')
        print('   - debug_full_page.png (完整截图)')
        print('   - debug_full_html_with_comments.html (完整HTML)')

if __name__ == '__main__':
    # Windows UTF-8修复
    import sys
    if sys.platform == 'win32':
        try:
            import codecs
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
        except:
            pass

    asyncio.run(debug_video_page())
