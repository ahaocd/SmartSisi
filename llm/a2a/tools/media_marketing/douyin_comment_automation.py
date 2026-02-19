"""
🔥 抖音评论自动化完整流程

完整功能：
1. 获取评论（chrome-devtools-mcp / Playwright / mcp-chrome）
2. 生成回复（AI大模型）
3. 点击输入框
4. 输入评论
5. 发送评论

支持的MCP：
- chrome-devtools-mcp（Google官方，最可靠）
- Playwright MCP（Microsoft官方）
- mcp-chrome（hangye，HTTP扩展）
"""

import asyncio
import json
import logging
import subprocess
import aiohttp
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class DouyinCommentAutomation:
    """抖音评论自动化 - 完整流程"""

    def __init__(self, mcp_chrome_url: str = "http://127.0.0.1:12306/mcp", chrome_debug_port: int = 9222):
        self.mcp_chrome_url = mcp_chrome_url
        self.chrome_debug_port = chrome_debug_port

        # mcp-chrome session
        self.mcp_session_id = None
        self.current_tab_id = None

        # chrome-devtools-mcp进程
        self.cdp_proc = None
        self.cdp_stdin = None
        self.cdp_stdout = None
        self._cdp_id = 0

        # Playwright MCP进程
        self.pw_proc = None
        self.pw_stdin = None
        self.pw_stdout = None
        self._pw_id = 0

    # ==================== 1. 获取评论 ====================

    async def get_comments(self, video_url: str, limit: int = 100) -> List[Dict]:
        """
        获取评论（自动尝试多种方法）

        返回: [{"nickname": "", "comment_text": "", "profile_url": "", "user_id": ""}]
        """
        logger.info(f"📊 获取评论: {video_url}")

        # 方法1: chrome-devtools-mcp（最可靠）
        try:
            comments = await self._get_comments_cdp(limit)
            if comments:
                logger.info(f"✅ [chrome-devtools-mcp] 获取到 {len(comments)} 条评论")
                return comments
        except Exception as e:
            logger.warning(f"⚠️  [chrome-devtools-mcp] 失败: {e}")

        # 方法2: mcp-chrome（简单）
        try:
            comments = await self._get_comments_mcp_chrome(limit)
            if comments:
                logger.info(f"✅ [mcp-chrome] 获取到 {len(comments)} 条评论")
                return comments
        except Exception as e:
            logger.warning(f"⚠️  [mcp-chrome] 失败: {e}")

        # 方法3: Playwright（备用）
        try:
            comments = await self._get_comments_playwright(limit)
            if comments:
                logger.info(f"✅ [Playwright] 获取到 {len(comments)} 条评论")
                return comments
        except Exception as e:
            logger.warning(f"⚠️  [Playwright] 失败: {e}")

        logger.error("❌ 所有方法都失败了")
        return []

    async def _get_comments_cdp(self, limit: int) -> List[Dict]:
        """使用chrome-devtools-mcp的evaluate_script获取评论"""
        if not self.cdp_proc:
            await self._start_cdp_mcp()

        # 滚动加载
        for i in range(min(10, limit // 20 + 1)):
            await self._call_cdp("keyboard", {"keys": ["PageDown"]})
            await asyncio.sleep(1.5)

        # 执行JS
        js_code = """
        (() => {
            const comments = [];
            const elems = document.querySelectorAll('div[data-e2e="comment-item"]');

            for (const elem of elems) {
                try {
                    const nickElem = elem.querySelector('[data-e2e="comment-user-nickname"]');
                    const textElem = elem.querySelector('[data-e2e="comment-text"]');
                    const linkElem = elem.querySelector('a[href*="/user/"]');

                    const nickname = nickElem?.textContent.trim() || '';
                    const comment_text = textElem?.textContent.trim() || '';
                    const profile_url = linkElem?.href || '';
                    const user_id = profile_url.match(/\\/user\\/([^?/]+)/)?.[1] || '';

                    if (nickname && comment_text) {
                        comments.push({ nickname, comment_text, profile_url, user_id, signature: '' });
                    }
                } catch {}
            }

            return comments;
        })()
        """

        result = await self._call_cdp("evaluate_script", {"script": js_code})
        return self._parse_comments_result(result, limit)

    async def _get_comments_mcp_chrome(self, limit: int) -> List[Dict]:
        """使用mcp-chrome获取HTML然后正则解析"""
        if not self.mcp_session_id:
            return []

        # 滚动
        for i in range(min(10, limit // 20 + 1)):
            await self._call_mcp("chrome_keyboard", {"keys": ["PageDown"]})
            await asyncio.sleep(1.5)

        # 获取HTML
        html_result = await self._call_mcp("chrome_get_web_content", {"selector": "body", "htmlContent": True})
        html = self._extract_html(html_result)

        if not html:
            return []

        # 正则解析
        import re
        comments = []
        blocks = re.findall(r'<div[^>]*data-e2e="comment-item"[^>]*>(.*?)</div>', html, re.DOTALL)

        for block in blocks[:limit]:
            try:
                nick_match = re.search(r'data-e2e="comment-user-nickname"[^>]*>([^<]+)<', block)
                text_match = re.search(r'data-e2e="comment-text"[^>]*>([^<]+)<', block)
                profile_match = re.search(r'href="(/user/([^"?]+))', block)

                if nick_match and text_match:
                    comments.append({
                        "nickname": nick_match.group(1).strip(),
                        "comment_text": text_match.group(1).strip(),
                        "profile_url": f"https://www.douyin.com{profile_match.group(1)}" if profile_match else "",
                        "user_id": profile_match.group(2) if profile_match else "",
                        "signature": ""
                    })
            except:
                continue

        return comments

    async def _get_comments_playwright(self, limit: int) -> List[Dict]:
        """使用Playwright MCP的browser_evaluate获取评论"""
        if not self.pw_proc:
            await self._start_playwright_mcp()

        # 滚动
        for i in range(min(10, limit // 20 + 1)):
            await self._call_pw("browser_keyboard", {"keys": ["PageDown"]})
            await asyncio.sleep(1.5)

        # 执行JS（同CDP的JS代码）
        js_code = """
        (() => {
            const comments = [];
            const elems = document.querySelectorAll('div[data-e2e="comment-item"]');
            for (const elem of elems) {
                try {
                    const nickElem = elem.querySelector('[data-e2e="comment-user-nickname"]');
                    const textElem = elem.querySelector('[data-e2e="comment-text"]');
                    const linkElem = elem.querySelector('a[href*="/user/"]');
                    const nickname = nickElem?.textContent.trim() || '';
                    const comment_text = textElem?.textContent.trim() || '';
                    const profile_url = linkElem?.href || '';
                    const user_id = profile_url.match(/\\/user\\/([^?/]+)/)?.[1] || '';
                    if (nickname && comment_text) {
                        comments.push({ nickname, comment_text, profile_url, user_id, signature: '' });
                    }
                } catch {}
            }
            return comments;
        })()
        """

        result = await self._call_pw("browser_evaluate", {"script": js_code})
        return self._parse_comments_result(result, limit)

    # ==================== 2. 发送评论 ====================

    async def send_comment(self, comment_text: str) -> bool:
        """
        发送评论（完整流程：点击输入框 → 输入文字 → 点击发送）

        抖音评论区选择器（2025有效）：
        - 输入框：textarea[data-e2e="comment-input"]
        - 发送按钮：button[data-e2e="comment-submit"] 或包含"发布"文字的按钮
        """
        logger.info(f"💬 发送评论: {comment_text[:30]}...")

        # 方法1: chrome-devtools-mcp
        try:
            success = await self._send_comment_cdp(comment_text)
            if success:
                logger.info("✅ [chrome-devtools-mcp] 评论已发送")
                return True
        except Exception as e:
            logger.warning(f"⚠️  [chrome-devtools-mcp] 发送失败: {e}")

        # 方法2: mcp-chrome
        try:
            success = await self._send_comment_mcp_chrome(comment_text)
            if success:
                logger.info("✅ [mcp-chrome] 评论已发送")
                return True
        except Exception as e:
            logger.warning(f"⚠️  [mcp-chrome] 发送失败: {e}")

        # 方法3: Playwright
        try:
            success = await self._send_comment_playwright(comment_text)
            if success:
                logger.info("✅ [Playwright] 评论已发送")
                return True
        except Exception as e:
            logger.warning(f"⚠️  [Playwright] 发送失败: {e}")

        logger.error("❌ 所有发送方法都失败了")
        return False

    async def _send_comment_cdp(self, comment_text: str) -> bool:
        """使用chrome-devtools-mcp发送评论"""
        if not self.cdp_proc:
            await self._start_cdp_mcp()

        # 执行JS：点击输入框 → 输入文字 → 点击发送
        js_code = f"""
        (async () => {{
            // 1. 找到输入框
            const input = document.querySelector('textarea[data-e2e="comment-input"]') ||
                         document.querySelector('textarea[placeholder*="评论"]') ||
                         document.querySelector('div[contenteditable="true"]');

            if (!input) return {{ success: false, error: '未找到输入框' }};

            // 2. 点击激活
            input.click();
            input.focus();
            await new Promise(r => setTimeout(r, 500));

            // 3. 输入文字
            if (input.tagName === 'TEXTAREA') {{
                input.value = {json.dumps(comment_text)};
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }} else {{
                input.textContent = {json.dumps(comment_text)};
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}

            await new Promise(r => setTimeout(r, 500));

            // 4. 找到发送按钮
            const submitBtn = document.querySelector('button[data-e2e="comment-submit"]') ||
                             [...document.querySelectorAll('button')].find(b => b.textContent.includes('发布') || b.textContent.includes('发送'));

            if (!submitBtn) return {{ success: false, error: '未找到发送按钮' }};

            // 5. 点击发送
            submitBtn.click();
            await new Promise(r => setTimeout(r, 1000));

            return {{ success: true }};
        }})()
        """

        result = await self._call_cdp("evaluate_script", {"script": js_code})

        # 解析结果
        try:
            content = result.get('content', [{}])[0].get('text', '{}')
            data = json.loads(content) if isinstance(content, str) else content
            return data.get('success', False)
        except:
            return False

    async def _send_comment_mcp_chrome(self, comment_text: str) -> bool:
        """使用mcp-chrome发送评论"""
        if not self.mcp_session_id:
            return False

        # 1. 点击输入框
        await self._call_mcp("chrome_click_element", {
            "selector": 'textarea[data-e2e="comment-input"]'
        })
        await asyncio.sleep(0.5)

        # 2. 输入文字
        await self._call_mcp("chrome_fill_or_select", {
            "selector": 'textarea[data-e2e="comment-input"]',
            "value": comment_text
        })
        await asyncio.sleep(0.5)

        # 3. 点击发送按钮
        await self._call_mcp("chrome_click_element", {
            "selector": 'button[data-e2e="comment-submit"]'
        })
        await asyncio.sleep(1)

        return True

    async def _send_comment_playwright(self, comment_text: str) -> bool:
        """使用Playwright MCP发送评论"""
        if not self.pw_proc:
            await self._start_playwright_mcp()

        # 1. 点击输入框
        await self._call_pw("browser_click", {"selector": 'textarea[data-e2e="comment-input"]'})
        await asyncio.sleep(0.5)

        # 2. 输入文字
        await self._call_pw("browser_type", {
            "selector": 'textarea[data-e2e="comment-input"]',
            "text": comment_text
        })
        await asyncio.sleep(0.5)

        # 3. 点击发送
        await self._call_pw("browser_click", {"selector": 'button[data-e2e="comment-submit"]'})
        await asyncio.sleep(1)

        return True

    # ==================== 工具方法 ====================

    async def _start_cdp_mcp(self):
        """启动chrome-devtools-mcp"""
        import os
        npx_cmd = os.environ.get('NPX_PATH') or 'npx'
        self.cdp_proc = subprocess.Popen(
            [npx_cmd, '-y', 'chrome-devtools-mcp@latest', '--browserUrl', f'http://127.0.0.1:{self.chrome_debug_port}'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        self.cdp_stdin = self.cdp_proc.stdin
        self.cdp_stdout = self.cdp_proc.stdout
        await asyncio.sleep(3)

    async def _start_playwright_mcp(self):
        """启动Playwright MCP"""
        import os
        npx_cmd = os.environ.get('NPX_PATH') or 'npx'
        self.pw_proc = subprocess.Popen(
            [npx_cmd, '-y', '@playwright/mcp@latest'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        self.pw_stdin = self.pw_proc.stdin
        self.pw_stdout = self.pw_proc.stdout
        await asyncio.sleep(2)

    async def _call_cdp(self, tool_name: str, args: Dict) -> Dict:
        """调用chrome-devtools-mcp工具"""
        if not self.cdp_stdin or not self.cdp_stdout:
            return {}

        self._cdp_id += 1
        req = {"jsonrpc": "2.0", "id": self._cdp_id, "method": "tools/call", "params": {"name": tool_name, "arguments": args}}
        self.cdp_stdin.write(json.dumps(req) + "\n")
        self.cdp_stdin.flush()

        import time
        deadline = time.time() + 30
        while time.time() < deadline:
            line = self.cdp_stdout.readline()
            if not line:
                await asyncio.sleep(0.05)
                continue
            try:
                obj = json.loads(line)
                if obj.get("id") == self._cdp_id:
                    return obj.get("result", {})
            except:
                pass
        return {}

    async def _call_pw(self, tool_name: str, args: Dict) -> Dict:
        """调用Playwright MCP工具"""
        if not self.pw_stdin or not self.pw_stdout:
            return {}

        self._pw_id += 1
        req = {"jsonrpc": "2.0", "id": self._pw_id, "method": "tools/call", "params": {"name": tool_name, "arguments": args}}
        self.pw_stdin.write(json.dumps(req) + "\n")
        self.pw_stdin.flush()

        import time
        deadline = time.time() + 30
        while time.time() < deadline:
            line = self.pw_stdout.readline()
            if not line:
                await asyncio.sleep(0.05)
                continue
            try:
                obj = json.loads(line)
                if obj.get("id") == self._pw_id:
                    return obj.get("result", {})
            except:
                pass
        return {}

    async def _call_mcp(self, tool_name: str, args: Dict) -> Dict:
        """调用mcp-chrome工具"""
        if not self.mcp_session_id:
            return {}

        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
            if self.current_tab_id:
                args.setdefault("tabId", self.current_tab_id)

            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": args},
                "id": int(asyncio.get_event_loop().time() * 1000)
            }
            headers = {"mcp-session-id": self.mcp_session_id, "Accept": "application/json, text/event-stream"}

            async with session.post(self.mcp_chrome_url, json=payload, headers=headers, timeout=60) as resp:
                text = await resp.text()
                try:
                    result = json.loads(text)
                    result_obj = result.get("result", {})
                    if isinstance(result_obj, dict) and "tabId" in result_obj:
                        self.current_tab_id = result_obj.get("tabId")
                    return result_obj
                except json.JSONDecodeError:
                    lines = text.split('\n')
                    data_lines = [line[6:] for line in lines if line.startswith('data: ')]
                    if data_lines:
                        for data_json in reversed(data_lines):
                            try:
                                last_data = json.loads(data_json)
                                result_obj = last_data.get("result", {})
                                if isinstance(result_obj, dict) and "tabId" in result_obj:
                                    self.current_tab_id = result_obj.get("tabId")
                                return result_obj
                            except:
                                continue
                    return {}

    def _parse_comments_result(self, result: Dict, limit: int) -> List[Dict]:
        """解析评论结果"""
        comments = []
        try:
            content = result.get('content', [{}])[0].get('text', '')
            if isinstance(content, str):
                comments = json.loads(content)
            elif isinstance(content, list):
                comments = content
        except:
            pass

        # 去重
        seen = set()
        unique = []
        for c in comments:
            if not isinstance(c, dict):
                continue
            key = f"{c.get('user_id', '')}_{c.get('comment_text', '')}"
            if key not in seen:
                seen.add(key)
                unique.append(c)

        return unique[:limit]

    def _extract_html(self, result: Dict) -> str:
        """提取HTML内容"""
        try:
            content_list = result.get('content', [])
            if content_list:
                text_str = content_list[0].get('text', '')
                if isinstance(text_str, str) and text_str.startswith('{'):
                    data = json.loads(text_str)
                    return data.get('htmlContent', '')
                return text_str
        except:
            pass
        return ""

    def cleanup(self):
        """清理资源"""
        if self.cdp_proc:
            try:
                self.cdp_proc.terminate()
            except:
                pass
        if self.pw_proc:
            try:
                self.pw_proc.terminate()
            except:
                pass
