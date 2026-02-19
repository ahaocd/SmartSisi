"""
🔥 抖音评论抓取器 - 4方案自动切换版

方案1: 语义搜索评论区DOM
方案2: JS注入直接读取
方案3: HTML正则解析
方案4: 交互元素获取

自动切换直到成功！
"""

import asyncio
import json
import logging
import aiohttp
import re
from typing import List, Dict, Optional
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CommentFetcher:
    """抖音评论抓取器 - 4方案自动切换"""

    def __init__(self, mcp_chrome_url: str = "http://127.0.0.1:12306/mcp", chrome_debug_port: int = 9222):
        self.mcp_chrome_url = mcp_chrome_url
        self.chrome_debug_port = chrome_debug_port
        self.session_id = None
        self.current_tab_id = None

    async def get_comments(self, video_url: str, limit: int = 500, method: str = "auto") -> List[Dict]:
        """
        获取评论 - 4方案自动切换

        Args:
            video_url: 视频URL
            limit: 最多获取多少条
            method: "auto"(自动切换)

        Returns:
            [{"nickname": "", "comment_text": "", "profile_url": "", "user_id": ""}]
        """
        logger.info(f"🚀 开始抓取评论（4方案自动切换）: {video_url}")

        # 等待评论区加载
        logger.info("   ⏳ 等待评论区加载（10秒）...")
        await asyncio.sleep(10)

        methods = [
            ("方案1_语义搜索", self._method1_semantic_search),
            ("方案2_JS注入", self._method2_inject_script),
            ("方案3_HTML正则", self._method3_html_regex),
            ("方案4_交互元素", self._method4_interactive_elements)
        ]

        for method_name, method_func in methods:
            logger.info(f"   🔄 尝试 {method_name}...")
            try:
                comments = await method_func(video_url, limit)

                # 验证数据质量
                if comments and self._validate_comments(comments):
                    logger.info(f"   ✅ {method_name} 成功！获取 {len(comments)} 条评论")
                    return comments
                else:
                    logger.warning(f"   ⚠️ {method_name} 数据无效，切换下一个")
            except Exception as e:
                logger.warning(f"   ❌ {method_name} 失败: {e}")
                continue

        logger.error("   ❌ 所有方案都失败")
        return []

    async def _method1_semantic_search(self, video_url: str, limit: int) -> List[Dict]:
        """方案1: 语义搜索找评论区DOM特征"""
        logger.info("      [语义搜索] 搜索评论区...")

        # 搜索包含评论结构的区域
        result = await self._call_mcp("search_tabs_content", {
            "query": "用户昵称 评论内容 data-e2e comment-item comment-user-nickname"
        })

        # 解析搜索结果，找到相关DOM区域
        if not result:
            logger.warning("      [语义搜索] 未找到相关区域")
            return []

        logger.info(f"      [语义搜索] 找到相关区域，尝试提取...")

        # 获取HTML内容
        html_result = await self._call_mcp("chrome_get_web_content", {
            "selector": "body",
            "htmlContent": True
        })

        html_content = self._extract_html_content(html_result)
        if not html_content:
            return []

        # 用正则提取
        return self._parse_comments_from_html(html_content, limit)

    async def _method2_inject_script(self, video_url: str, limit: int) -> List[Dict]:
        """方案2: JS注入直接读取评论DOM"""
        logger.info("      [JS注入] 执行脚本...")

        js_code = """
        (() => {
            const comments = [];

            // 抖音评论区固定特征
            const items = document.querySelectorAll('[data-e2e="comment-item"]');

            items.forEach(item => {
                // 昵称
                const nicknameElem = item.querySelector('[data-e2e="comment-user-nickname"]') ||
                                    item.querySelector('.nickname') ||
                                    item.querySelector('a[href*="/user/"] span');
                const nickname = nicknameElem?.textContent?.trim() || '';

                // 评论文本
                const textElem = item.querySelector('[data-e2e="comment-text"]') ||
                                item.querySelector('.comment-text') ||
                                item.querySelector('[class*="comment"]');
                const text = textElem?.textContent?.trim() || '';

                // 主页链接
                const profileElem = item.querySelector('a[href*="/user/"]');
                const profileUrl = profileElem?.href || '';
                const userId = profileUrl ? profileUrl.split('/user/')[1]?.split('?')[0] : '';

                if (nickname && text && text.length > 3) {
                    // 过滤垃圾文本
                    const invalid = ['举报', '违法', 'SVG', 'Icon', '算法推荐'];
                    if (!invalid.some(bad => text.includes(bad))) {
                        comments.push({
                            nickname: nickname,
                            comment_text: text,
                            profile_url: profileUrl,
                            user_id: userId
                        });
                    }
                }
            });

            return {success: true, count: comments.length, comments: comments};
        })()
        """

        result = await self._call_mcp("chrome_inject_script", {
            "type": "MAIN",
            "jsScript": js_code
        })

        # 解析JS返回结果
        comments = self._parse_js_result(result)
        logger.info(f"      [JS注入] 提取到 {len(comments)} 条评论")
        return comments[:limit]

    async def _method3_html_regex(self, video_url: str, limit: int) -> List[Dict]:
        """方案3: HTML正则解析（原方法）"""
        logger.info("      [HTML正则] 获取HTML...")

        html_result = await self._call_mcp("chrome_get_web_content", {
            "selector": "body",
            "htmlContent": True
        })

        html_content = self._extract_html_content(html_result)
        if not html_content:
            return []

        return self._parse_comments_from_html(html_content, limit)

    async def _method4_interactive_elements(self, video_url: str, limit: int) -> List[Dict]:
        """方案4: 获取交互元素"""
        logger.info("      [交互元素] 查找评论元素...")

        result = await self._call_mcp("chrome_get_interactive_elements", {
            "textQuery": "回复 点赞",
            "includeCoordinates": True
        })

        # 这个方法可能拿不到完整评论内容，作为最后备用
        # 返回空让其他方法处理
        logger.warning("      [交互元素] 此方法无法获取完整评论内容")
        return []

    def _validate_comments(self, comments: List[Dict]) -> bool:
        """验证评论数据质量"""
        if not comments:
            return False

        invalid_texts = ['举报', '违法和不良信息', 'SVG Icon', '算法推荐', 'http']

        # 检查前3条评论
        for c in comments[:3]:
            nickname = c.get('nickname', '').strip()
            text = c.get('comment_text', '').strip()

            # 必须有昵称和评论
            if not nickname or not text:
                logger.warning(f"      [验证失败] 昵称或评论为空")
                return False

            # 评论长度合理
            if len(text) < 2 or len(text) > 500:
                logger.warning(f"      [验证失败] 评论长度异常: {len(text)}")
                return False

            # 不能是页面固定文案
            if any(bad in text for bad in invalid_texts):
                logger.warning(f"      [验证失败] 包含垃圾文本: {text[:30]}")
                return False

            # 昵称不能是固定文字
            if nickname in ['作者', '回复', '删除', '举报']:
                logger.warning(f"      [验证失败] 昵称是固定文字: {nickname}")
                return False

        logger.info(f"      [验证通过] 数据质量合格")
        return True

    def _extract_html_content(self, html_result: Dict) -> str:
        """从MCP结果提取HTML内容"""
        html_content = ""
        try:
            if isinstance(html_result, dict):
                content_list = html_result.get('content', [])
                if content_list and isinstance(content_list, list):
                    text_str = content_list[0].get('text', '')

                    if isinstance(text_str, str) and text_str.startswith('{'):
                        try:
                            data = json.loads(text_str)
                            html_content = data.get('htmlContent', '')
                        except:
                            html_content = text_str
                    else:
                        html_content = text_str

            if html_content:
                logger.info(f"      提取HTML成功，长度: {len(html_content)}")
            return html_content
        except Exception as e:
            logger.error(f"      提取HTML失败: {e}")
            return ""

    def _parse_comments_from_html(self, html_content: str, limit: int) -> List[Dict]:
        """从HTML中解析评论（正则方法）"""
        comments = []

        # 找到所有评论块
        comment_starts = [m.start() for m in re.finditer(r'<div[^>]*data-e2e="comment-item"', html_content)]

        comment_blocks = []
        for i, start_pos in enumerate(comment_starts):
            end_pos = comment_starts[i + 1] if i + 1 < len(comment_starts) else len(html_content)
            block_html = html_content[start_pos:end_pos]
            comment_blocks.append(block_html)

        logger.info(f"      找到 {len(comment_blocks)} 个评论块")

        for block in comment_blocks[:limit]:
            try:
                # 提取昵称
                nickname = ""
                nickname_match = re.search(r'data-e2e="comment-user-nickname"[^>]*>([^<]+)<', block)
                if nickname_match:
                    nickname = nickname_match.group(1).strip()

                if not nickname:
                    nickname_match = re.search(r'href="[^"]*\/user\/[^"]*"[^>]*>.*?<span[^>]*>([^<]+)</span>', block, re.DOTALL)
                    if nickname_match:
                        nickname = nickname_match.group(1).strip()

                # 提取评论
                comment_text = ""
                text_match = re.search(r'data-e2e="comment-text"[^>]*>([^<]+)<', block)
                if text_match:
                    comment_text = text_match.group(1).strip()

                if not comment_text:
                    all_texts = re.findall(r'>([^<]+)<', block)
                    valid_texts = []
                    for t in all_texts:
                        t = t.strip()
                        if (4 <= len(t) <= 500 and
                            t not in ['作者', '回复', '删除', '举报', '点赞', '评论', '分享'] and
                            t != nickname and
                            '举报' not in t and
                            '违法' not in t and
                            'SVG' not in t and
                            not t.startswith('http')):
                            valid_texts.append(t)

                    if valid_texts:
                        comment_text = max(valid_texts, key=len)

                # 提取主页链接
                profile_match = re.search(r'href="(/user/([^"?]+))', block)
                if profile_match:
                    profile_url = f"https://www.douyin.com{profile_match.group(1)}"
                    user_id = profile_match.group(2)
                else:
                    profile_url = ""
                    user_id = ""

                if nickname and comment_text:
                    comments.append({
                        "nickname": nickname,
                        "comment_text": comment_text,
                        "profile_url": profile_url,
                        "user_id": user_id,
                        "signature": ""
                    })
            except Exception as e:
                logger.warning(f"      解析评论块失败: {e}")
                continue

        # 去重
        seen = set()
        unique = []
        for c in comments:
            key = f"{c.get('user_id', '')}_{c.get('comment_text', '')}"
            if key not in seen:
                seen.add(key)
                unique.append(c)

        return unique

    def _parse_js_result(self, result: Dict) -> List[Dict]:
        """解析JS执行结果"""
        comments = []
        try:
            if isinstance(result, dict):
                content_list = result.get('content', [])
                if isinstance(content_list, list) and len(content_list) > 0:
                    text_str = content_list[0].get('text', '{}')
                    data = json.loads(text_str) if isinstance(text_str, str) else text_str

                    if isinstance(data, dict):
                        comments = data.get('comments', [])
                        if isinstance(comments, list):
                            return comments
        except Exception as e:
            logger.error(f"      解析JS结果失败: {e}")

        return []

    def cleanup(self):
        """清理资源"""
        pass

    async def _call_mcp(self, tool_name: str, args: Dict) -> Dict:
        """调用mcp-chrome工具"""
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
            if self.current_tab_id and isinstance(args, dict):
                args.setdefault("tabId", self.current_tab_id)

            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": args},
                "id": int(asyncio.get_event_loop().time() * 1000)
            }
            headers = {
                "mcp-session-id": self.session_id,
                "Accept": "application/json, text/event-stream"
            }

            async with session.post(self.mcp_chrome_url, json=payload, headers=headers, timeout=60) as resp:
                text = await resp.text()

                try:
                    result = json.loads(text)
                    result_obj = result.get("result", {})
                    if isinstance(result_obj, dict) and "tabId" in result_obj:
                        self.current_tab_id = result_obj.get("tabId")
                    return result_obj
                except json.JSONDecodeError:
                    # SSE格式
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
