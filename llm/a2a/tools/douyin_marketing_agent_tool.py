"""
抖音评论区获客智能体 - 超级完整版
一个文件搞定所有逻辑！自动启动MCP！

功能：
1. 自动检测并启动mcp-chrome服务
2. 完整的浏览器自动化（登录、搜索、评论、私信）
3. AI智能分析和评论生成
4. 完整的数据库管理和去重
5. 人类行为模拟和风控规避
6. 错误处理和自动重试
7. Cookie自动管理
8. 任务调度和执行

使用方法：
    python douyin_marketing_agent_tool.py
"""

import os
import sys
import json
import time
import logging
import asyncio
import aiohttp
import sqlite3
import hashlib
import random
import subprocess
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

# 导入评论抓取器
try:
    from media_marketing.get_comments_with_cdp import CommentFetcher
    COMMENT_FETCHER_AVAILABLE = True
except Exception as e:
    COMMENT_FETCHER_AVAILABLE = False
    CommentFetcher = None
    print(f"⚠️ CommentFetcher评论抓取器导入失败: {e}")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("DouyinMarketingAgent")

# OpenAI兼容API客户端
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI SDK未安装：pip install openai")

# A2A工具基类
try:
    from SmartSisi.llm.a2a.base_a2a_tool import StandardA2ATool
    A2A_AVAILABLE = True
except ImportError:
    A2A_AVAILABLE = False
    logger.warning("A2A基类未找到，将作为独立脚本运行")
    StandardA2ATool = object  # 占位符


# ==================== MCP服务管理器 ====================
class MCPServiceManager:
    """MCP服务自动管理器"""
    
    def __init__(self):
        self.mcp_url = "http://127.0.0.1:12306/mcp"  # 你的MCP扩展端口（看截图）
        self.chrome_extension_path = None
        self.chrome_process = None  # Chrome进程
        
    async def check_mcp_chrome_running(self) -> bool:
        """检查mcp-chrome是否运行"""
        try:
            # 🔥 绕过VPN代理
            connector = aiohttp.TCPConnector()
            async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
                # 发送一个简单的 MCP 请求测试连接
                payload = {
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "params": {},
                    "id": 1
                }
                async with session.post(self.mcp_url, json=payload, timeout=3) as resp:
                    # 只要服务响应就算成功（不管是否有错误）
                    return resp.status in [200, 400, 500]
        except:
            return False
    
    def find_chrome_extension(self) -> Optional[str]:
        """查找Chrome扩展路径"""
        possible_paths = [
            Path("E:/liusisi/mcpsever/mcp-chrome/releases/chrome-extension/latest/extracted"),
            Path("mcpsever/mcp-chrome/releases/chrome-extension/latest/extracted"),
            Path.home() / "Downloads/mcp-chrome-extension",
        ]
        
        for path in possible_paths:
            if path.exists() and (path / "manifest.json").exists():
                logger.info(f"找到Chrome扩展: {path}")
                return str(path)
        
        logger.warning("未找到Chrome扩展")
        return None
    
    def start_chrome_with_extension(self) -> bool:
        """启动Chrome浏览器（优先使用用户已登录的配置文件；如找到扩展则一并加载）"""
        import subprocess
        import os
        import json
        from pathlib import Path
        
        try:
            # Chrome路径
            chrome_paths = [
                r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
                str(Path.home() / r"AppData\\Local\\Google\\Chrome\\Application\\chrome.exe"),
            ]
            chrome_exe = None
            for path in chrome_paths:
                if Path(path).exists():
                    chrome_exe = str(path)
                    break
            if not chrome_exe:
                logger.error("未找到Chrome浏览器")
                return False
            
            # 读取Chrome用户目录；强制使用 Default 配置，避免 Guest/账户选择器
            user_data_dir = os.path.expandvars(r"%LOCALAPPDATA%\\Google\\Chrome\\User Data")
            profile_dir = "Default"
            local_state = os.path.join(user_data_dir, "Local State")
            try:
                with open(local_state, "r", encoding="utf-8") as f:
                    state = json.load(f)
                last_used = state.get("profile", {}).get("last_used") or profile_dir
                # 若上次为 Guest Profile，则改用 Default，避免弹出选择界面
                if isinstance(last_used, str) and "guest" not in last_used.lower():
                    profile_dir = last_used
            except Exception:
                # 读取失败则使用 Default
                profile_dir = "Default"
            
            # 可选：查找扩展（若用户已有安装，也无需此参数）
            extension_path = self.find_chrome_extension()
            
            logger.info(f"启动Chrome: {chrome_exe}")
            logger.info(f"使用用户数据目录: {user_data_dir} | Profile: {profile_dir}")
            if extension_path:
                logger.info(f"加载扩展: {extension_path}")
            
            args = [
                chrome_exe,
                f"--user-data-dir={user_data_dir}",
                f"--profile-directory={profile_dir}",
                "--no-first-run",
                "--disable-popup-blocking",
                "--disable-infobars",
                "--disable-notifications",
                "--no-default-browser-check",
                "--disable-sync",
                "--disable-features=SignInProfileCreation,BrowserSignin,ChromeSignin",
                "--window-size=1280,800",
                "--window-position=100,100",
                "--new-window",
                "--remote-debugging-port=9222"  # 🔥 添加远程调试端口，让chrome-devtools-mcp可以连接
            ]
            if extension_path:
                args.insert(1, f"--load-extension={extension_path}")
            
            self.chrome_process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info(f"✅ Chrome已启动 (PID: {self.chrome_process.pid})")
            return True
        except Exception as e:
            logger.error(f"启动Chrome失败: {e}")
            return False
    
    def start_mcp_chrome_bridge(self) -> bool:
        """启动mcp-chrome-bridge"""
        try:
            # 使用npx直接运行（无需安装）
            logger.info("启动mcp-chrome-bridge...")
            self.bridge_process = subprocess.Popen(
                ['npx', '-y', 'mcp-chrome-bridge'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            
            time.sleep(5)  # 等待启动
            logger.info(f"✅ mcp-chrome-bridge已启动 (PID: {self.bridge_process.pid})")
            return True
            
        except Exception as e:
            logger.error(f"启动mcp-chrome-bridge失败: {e}")
            return False
    
    async def ensure_mcp_chrome_ready(self) -> bool:
        """确保mcp-chrome服务就绪 - 使用用户已打开的Chrome"""
        logger.info("检查mcp-chrome扩展服务...")
        
        # 检查服务是否已运行（用户的主Chrome）
        if await self.check_mcp_chrome_running():
            logger.info("✅ mcp-chrome扩展已就绪（连接到你的Chrome）")
            return True
        
        # 服务未运行 → 自动启动Chrome
        logger.warning("⚠️  MCP服务未检测到，正在启动Chrome...")
        
        # 启动Chrome（带扩展）
        if not self.start_chrome_with_extension():
            logger.error("❌ 启动Chrome失败")
            return False
        
        # 等待服务就绪（最多30秒）
        logger.info("⏳ 等待Chrome和扩展启动...")
        for i in range(30):
            await asyncio.sleep(1)
            if await self.check_mcp_chrome_running():
                logger.info("✅ mcp-chrome扩展已连接！")
                return True
        
        logger.error("❌ 等待超时，扩展未启动")
        return False
    
    def cleanup(self):
        """清理资源"""
        if self.chrome_process:
            try:
                self.chrome_process.terminate()
                logger.info("Chrome进程已停止")
            except:
                pass


# ==================== Playwright MCP（仅用于browser_snapshot）====================
class PlaywrightMCPClient:
    """最小Playwright MCP客户端（stdio）- 只为 browser_snapshot 提供支持"""
    def __init__(self):
        self.proc = None
        self.stdin = None
        self.stdout = None
        self._id = 0

    async def start(self) -> bool:
        if self.proc:
            return True
        try:
            import os as _os
            npx_cmd = _os.environ.get('NPX_PATH') or 'npx'
            self.proc = subprocess.Popen(
                [npx_cmd, '-y', '@playwright/mcp@latest'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            self.stdin = self.proc.stdin
            self.stdout = self.proc.stdout
            await asyncio.sleep(2)
            logger.info(f"✅ Playwright MCP已启动 (PID: {self.proc.pid})")
            return True
        except Exception as e:
            logger.error(f"❌ 启动Playwright MCP失败: {e}")
            return False

    async def call(self, name: str, params: Dict | None = None) -> Dict:
        if not self.proc:
            ok = await self.start()
            if not ok:
                return {}

        # Type safety check: stdin/stdout must be initialized
        if self.stdin is None or self.stdout is None:
            logger.error("stdin/stdout not initialized")
            return {}
        try:
            self._id += 1
            req = {
                "jsonrpc": "2.0",
                "id": self._id,
                "method": "tools/call",
                "params": {"name": name, "arguments": params or {}}
            }
            self.stdin.write(json.dumps(req) + "\n")
            self.stdin.flush()

            # 读取一行响应（Playwright MCP按行输出SSE/JSON）
            import time as _t
            deadline = _t.time() + 30
            buf = ""
            while _t.time() < deadline:
                line = self.stdout.readline()
                if not line:
                    await asyncio.sleep(0.05)
                    continue
                buf += line
                # 先尝试直接JSON
                try:
                    obj = json.loads(line)
                    if obj.get('id') == self._id:
                        return obj.get('result', {})
                except Exception:
                    pass
                # 再尝试SSE data: {...}
                try:
                    import re
                    matches = re.findall(r'data: (\{.*?\})\n', buf, re.DOTALL)
                    if matches:
                        last = json.loads(matches[-1])
                        if last.get('id') == self._id:
                            return last.get('result', {})
                except Exception:
                    pass
            return {}
        except Exception as e:
            logger.error(f"Playwright MCP调用失败: {e}")
            return {}

    async def navigate(self, url: str) -> bool:
        # 尝试多种候选名
        for name in ["navigate", "goTo", "goto", "browser_navigate"]:
            res = await self.call(name, {"url": url})
            if isinstance(res, dict):
                return True
        return False

    async def page_down(self, times: int = 1):
        for _ in range(times):
            await self.call("keyboard", {"keys": "PageDown"})
            await asyncio.sleep(0.8)

    async def snapshot(self) -> str:
        for name in ["browser_snapshot", "getSnapshot"]:
            res = await self.call(name, {})
            if isinstance(res, dict):
                content = res.get('content', [])
                if isinstance(content, list) and content:
                    text = content[0].get('text', '')
                    return text or ""
        return ""

    async def close(self):
        try:
            if self.proc:
                self.proc.terminate()
                self.proc = None
        except Exception:
            pass

# ==================== Chrome DevTools MCP ====================
class ChromeDevToolsMCPClient:
    """Chrome DevTools MCP客户端（stdio）- 用于获取网络请求和评论"""
    def __init__(self, browser_url: str = "http://127.0.0.1:9222"):
        self.proc = None
        self.stdin = None
        self.stdout = None
        self._id = 0
        self.browser_url = browser_url

    async def start(self) -> bool:
        if self.proc:
            return True
        try:
            import os as _os
            npx_cmd = _os.environ.get('NPX_PATH') or 'npx'
            self.proc = subprocess.Popen(
                [npx_cmd, '-y', 'chrome-devtools-mcp@latest', f'--browserUrl={self.browser_url}'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            self.stdin = self.proc.stdin
            self.stdout = self.proc.stdout
            await asyncio.sleep(5)  # 等待连接到Chrome
            logger.info(f"✅ Chrome DevTools MCP已启动并连接到 {self.browser_url}")
            return True
        except Exception as e:
            logger.error(f"❌ 启动Chrome DevTools MCP失败: {e}")
            return False

    async def call(self, name: str, params: Dict | None = None) -> Dict:
        if not self.proc:
            ok = await self.start()
            if not ok:
                return {}

        # Type safety check: stdin/stdout must be initialized
        if self.stdin is None or self.stdout is None:
            logger.error("stdin/stdout not initialized (ChromeDevTools)")
            return {}
        try:
            self._id += 1
            req = {
                "jsonrpc": "2.0",
                "id": self._id,
                "method": "tools/call",
                "params": {"name": name, "arguments": params or {}}
            }
            self.stdin.write(json.dumps(req) + "\n")
            self.stdin.flush()

            # 读取响应
            import time as _t
            deadline = _t.time() + 30
            while _t.time() < deadline:
                line = self.stdout.readline()
                if not line:
                    await asyncio.sleep(0.05)
                    continue

                # 处理SSE格式 "data: {...}"
                if line.startswith('data: '):
                    line = line[6:]

                try:
                    obj = json.loads(line)
                    if obj.get('id') == self._id:
                        return obj.get('result', {})
                except Exception:
                    pass

            return {}
        except Exception as e:
            logger.error(f"Chrome DevTools MCP调用失败: {e}")
            return {}

    def cleanup(self):
        if self.proc:
            try:
                self.proc.terminate()
                logger.info("Chrome DevTools MCP进程已停止")
            except:
                pass

# ==================== 浏览器自动化 ====================
class DouyinBrowserAutomation:
    """抖音浏览器自动化（集成在主文件中）"""
    
    def __init__(self, mcp_url: str = "http://127.0.0.1:12306/mcp"):
        self.mcp_url = mcp_url
        self.session_id = None  # MCP session ID
        self.tool_map: Dict[str, str] = {}  # 逻辑名→实际工具名
        
        # Cookie路径 - 统一使用 media_marketing 目录
        cookies_dir = Path(__file__).parent / "media_marketing" / "cookies"
        cookies_dir.mkdir(parents=True, exist_ok=True)
        self.cookie_file = cookies_dir / "douyin_cookies.json"
        
        # 配置
        self.page_load_timeout = 30
        self.element_timeout = 10
        self.current_tab_id = None
        
    async def human_sleep(self, a: float, b: float):
        """人类化随机等待"""
        await asyncio.sleep(random.uniform(a, b))
        
    async def initialize_session(self):
        """初始化MCP session"""
        if self.session_id:
            return True  # 已初始化

        try:
            # 🔥 绕过VPN代理
            connector = aiohttp.TCPConnector()
            async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
                payload = {
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "DouyinMarketingAgent",
                            "version": "1.0.0"
                        }
                    },
                    "id": 1
                }
                
                # 必须接受 application/json 和 text/event-stream
                headers = {
                    "Accept": "application/json, text/event-stream"
                }
                
                async with session.post(self.mcp_url, json=payload, headers=headers, timeout=10) as resp:
                    # 从响应头获取 session ID
                    self.session_id = resp.headers.get('mcp-session-id')
                    
                    # 响应可能是SSE格式，不解析JSON，只读取文本
                    text = await resp.text()
                    
                    if not self.session_id:
                        logger.error(f"未获取到 session ID，响应: {text[:200]}")
                        raise Exception("未获取到 session ID")
                    
                    logger.info(f"✅ MCP session initialized: {self.session_id[:8]}...")
                    return True
        except Exception as e:
            logger.error(f"MCP session初始化失败: {e}")
            return False
        
    async def call_mcp(self, tool_name: str, args: Dict | None = None) -> Dict:
        """调用MCP工具（自动携带tabId并更新）"""
        import json as json_module  # Type safety: import at function start
        if not self.session_id:
            if not await self.initialize_session():
                raise Exception("MCP session未初始化")
        try:
            # 🔥 绕过VPN代理
            connector = aiohttp.TCPConnector()
            async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
                arguments = args or {}
                # 只有当current_tab_id存在且arguments是字典时才设置tabId
                if isinstance(arguments, dict) and self.current_tab_id:
                    arguments.setdefault("tabId", self.current_tab_id)
                payload = {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments},
                    "id": int(time.time() * 1000)
                }
                headers = {
                    "mcp-session-id": self.session_id,
                    "Accept": "application/json, text/event-stream"
                }
                async with session.post(self.mcp_url, json=payload, headers=headers, timeout=60) as resp:
                    text = await resp.text()
                    try:
                        result = json_module.loads(text)
                        if "error" in result:
                            raise Exception(f"MCP错误: {result['error']}")
                        result_obj = result.get("result", {})
                        # 只有当result_obj是字典且包含tabId时才更新current_tab_id
                        if isinstance(result_obj, dict) and "tabId" in result_obj:
                            self.current_tab_id = result_obj.get("tabId")
                        return result_obj
                    except json_module.JSONDecodeError:
                        import re
                        # 🔥 修复：改进SSE解析，正确处理多行JSON和嵌套对象
                        # 方法1：提取所有data:行，拼接后再解析
                        lines = text.split('\n')
                        data_lines = []
                        for line in lines:
                            if line.startswith('data: '):
                                data_lines.append(line[6:])  # 去掉"data: "前缀

                        if data_lines:
                            # 尝试解析最后一个完整的data块
                            for data_json in reversed(data_lines):
                                try:
                                    last_data = json_module.loads(data_json)
                                    if "error" in last_data:
                                        raise Exception(f"MCP错误: {last_data['error']}")
                                    result_obj = last_data.get("result", {})
                                    # 只有当result_obj是字典且包含tabId时才更新current_tab_id
                                    if isinstance(result_obj, dict) and "tabId" in result_obj:
                                        self.current_tab_id = result_obj.get("tabId")
                                    return result_obj
                                except:
                                    continue
                            logger.error(f"SSE解析失败: 所有data块都无法解析")
                            return {}
                        else:
                            logger.warning(f"MCP响应不是JSON也不是SSE: {text[:100]}")
                            return {}
        except Exception as e:
            error_msg = str(e)
            logger.error(f"MCP调用失败 [{tool_name}]: {error_msg}")

            # 🔥 检测MCP连接断开，立即抛出致命错误停止程序
            if "Cannot connect to host" in error_msg or "拒绝网络连接" in error_msg:
                logger.critical("❌ MCP连接已断开！程序立即停止！")
                raise SystemExit("MCP连接断开，程序终止")

            # 尝试重连一次
            try:
                self.session_id = None
                await self.initialize_session()
            except Exception:
                pass
            raise

    async def list_tools(self) -> List[str]:
        """列出可用工具名称"""
        if not self.session_id:
            if not await self.initialize_session():
                raise Exception("MCP session未初始化")
        try:
            # 🔥 绕过VPN代理
            connector = aiohttp.TCPConnector()
            async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
                payload = {
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "params": {},
                    "id": int(time.time() * 1000)
                }
                headers = {
                    "mcp-session-id": self.session_id,
                    "Accept": "application/json, text/event-stream"
                }
                async with session.post(self.mcp_url, json=payload, headers=headers, timeout=15) as resp:
                    text = await resp.text()
                    try:
                        import json as json_module
                        data = json_module.loads(text)
                        result = data.get("result", {})
                        tools = [t.get("name") for t in result.get("tools", []) if isinstance(t, dict)]
                        return [t for t in tools if t]
                    except Exception:
                        # SSE fallback
                        import re, json as json_module
                        matches = re.findall(r'data: ({.*?})\n', text, re.DOTALL)
                        if matches:
                            try:
                                obj = json_module.loads(matches[-1])
                                result = obj.get("result", {})
                                tools = [t.get("name") for t in result.get("tools", []) if isinstance(t, dict)]
                                return [t for t in tools if t]
                            except Exception:
                                return []
                        return []
        except Exception as e:
            logger.warning(f"获取工具列表失败: {e}")
            return []

    async def resolve_tool(self, logical: str) -> str:
        """解析逻辑名→真实工具名，带缓存与候选名尝试"""
        if logical in self.tool_map:
            return self.tool_map[logical]
        candidates_map = {
            "navigate": ["chrome_navigate", "navigate", "goTo", "goto"],
            "browser_snapshot": ["browser_snapshot", "getSnapshot", "chrome_snapshot", "snapshot"],
            "getWebContent": ["chrome_get_web_content", "getWebContent", "get_web_content", "getActiveTabHtml"],
            "getInteractiveElements": ["chrome_get_interactive_elements", "getInteractiveElements", "get_interactive_elements"],
            "click": ["chrome_click_element", "chrome_click", "click", "clickElement"],
            "scroll": ["chrome_scroll", "scroll"],
            "type": ["chrome_fill_or_select", "chrome_type", "type", "input", "enterText"],
            "keyboard": ["chrome_keyboard", "keyboard", "pressKeys", "keyPress"],
            "setCookie": ["chrome_set_cookie", "setCookie"],
            "closeTab": ["chrome_close_tabs", "closeTab", "closeCurrentTab"],
            "chrome_screenshot": ["chrome_screenshot", "screenshot", "takeScreenshot"],
            # 执行JS代码的工具：不同版本命名不同，全部兼容
            "chrome_eval": [
                "chrome_eval",            # 新版本常用
                "chrome_inject_script",   # 有些版本暴露为inject_script
                "injectScript",
                "evaluateJavascript",
                "evaluateJS",
                "eval"
            ],
        }
        tools = await self.list_tools()
        
        # 🔥 调试：首次映射时打印所有可用工具
        if not self.tool_map and logical in ["navigate", "chrome_snapshot"]:
            logger.info(f"📋 当前可用的MCP工具 ({len(tools)}个):")
            for i, tool in enumerate(tools[:25], 1):
                logger.info(f"   {i}. {tool}")
            if len(tools) > 25:
                logger.info(f"   ... 还有 {len(tools)-25} 个工具")
        
        candidates = candidates_map.get(logical, [logical])
        for name in candidates:
            if name in tools:
                self.tool_map[logical] = name
                logger.info(f"🔧 工具映射: {logical} -> {name}")
                return name
        # 未找到则保底用原名
        self.tool_map[logical] = logical
        logger.warning(f"⚠️ 工具未匹配，回退使用原名: {logical}")
        logger.warning(f"   尝试的候选名: {candidates[:5]}")
        return logical

    async def call_tool(self, logical: str, args: Dict | None = None) -> Dict:
        """按逻辑名调用MCP工具，自动映射到真实工具名"""
        args = args or {}

        # 🔥 工具名映射表（逻辑名 -> MCP真实名）
        tool_name_map = {
            "navigate": "chrome_navigate",
            "getWebContent": "chrome_get_web_content",
            "getInteractiveElements": "chrome_get_interactive_elements",
            "click": "chrome_click_element",
            "type": "chrome_fill_or_select",
            "scroll": "chrome_scroll",
            "keyboard": "chrome_keyboard",
            "setCookie": "chrome_set_cookie",
            "closeTab": "chrome_close_tabs",
            "chrome_screenshot": "chrome_screenshot",
            "chrome_keyboard": "chrome_keyboard",
            "chrome_type": "chrome_fill_or_select",
        }

        # 映射逻辑名到真实工具名
        real_tool_name = tool_name_map.get(logical, logical)

        return await self.call_mcp(real_tool_name, args)
    
    async def open_douyin(self, wait_login: bool = True) -> bool:
        """打开抖音"""
        try:
            # 检查Cookie
            if self.cookie_file.exists() and not wait_login:
                try:
                    cookie_text = self.cookie_file.read_text()
                    cookies = json.loads(cookie_text)
                    if isinstance(cookies, str):
                        logger.warning("Cookie文件格式错误，删除旧文件")
                        self.cookie_file.unlink()
                    else:
                        if isinstance(cookies, list) and self._check_cookies(cookies):
                            return await self._login_with_cookies(cookies)
                except Exception as e:
                    logger.warning(f"读取Cookie失败: {e}，删除旧文件")
                    if self.cookie_file.exists():
                        self.cookie_file.unlink()
            
            # 打开页面
            result = await self.call_tool("navigate", {"url": "https://www.douyin.com/?recommend=1"})
            if isinstance(result, dict):
                self.current_tab_id = result.get("tabId")
            
            # 等待页面初始化
            await self.human_sleep(1.5, 2.5)
            
            logger.info("=" * 60)
            logger.info("💡 已打开抖音（使用当前Chrome登录状态）")
            logger.info("=" * 60)
            await self.human_sleep(2.0, 3.0)
            
            return True
        except Exception as e:
            logger.error(f"打开抖音失败: {e}")
            return False
    
    async def _check_login_status(self) -> bool:
        """检测抖音登录状态 - 通过DOM元素判断"""
        try:
            logger.info("🔍 检测登录状态...")
            
            # 获取页面HTML内容（mcp-chrome没有getCookies工具！）
            result = await self.call_tool("getWebContent", {
                "contentType": "html",
                "selector": "body"
            })
            
            # 解析MCP返回的HTML内容
            import json as json_module
            html_content = ""
            
            if isinstance(result, dict):
                content = result.get("content", [])
                if isinstance(content, list) and len(content) > 0:
                    if isinstance(content[0], dict) and 'text' in content[0]:
                        text_data = content[0]['text']
                        # 可能是JSON字符串，尝试解析
                        try:
                            parsed = json_module.loads(text_data)
                            # MCP返回格式：{"status": "success", "data": "HTML内容"}
                            if isinstance(parsed, dict) and 'data' in parsed:
                                html_content = parsed['data']
                            elif isinstance(parsed, str):
                                html_content = parsed
                            else:
                                html_content = text_data
                        except:
                            html_content = text_data
            elif isinstance(result, str):
                html_content = result
            
            if not html_content:
                logger.warning("⚠️ 未获取到页面内容")
                return False
            
            logger.info(f"✅ 获取到HTML内容，长度: {len(html_content)}")
            logger.info(f"   [调试] HTML前500字符: {html_content[:500]}")
            
            # 检查登录状态标志（DOM元素检测）
            # 已登录标志：用户头像、昵称、"我的"等
            logged_in_indicators = [
                'class="avatar"',  # 头像元素
                'class="user-info"',  # 用户信息
                'data-e2e="user-info"',  # 用户信息（抖音特有）
                '"isLogin":true',  # JS变量
                'class="login-guide-bar__avatar"',  # 登录引导栏的头像
            ]
            
            # 未登录标志："登录"按钮
            logged_out_indicators = [
                '>登录<',
                'class="login-button"',
                'data-e2e="login-button"',
                '"isLogin":false',
            ]
            
            # 统计命中数
            login_score = sum(1 for indicator in logged_in_indicators if indicator in html_content)
            logout_score = sum(1 for indicator in logged_out_indicators if indicator in html_content)
            
            logger.info(f"   [登录检测] 已登录标志命中: {login_score}, 未登录标志命中: {logout_score}")
            
            if login_score > logout_score:
                logger.info("✅ 检测到已登录状态（通过DOM元素）")
                return True
            else:
                logger.warning("⚠️ 未检测到登录状态")
                return False
            
        except Exception as e:
            logger.warning(f"检测登录状态失败: {e}")
            return False
    
    def _check_cookies(self, cookies: List) -> bool:
        """检查Cookie有效性"""
        # 类型检查：必须是列表
        if not isinstance(cookies, list) or not cookies:
            logger.warning(f"Cookie类型错误: {type(cookies)}")
            return False
        
        # 检查列表元素是否是字典
        if not all(isinstance(c, dict) for c in cookies):
            logger.warning("Cookie元素不是字典")
            return False
            
        has_session = any(c.get('name') == 'sessionid' for c in cookies)
        now = datetime.now().timestamp()
        not_expired = all(c.get('expirationDate', now+1) > now for c in cookies)
        return has_session and not_expired
    
    async def _login_with_cookies(self, cookies: List) -> bool:
        """Cookie登录"""
        try:
            await self.call_tool("navigate", {"url": "https://www.douyin.com/?recommend=1"})
            await self.human_sleep(1.5, 2.5)
            
            for cookie in cookies:
                try:
                    await self.call_tool("setCookie", {"cookie": cookie})
                except:
                    pass
            
            await self.call_tool("navigate", {"url": "https://www.douyin.com/?recommend=1"})
            await self.human_sleep(2.5, 3.5)
            logger.info("✅ Cookie登录成功")
            return True
        except:
            return False
    
    async def _save_cookies(self):
        """保存Cookie（注：mcp-chrome没有Cookie工具，此方法已禁用）"""
        logger.warning("⚠️  mcp-chrome不支持Cookie操作，跳过保存")
        return
        
        try:
            # 以下代码已废弃（mcp-chrome没有getCookies工具）
            result = await self.call_mcp("getCookies", {"url": "https://www.douyin.com/?recommend=1"})
            
            # 处理SSE响应（可能包裹在event:message中）
            cookies = []
            if isinstance(result, dict):
                content = result.get("content", [])
                # 如果content是列表且第一个元素是dict，提取text
                if isinstance(content, list) and len(content) > 0:
                    if isinstance(content[0], dict) and 'text' in content[0]:
                        try:
                            cookies = json.loads(content[0]['text'])
                        except:
                            cookies = content
                    else:
                        cookies = content
                else:
                    cookies = content
            
            # 确保cookies是列表
            if not isinstance(cookies, list):
                logger.warning(f"Cookie格式错误: {type(cookies)}")
                return
                
            if cookies:
                self.cookie_file.write_text(json.dumps(cookies, ensure_ascii=False, indent=2))
                logger.info(f"Cookie已保存: {len(cookies)}条")
        except Exception as e:
            logger.error(f"保存Cookie失败: {e}")
    
    async def post_comment(self, video_url: str, comment: str) -> bool:
        """发表评论"""
        try:
            await self.call_tool("navigate", {"url": video_url})
            await self.human_sleep(3.5, 5.5)
            
            # 点击评论框
            await self.call_tool("click", {"selector": "textarea[placeholder*='评论']"})
            await self.human_sleep(0.8, 1.2)
            
            # 输入评论（模拟人类）
            for char in comment:
                await self.call_tool("type", {"text": char})
                await asyncio.sleep(random.uniform(0.05, 0.15))
            
            await self.human_sleep(1.0, 3.0)
            
            # 发送
            await self.call_tool("click", {"selector": "button:has-text('发布')"})
            logger.info(f"✅ 评论成功: {comment[:20]}...")
            return True
        except Exception as e:
            logger.error(f"评论失败: {e}")
            return False
    
    async def get_user_profile_data(self, profile_url: str) -> Dict:
        """访问用户主页并抓取详细信息（通过JS精准抓取）"""
        try:
            logger.info(f"🔍 打开用户主页: {profile_url}")
            
            # 打开主页
            await self.call_tool("navigate", {"url": profile_url})
            await self.human_sleep(2.5, 4.0)
            
            # 滚动加载视频和评论
            logger.info("   滚动加载内容...")
            for i in range(3):  # 滚动3次
                await self.call_tool("chrome_keyboard", {"keys": "PageDown"})
                await self.human_sleep(0.8, 1.3)
            
            # 执行JS抓取用户主页数据（比HTML解析准确100倍！）
            logger.info("   执行JS抓取主页数据...")
            
            js_code = """
            (async () => {
                const profile = {
                    nickname: '',
                    signature: '',
                    cover_url: null,
                    video_titles: [],
                    location: null,
                    comments_about_user: []
                };
                
                // 1. 提取昵称（从title或DOM）
                profile.nickname = document.title.replace('的主页', '').replace('抖音', '').trim();
                if (!profile.nickname || profile.nickname.length < 2) {
                    const nicknameElem = document.querySelector('[data-e2e="user-info-nickname"]') ||
                                        document.querySelector('.nickname') ||
                                        document.querySelector('h1');
                    if (nicknameElem) profile.nickname = nicknameElem.textContent.trim();
                }
                
                // 2. 提取签名/简介
                const signatureElem = document.querySelector('[data-e2e="user-info-signature"]') ||
                                     document.querySelector('.signature') ||
                                     document.querySelector('.user-bio');
                if (signatureElem) profile.signature = signatureElem.textContent.trim();
                
                // 3. 提取头像
                const avatarElem = document.querySelector('[data-e2e="user-info-avatar"]') ||
                                  document.querySelector('.avatar img') ||
                                  document.querySelector('img[src*="avatar"]');
                if (avatarElem) profile.cover_url = avatarElem.src;
                
                // 4. 提取视频标题（前5个）
                const videoItems = document.querySelectorAll('[data-e2e="user-post-item"]');
                for (const item of Array.from(videoItems).slice(0, 5)) {
                    const titleElem = item.querySelector('.desc') ||
                                     item.querySelector('.video-desc') ||
                                     item.querySelector('span[title]');
                    if (titleElem) {
                        const title = titleElem.textContent.trim() || titleElem.getAttribute('title');
                        if (title && title.length > 3) {
                            profile.video_titles.push(title);
                        }
                    }
                }
                
                // 5. 提取评论区称呼（关键！）
                const commentElements = document.querySelectorAll('[data-e2e="comment-item"]');
                const keywords = ['老板', '总', '店长', '馆长', '哥', '姐', '师傅'];
                
                for (const elem of Array.from(commentElements).slice(0, 20)) {
                    const commentText = elem.querySelector('[data-e2e="comment-text"]') ||
                                       elem.querySelector('.comment-text');
                    if (commentText) {
                        const text = commentText.textContent.trim();
                        if (text && keywords.some(kw => text.includes(kw))) {
                            profile.comments_about_user.push(text);
                        }
                    }
                }
                
                // 去重
                profile.comments_about_user = [...new Set(profile.comments_about_user)].slice(0, 10);
                
                return {
                    success: true,
                    profile: profile
                };
            })()
            """


            
            result = await self.call_mcp("chrome_inject_script", {"type": "MAIN", "jsScript": js_code})
            
            # 解析JS执行结果
            profile_data = {
                "nickname": "未知用户",
                "signature": "",
                "cover_url": None,
                "video_titles": [],
                "location": None,
                "comments_about_user": [],
                "profile_url": profile_url
            }
            
            try:
                if isinstance(result, dict):
                    content_list = result.get('content', [])
                    if isinstance(content_list, list) and len(content_list) > 0:
                        text_str = content_list[0].get('text', '{}')
                        data = json.loads(text_str) if isinstance(text_str, str) else text_str
                        if isinstance(data, dict) and 'profile' in data:
                            profile_data.update(data['profile'])
                            profile_data['profile_url'] = profile_url
                
                logger.info(f"   ✅ 通过JS抓取到主页数据")
                
            except Exception as e:
                logger.error(f"   解析JS结果失败: {e}")
            
            # 打印抓取结果
            logger.info(f"   ✅ 昵称: {profile_data['nickname']}")
            logger.info(f"   ✅ 简介: {profile_data['signature'][:30]}..." if profile_data['signature'] else "   ⚠️  无简介")
            logger.info(f"   ✅ 视频数: {len(profile_data['video_titles'])}")
            logger.info(f"   ✅ 评论数: {len(profile_data['comments_about_user'])} 条（含称呼）")
            
            return profile_data
            
        except Exception as e:
            logger.error(f"获取用户主页数据失败: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    async def follow_user(self, profile_url: str) -> bool:
        """关注用户"""
        try:
            logger.info(f"👍 关注用户...")
            
            # 确保在用户主页
            await self.call_tool("navigate", {"url": profile_url})
            await self.human_sleep(1.0, 2.0)
            
            # 尝试点击关注按钮（多种可能的选择器）
            follow_selectors = [
                'button:contains("关注")',
                'div[class*="follow"]',
                'button[class*="follow"]',
                '.follow-button'
            ]
            
            for selector in follow_selectors:
                try:
                    await self.call_tool("click", {"selector": selector})
                    await self.human_sleep(0.6, 1.2)
                    logger.info("   ✅ 关注成功")
                    return True
                except:
                    continue
            
            logger.warning("   ⚠️  未找到关注按钮")
            return False
            
        except Exception as e:
            logger.error(f"关注失败: {e}")
            return False
    
    async def send_private_message(self, profile_url: str, message: str) -> bool:
        """发送私信"""
        try:
            logger.info(f"💬 发送私信...")
            
            # 确保在用户主页
            await self.call_tool("navigate", {"url": profile_url})
            await self.human_sleep(1.0, 2.0)
            
            # 点击私信按钮
            message_selectors = [
                'button:contains("私信")',
                'div[class*="message"]',
                'button[class*="message"]',
                '.message-button'
            ]
            
            clicked = False
            for selector in message_selectors:
                try:
                    await self.call_tool("click", {"selector": selector})
                    await self.human_sleep(1.0, 2.0)
                    clicked = True
                    break
                except:
                    continue
            
            if not clicked:
                logger.warning("   ⚠️  未找到私信按钮")
                return False
            
            # 输入消息
            input_selectors = [
                'textarea',
                'input[type="text"]',
                'div[contenteditable="true"]'
            ]
            
            for selector in input_selectors:
                try:
                    await self.call_tool("type", {
                        "selector": selector,
                        "text": message
                    })
                    await self.human_sleep(0.6, 1.0)
                    
                    # 点击发送
                    send_selectors = ['button:contains("发送")', 'button[class*="send"]']
                    for send_sel in send_selectors:
                        try:
                            await self.call_tool("click", {"selector": send_sel})
                            logger.info("   ✅ 私信已发送")
                            return True
                        except:
                            continue
                except:
                    continue
            
            logger.warning("   ⚠️  私信发送失败")
            return False
        except Exception as e:
            logger.error(f"私信失败: {e}")
            return False


    async def reply_to_comment(self, video_url: str, nickname: str, reply_text: str) -> bool:
        """在指定视频下，回复某个评论者（通过JS精准定位）"""
        try:
            logger.info(f"💬 准备回复 {nickname} 的评论...")
            
            # 打开视频
            await self.call_tool("navigate", {"url": video_url})
            await self.human_sleep(2.0, 3.2)

            # 滚动加载评论
            for _ in range(6):
                await self.call_tool("chrome_keyboard", {"keys": "PageDown"})
                await self.human_sleep(0.8, 1.2)

            # 使用JS精准定位并点击回复按钮
            js_find_reply_button = f"""
            (() => {{
                // 查找所有评论
                const commentElements = document.querySelectorAll('[data-e2e="comment-item"]');
                
                for (const elem of commentElements) {{
                    // 检查昵称是否匹配
                    const nicknameElem = elem.querySelector('[data-e2e="comment-user-nickname"]') ||
                                        elem.querySelector('.nickname');
                    const nickname = nicknameElem?.textContent?.trim();
                    
                    if (nickname === "{nickname}") {{
                        // 找到了目标评论，点击回复按钮
                        const replyBtn = elem.querySelector('[data-e2e="comment-reply"]') ||
                                        elem.querySelector('button:has-text("回复")') ||
                                        elem.querySelector('.reply-button');
                        
                        if (replyBtn) {{
                            replyBtn.click();
                            return {{ success: true, message: '找到并点击了回复按钮' }};
                        }}
                    }}
                }}
                
                return {{ success: false, message: '未找到目标评论或回复按钮' }};
            }})()
            """
            
            result = await self.call_mcp("chrome_inject_script", {"type": "MAIN", "jsScript": js_find_reply_button})
            
            # 解析结果
            success = False
            try:
                if isinstance(result, dict):
                    content_list = result.get('content', [])
                    if isinstance(content_list, list) and len(content_list) > 0:
                        text_str = content_list[0].get('text', '{}')
                        data = json.loads(text_str) if isinstance(text_str, str) else text_str
                        success = data.get('success', False)
            except:
                pass
            
            if not success:
                logger.warning(f"   ⚠️ 未找到 {nickname} 的评论或回复按钮")
                return False
            
            logger.info(f"   ✅ 已定位到 {nickname} 的评论")
            await self.human_sleep(0.8, 1.2)

            # 输入回复文本（MCP的type工具）
            await self.call_tool("chrome_type", {"text": reply_text})
            await self.human_sleep(1.0, 2.0)

            # 点击发送按钮（用JS定位最准确的发送按钮）
            js_click_send = """
            (() => {
                const sendBtn = document.querySelector('[data-e2e="comment-send"]') ||
                               document.querySelector('button:has-text("发送")') ||
                               document.querySelector('button[class*="send"]');
                if (sendBtn) {
                    sendBtn.click();
                    return { success: true };
                }
                return { success: false };
            })()
            """
            
            await self.call_mcp("chrome_inject_script", {"type": "MAIN", "jsScript": js_click_send})
            logger.info(f"   ✅ 回复已发送: {reply_text[:30]}...")
            return True
            
        except Exception as e:
            logger.error(f"回复评论失败: {e}")
            return False

        
    
    async def close_current_tab(self):
        """关闭当前标签页（使用MCP的chrome_close_tabs）"""
        if not self.current_tab_id:
            logger.warning("   无法关闭：当前没有tabId")
            return False
        
        try:
            logger.info(f"🔙 关闭标签页 (tabId: {self.current_tab_id})...")
            # 使用MCP的chrome_close_tabs工具（注意：tabIds是数组！）
            result = await self.call_mcp("chrome_close_tabs", {
                "tabIds": [self.current_tab_id]  # ← 必须是数组！
            })
            logger.info(f"   ✅ 标签页已关闭")
            self.current_tab_id = None  # 清除当前tabId
            return True
        except Exception as e:
            logger.warning(f"   ⚠️ 关闭标签页失败: {e}")
            return False


# ==================== 数据库管理 ====================
class DouyinMarketingDatabase:
    """完整的数据库管理"""
    
    def __init__(self, db_path: str = None):
        if not db_path:
            # 统一使用 media_marketing 目录
            db_dir = Path(__file__).parent / "media_marketing"
            db_dir.mkdir(exist_ok=True)
            db_path = str(db_dir / "douyin_marketing.db")
        
        self.db_path = db_path
        self.init_database()
        logger.info(f"数据库初始化: {db_path}")
    
    def get_conn(self):
        return sqlite3.connect(self.db_path)
    
    def init_database(self):
        """创建所有表"""
        conn = self.get_conn()
        c = conn.cursor()
        
        # 目标账号
        c.execute("""CREATE TABLE IF NOT EXISTS target_accounts (
            id INTEGER PRIMARY KEY,
            douyin_id TEXT UNIQUE,
            nickname TEXT,
            category TEXT,
            priority INTEGER DEFAULT 1,
            last_checked DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        
        # 已评论视频
        c.execute("""CREATE TABLE IF NOT EXISTS commented_videos (
            id INTEGER PRIMARY KEY,
            video_id TEXT UNIQUE,
            video_url TEXT,
            comment_text TEXT,
            commented_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        
        # 已分析用户
        c.execute("""CREATE TABLE IF NOT EXISTS analyzed_users (
            id INTEGER PRIMARY KEY,
            user_id TEXT,
            analyzed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_target BOOLEAN,
            confidence REAL
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_analyzed ON analyzed_users(user_id, analyzed_at)")
        
        # 潜在客户
        c.execute("""CREATE TABLE IF NOT EXISTS potential_clients (
            id INTEGER PRIMARY KEY,
            douyin_id TEXT UNIQUE,
            nickname TEXT,
            confidence REAL,
            venue_type TEXT,
            tags TEXT,
            status TEXT DEFAULT 'discovered',
            messaged BOOLEAN DEFAULT 0,
            messaged_at DATETIME,
            first_found DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        
        # 已私信用户（记录所有私信，包括非客户）
        c.execute("""CREATE TABLE IF NOT EXISTS messaged_users (
            id INTEGER PRIMARY KEY,
            user_id TEXT,
            message_text TEXT,
            messaged_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            account_source TEXT
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_messaged_user ON messaged_users(user_id, messaged_at)")
        
        # 已使用评论
        c.execute("""CREATE TABLE IF NOT EXISTS used_comments (
            id INTEGER PRIMARY KEY,
            comment_text TEXT,
            comment_hash TEXT UNIQUE,
            used_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        
        conn.commit()
        conn.close()
    
    def already_commented(self, video_id: str) -> bool:
        """检查是否已评论"""
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM commented_videos WHERE video_id=?", (video_id,))
        count = c.fetchone()[0]
        conn.close()
        return count > 0
    
    def user_analyzed(self, user_id: str, days: int = 30) -> bool:
        """检查用户是否已分析"""
        conn = self.get_conn()
        c = conn.cursor()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        c.execute("SELECT COUNT(*) FROM analyzed_users WHERE user_id=? AND analyzed_at>?", (user_id, cutoff))
        count = c.fetchone()[0]
        conn.close()
        return count > 0
    
    def is_similar_comment(self, comment: str, threshold: float = 0.8) -> bool:
        """检查相似评论"""
        hash_val = hashlib.md5(comment.encode()).hexdigest()
        conn = self.get_conn()
        c = conn.cursor()
        
        # 完全相同
        c.execute("SELECT COUNT(*) FROM used_comments WHERE comment_hash=?", (hash_val,))
        if c.fetchone()[0] > 0:
            conn.close()
            return True
        
        # 相似度检查
        cutoff = (datetime.now() - timedelta(days=30)).isoformat()
        c.execute("SELECT comment_text FROM used_comments WHERE used_at>?", (cutoff,))
        for (existing,) in c.fetchall():
            if SequenceMatcher(None, comment, existing).ratio() >= threshold:
                conn.close()
                return True
        
        conn.close()
        return False
    
    def save_comment(self, comment: str):
        """保存评论"""
        hash_val = hashlib.md5(comment.encode()).hexdigest()
        conn = self.get_conn()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO used_comments (comment_text, comment_hash) VALUES (?,?)", (comment, hash_val))
            conn.commit()
        except:
            pass
        finally:
            conn.close()
    
    def record_video_comment(self, video_id: str, video_url: str, comment_text: str):
        """记录已评论的视频"""
        conn = self.get_conn()
        c = conn.cursor()
        try:
            c.execute("""INSERT INTO commented_videos (video_id, video_url, comment_text) 
                        VALUES (?,?,?)""", (video_id, video_url, comment_text))
            conn.commit()
            logger.info(f"记录评论：视频{video_id[:8]}...")
        except sqlite3.IntegrityError:
            logger.warning(f"视频{video_id}已评论过，跳过记录")
        except Exception as e:
            logger.warning(f"记录评论失败: {e}")
        finally:
            conn.close()
    
    def already_messaged(self, user_id: str, days: int = 30) -> bool:
        """检查用户是否已私信过（30天内）"""
        conn = self.get_conn()
        c = conn.cursor()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        c.execute("SELECT COUNT(*) FROM messaged_users WHERE user_id=? AND messaged_at>?", 
                 (user_id, cutoff))
        count = c.fetchone()[0]
        conn.close()
        return count > 0
    
    def record_message(self, user_id: str, message_text: str, account_source: str | None = None):
        """记录私信"""
        conn = self.get_conn()
        c = conn.cursor()
        try:
            c.execute("""INSERT INTO messaged_users (user_id, message_text, account_source) 
                        VALUES (?,?,?)""", (user_id, message_text, account_source))
            conn.commit()
            logger.info(f"记录私信：用户{user_id[:8]}...")
        except Exception as e:
            logger.warning(f"记录私信失败: {e}")
        finally:
            conn.close()
    
    def update_account_checked(self, douyin_id: str):
        """更新账号检查时间"""
        conn = self.get_conn()
        c = conn.cursor()
        try:
            c.execute("UPDATE target_accounts SET last_checked=? WHERE douyin_id=?",
                     (datetime.now().isoformat(), douyin_id))
            conn.commit()
        except Exception as e:
            logger.warning(f"更新账号检查时间失败: {e}")
        finally:
            conn.close()
    
    def record_user_analysis(self, user_id: str, is_target: bool, confidence: float):
        """记录用户分析结果"""
        conn = self.get_conn()
        c = conn.cursor()
        try:
            c.execute("""INSERT INTO analyzed_users (user_id, is_target, confidence) 
                        VALUES (?,?,?)""", (user_id, is_target, confidence))
            conn.commit()
        except Exception as e:
            logger.warning(f"记录分析结果失败: {e}")
        finally:
            conn.close()
    
    def save_client(self, data: Dict):
        """保存潜在客户"""
        conn = self.get_conn()
        c = conn.cursor()
        try:
            c.execute("""INSERT INTO potential_clients (douyin_id, nickname, confidence, venue_type, tags)
                        VALUES (?,?,?,?,?)""",
                     (data['douyin_id'], data['nickname'], data['confidence'], 
                      data.get('venue_type'), json.dumps(data.get('tags', []))))
            conn.commit()
            logger.info(f"保存客户: {data['nickname']} (置信度{data['confidence']})")
        except:
            pass
        finally:
            conn.close()
    
    def add_target_account(self, douyin_id: str, nickname: str | None = None, category: str | None = None):
        """添加目标账号"""
        conn = self.get_conn()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO target_accounts (douyin_id, nickname, category) VALUES (?,?,?)",
                     (douyin_id, nickname or f"主播_{douyin_id[:8]}", category))
            conn.commit()
            logger.info(f"添加目标: {nickname or douyin_id[:8]}")
        except:
            logger.warning(f"目标已存在: {douyin_id}")
        finally:
            conn.close()
    
    def batch_import_from_json(self, json_path: str) -> int:
        """批量导入目标账号（从JSON配置文件）"""
        if not Path(json_path).exists():
            logger.error(f"配置文件不存在: {json_path}")
            return 0
        
        try:
            config = json.loads(Path(json_path).read_text(encoding='utf-8'))
            categories = config.get('categories', {})
            
            count = 0
            for category_name, category_data in categories.items():
                accounts = category_data.get('accounts', [])
                priority = category_data.get('priority', 1)
                
                for account in accounts:
                    douyin_id = account.get('douyin_id')
                    nickname = account.get('nickname') or None
                    
                    if douyin_id and len(douyin_id) > 10:
                        self.add_target_account(
                            douyin_id, 
                            nickname=nickname, 
                            category=category_name
                        )
                        count += 1
            
            logger.info(f"✅ 批量导入完成: {count} 个账号")
            return count
            
        except Exception as e:
            logger.error(f"导入失败: {e}")
            return 0
    
    def cleanup_old_data(self, config_path: str | None = None):
        """自动清理过期数据"""
        try:
            # 读取清理规则
            if config_path and Path(config_path).exists():
                config = json.loads(Path(config_path).read_text(encoding='utf-8'))
                rules = config.get('cleanup_rules', {}).get('rules', {})
            else:
                # 默认规则
                rules = {
                    'analyzed_users': {'keep_days': 30},
                    'commented_videos': {'keep_days': 90},
                    'used_comments': {'keep_days': 30}
                }
            
            conn = self.get_conn()
            c = conn.cursor()
            
            # 清理分析过的用户记录
            if 'analyzed_users' in rules:
                days = rules['analyzed_users'].get('keep_days', 30)
                cutoff = (datetime.now() - timedelta(days=days)).isoformat()
                c.execute("DELETE FROM analyzed_users WHERE analyzed_at < ?", (cutoff,))
                deleted_users = c.rowcount
                logger.info(f"清理用户分析记录: {deleted_users} 条（{days}天前）")
            
            # 清理评论记录
            if 'commented_videos' in rules:
                days = rules['commented_videos'].get('keep_days', 90)
                cutoff = (datetime.now() - timedelta(days=days)).isoformat()
                c.execute("DELETE FROM commented_videos WHERE commented_at < ?", (cutoff,))
                deleted_videos = c.rowcount
                logger.info(f"清理评论记录: {deleted_videos} 条（{days}天前）")
            
            # 清理评论文本记录
            if 'used_comments' in rules:
                days = rules['used_comments'].get('keep_days', 30)
                cutoff = (datetime.now() - timedelta(days=days)).isoformat()
                c.execute("DELETE FROM used_comments WHERE used_at < ?", (cutoff,))
                deleted_comments = c.rowcount
                logger.info(f"清理评论文本记录: {deleted_comments} 条（{days}天前）")
            
            conn.commit()
            conn.close()
            
            logger.info("✅ 数据清理完成")
            
        except Exception as e:
            logger.error(f"数据清理失败: {e}")
    
    def get_target_accounts(self, limit: int = 10) -> List[Dict]:
        """获取目标账号"""
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM target_accounts ORDER BY priority DESC, last_checked ASC LIMIT ?", (limit,))
        cols = [d[0] for d in c.description]
        accounts = [dict(zip(cols, row)) for row in c.fetchall()]
        conn.close()
        return accounts



# ==================== AI分析引擎（已移至独立文件） ====================
try:
    # 绝对导入（支持直接运行脚本）
    import sys
    from pathlib import Path
    media_marketing_dir = Path(__file__).parent / "media_marketing"
    if str(media_marketing_dir) not in sys.path:
        sys.path.insert(0, str(media_marketing_dir))

    from ai_engine import AIAnalysisEngine
    from prompts import FALLBACK_COMMENTS, NO_COMMENT_EMOJIS
    logger.info("✅ AI引擎模块加载成功")
except Exception as e:
    logger.warning(f"⚠️  AI引擎模块加载失败: {e}")
    AIAnalysisEngine = None
    FALLBACK_COMMENTS = ["问题不大", "差不多吧", "还好"]
    NO_COMMENT_EMOJIS = ['💆‍♀️', '💆', '👍', '🔥']


# ==================== 主智能体 ====================
class DouyinMarketingAgent:
    """抖音营销智能体 - 超级完整版"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # ==================== 自动清理机制 ====================
        # 启动时自动清理临时文件（可通过config控制）
        auto_cleanup = self.config.get('auto_cleanup', True)
        chrome_keep_days = self.config.get('chrome_keep_days', 0)  # 0=每次启动清空Chrome缓存
        log_keep_days = self.config.get('log_keep_days', 30)  # 保留30天日志
        
        if auto_cleanup:
            try:
                from .media_marketing.cleanup_utils import MediaMarketingCleaner
                cleaner = MediaMarketingCleaner()
                
                logger.info("🧹 启动清理...")
                # 查看清理前大小
                sizes_before = cleaner.get_folder_sizes()
                chrome_before = sizes_before.get('chrome_data', 0)
                
                # 执行清理
                cleaner.run_full_cleanup(
                    chrome_keep_days=chrome_keep_days,
                    log_keep_days=log_keep_days
                )
                
                # 查看清理后大小
                sizes_after = cleaner.get_folder_sizes()
                chrome_after = sizes_after.get('chrome_data', 0)
                
                if chrome_before > 0:
                    logger.info(f"   💾 Chrome缓存: {chrome_before:.2f}MB → {chrome_after:.2f}MB")
            
            except Exception as e:
                logger.warning(f"⚠️  自动清理失败（不影响运行）: {e}")
        # ====================================================
        
        # 初始化组件
        self.mcp_manager = MCPServiceManager()
        self.db = DouyinMarketingDatabase(self.config.get('db_path'))
        self.browser = None
        
        # AI引擎（从system.conf自动加载配置）
        if AIAnalysisEngine is not None and OPENAI_AVAILABLE:
            self.ai = AIAnalysisEngine(config=self.config if self.config else None)
        else:
            self.ai = None
            if not OPENAI_AVAILABLE:
                logger.warning("⚠️  OpenAI SDK未安装，AI功能不可用")
            else:
                logger.warning("⚠️  AI引擎模块加载失败，AI功能不可用")
        
        logger.info(f"抖音营销智能体初始化 - 会话ID: {self.session_id}")
    
    async def random_sleep(self, a: float, b: float):
        """带抖动的人类化等待"""
        await asyncio.sleep(random.uniform(a, b))

    def read_broadcaster_urls(self, max_count: int = 20) -> List[str]:
        """读取主播URL列表（足浴/球房），去重后随机取N个"""
        import random
        
        base_dir = Path(__file__).parent / "media_marketing"
        files = [
            base_dir / "足浴运营主播.txt",
            base_dir / "球房运营主播.txt",
        ]
        urls: List[str] = []
        for f in files:
            if f.exists():
                try:
                    for line in f.read_text(encoding="utf-8").splitlines():
                        u = line.strip()
                        if u and u.startswith("http"):
                            urls.append(u)
                except Exception as e:
                    logger.warning(f"读取文件失败 {f}: {e}")
            else:
                logger.warning(f"未找到主播列表: {f}")
        
        # 去重
        seen = set()
        deduped: List[str] = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                deduped.append(u)
        
        # 如果外部列表为空，使用内置种子（避免任何交互，直接开播主主页）
        if not deduped:
            logger.info("📋 外部列表为空，使用内置种子主播URL（随机）")
            seed_urls = [
                # 示例/占位（可在运行时从页面推荐页随机进入博主）
                "https://www.douyin.com/user/MS4wLjABAAAAxxxxxxxxxxxxxxxxxxxxxxxxxxxx1",
                "https://www.douyin.com/user/MS4wLjABAAAAxxxxxxxxxxxxxxxxxxxxxxxxxxxx2",
                "https://www.douyin.com/user/MS4wLjABAAAAxxxxxxxxxxxxxxxxxxxxxxxxxxxx3",
            ]
            random.shuffle(seed_urls)
            deduped = seed_urls

        # ========== 随机打乱顺序（每次运行都不同）==========
        random.shuffle(deduped)
        logger.info(f"📃 已读取主播URL {len(deduped)} 条，随机打乱后取前 {max_count} 个")
        
        # 取前N个
        return deduped[:max_count]
    
    async def initialize(self) -> bool:
        """初始化（检查MCP服务并打开浏览器）"""
        logger.info("=" * 60)
        logger.info("抖音营销智能体启动中...")
        logger.info("=" * 60)
        
        # 检查MCP服务（你已在 mcp-config.json 配置）
        if not await self.mcp_manager.ensure_mcp_chrome_ready():
            logger.error("❌ MCP chrome 服务未就绪")
            logger.error("请确保执行: npx -y mcp-chrome-bridge")
            return False
        
        # 初始化浏览器自动化
        self.browser = DouyinBrowserAutomation(self.mcp_manager.mcp_url)
        logger.info("✅ 浏览器自动化已初始化")
        
        # 打开抖音（Cookie登录或手动登录）
        cookie_exists = self.browser.cookie_file.exists()
        logger.info(f"Cookie文件: {'存在' if cookie_exists else '不存在'}")
        if not await self.browser.open_douyin(wait_login=not cookie_exists):
            logger.error("❌ 打开抖音失败")
            return False

        logger.info("✅ 智能体初始化完成！")
        return True
    
    async def get_videos_with_time_from_homepage(self, max_videos: int = 10) -> List[Dict]:
        """✅ [MCP截图+deepseek-vl2 OCR] 从主播主页提取：视频链接+是否置顶

        策略：
        1. MCP截图主播主页
        2. deepseek-vl2 OCR识别"置顶"标记
        3. 从HTML提取视频链接
        4. 结合OCR和HTML，标记置顶视频

        Returns:
            List[Dict]: [
                {'video_url': 'xxx', 'video_id': 'xxx', 'is_pinned': False},
                ...
            ]
        """
        try:
            logger.info(f"📝 [OCR方案] 提取主页视频信息（最多{max_videos}个）...")

            # ========== 🔥 步骤0：简单等待页面加载（2-3秒足够） ==========
            logger.info("   ⏳ 等待页面加载...")
            await asyncio.sleep(3)  # 抖音SPA页面3秒基本加载完成

            # ========== 人类化行为：滚动页面 ==========
            logger.info("   📜 滚动主播主页...")
            try:
                await self.browser.call_mcp("chrome_keyboard", {"keys": ["PageDown"]})
                await self.random_sleep(1.5, 2.0)
                await self.browser.call_mcp("chrome_keyboard", {"keys": ["Home"]})
                await self.random_sleep(1.0, 1.5)
            except Exception as e:
                logger.warning(f"   ⚠️ 滚动失败: {e}，继续执行")

            # ========== Step 1: MCP截图主播主页 ==========
            logger.info("   📸 截图主播主页...")
            screenshot_result = await self.browser.call_tool("chrome_screenshot", {
                "tabId": self.browser.current_tab_id,
                "fullPage": False,
                "storeBase64": True,
                "width": 1920,
                "height": 1080
            })

            # 解析截图base64数据
            import json as json_module
            import re
            import base64
            import io
            from PIL import Image


            screenshot_data = None
            if isinstance(screenshot_result, dict):
                if "content" in screenshot_result:
                    content = screenshot_result["content"]
                    if isinstance(content, list) and len(content) > 0:
                        text_item = content[0]
                        if isinstance(text_item, dict) and "text" in text_item:
                            try:
                                # ✅ 直接解析 text 字段，得到 {"base64Data": "...", "mimeType": "..."}
                                data_obj = json_module.loads(text_item["text"])

                                # ✅ 直接提取 base64Data
                                screenshot_data = data_obj.get("base64Data") or data_obj.get("base64")

                                if screenshot_data:
                                    logger.info(f"   ✅ 截图成功提取，base64长度: {len(screenshot_data)}")
                                else:
                                    logger.error(f"   ❌ 数据对象中没有 base64Data 字段: {list(data_obj.keys())}")

                            except json_module.JSONDecodeError as e:
                                logger.error(f"   ❌ JSON解析失败: {e}")
                            except Exception as e:
                                logger.error(f"   ❌ 解析截图异常: {e}")
                                import traceback
                                traceback.print_exc()

            if not screenshot_data:
                logger.error("   ❌ MCP截图失败，无法提取base64数据")
                return []
            
            logger.info(f"   ✅ 截图成功，大小: {len(screenshot_data) // 1024}KB (base64)")
            
            # ========== Step 2: 压缩图片到80KB ==========
            logger.info("   🗜️  压缩图片...")
            try:
                img_bytes = base64.b64decode(screenshot_data)
                img = Image.open(io.BytesIO(img_bytes))
                
                # 降低分辨率
                width, height = img.size
                if width > 1024 or height > 1024:
                    ratio = min(1024/width, 1024/height)
                    new_size = (int(width*ratio), int(height*ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                
                # 压缩为JPEG
                output = io.BytesIO()
                quality = 95
                max_size_kb = 200
                
                while quality > 20:
                    output.seek(0)
                    output.truncate()
                    img.convert('RGB').save(output, format='JPEG', quality=quality, optimize=True)
                    size_kb = len(output.getvalue()) / 1024
                    
                    if size_kb <= max_size_kb:
                        break
                    quality -= 5
                
                compressed_image_b64 = base64.b64encode(output.getvalue()).decode('utf-8')
                logger.info(f"   ✅ 压缩完成: {size_kb:.1f}KB, quality={quality}")

                # 🔥 保存截图到文件供调试查看
                try:
                    debug_dir = Path(__file__).parent / "media_marketing" / "debug_screenshots"
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    screenshot_path = debug_dir / f"ocr_screenshot_{timestamp}.jpg"
                    screenshot_path.write_bytes(output.getvalue())
                    logger.info(f"   💾 截图已保存: {screenshot_path}")
                except Exception as save_error:
                    logger.warning(f"   ⚠️ 保存截图失败(不影响OCR): {save_error}")
                
            except Exception as e:
                logger.error(f"   ❌ 压缩图片失败: {e}，OCR为唯一方法，无法继续")
                return []
            
            # ========== Step 3: 调用deepseek-vl2 OCR识别"置顶"（严格JSON） ==========
            logger.info("   🔍 OCR识别置顶标记（JSON）...")
            ocr_result = await self._call_deepseek_vl2_ocr(compressed_image_b64)
            ocr_videos = []  # [{title,is_pinned,position}]
            if ocr_result.get("success"):
                ocr_content = ocr_result.get("content", "").strip()
                logger.info(f"   ✅ OCR识别成功，内容长度: {len(ocr_content)}")

                # 🔥 调试：打印OCR原始返回
                logger.info(f"   [OCR原始输出] {ocr_content[:500]}...")

                try:
                    # 去除可能的markdown包裹
                    if ocr_content.startswith('```'):
                        import re as _re
                        ocr_content = _re.sub(r'^```(?:json)?\n', '', ocr_content)
                        ocr_content = _re.sub(r'\n```$', '', ocr_content)
                    import json as _json
                    data = _json.loads(ocr_content)
                    ocr_videos = data.get('videos', []) if isinstance(data, dict) else []
                    logger.info(f"   📊 OCR解析视频条目: {len(ocr_videos)}")

                    # 🔥 调试：打印每个视频的置顶状态
                    for idx, v in enumerate(ocr_videos[:5], 1):
                        pinned_mark = "📌置顶" if v.get('is_pinned') else "⚪正常"
                        logger.info(f"      [{idx}] {pinned_mark} | {v.get('title', '')[:20]}")

                except Exception as e:
                    logger.error(f"   ❌ OCR JSON解析失败: {e}")
            else:
                logger.warning(f"   ⚠️  OCR失败: {ocr_result.get('error')}")
            
            # ========== Step 4: 获取HTML并提取视频链接 ==========
            logger.info("   📄 提取HTML视频链接...")
            html_result = await self.browser.call_tool("getWebContent", {
                "selector": "body",
                "htmlContent": True
            })
            
            html_content = ""
            try:
                if isinstance(html_result, dict):
                    content_list = html_result.get('content', [])
                    if isinstance(content_list, list) and len(content_list) > 0:
                        first_item = content_list[0]
                        if isinstance(first_item, dict) and 'text' in first_item:
                            text_json_str = first_item.get('text', '')
                            try:
                                parsed_data = json_module.loads(text_json_str)
                                
                                if isinstance(parsed_data, dict):
                                    if 'htmlContent' in parsed_data:
                                        html_content = parsed_data['htmlContent']
                                    elif 'data' in parsed_data and isinstance(parsed_data['data'], dict):
                                        if 'htmlContent' in parsed_data['data']:
                                            html_content = parsed_data['data']['htmlContent']
                                        elif 'content' in parsed_data['data']:
                                            inner_content = parsed_data['data']['content']
                                            if isinstance(inner_content, list) and len(inner_content) > 0:
                                                if isinstance(inner_content[0], dict) and 'text' in inner_content[0]:
                                                    inner_json = json_module.loads(inner_content[0]['text'])
                                                    if isinstance(inner_json, dict) and 'htmlContent' in inner_json:
                                                        html_content = inner_json['htmlContent']
                            except json_module.JSONDecodeError:
                                logger.warning("   ⚠️  JSON解析失败")
                
                if not isinstance(html_content, str):
                    html_content = str(html_content)

                if not html_content:
                    logger.warning("   ❌ 未提取到HTML内容")
                    return []

                logger.info(f"   ✅ 提取到HTML，长度: {len(html_content)} 字符")
                
                # ========== Step 5: 从HTML提取视频链接 ==========
                videos = []
                
                # 提取所有视频链接
                video_links = re.findall(r'href="(/video/\d+)"', html_content)
                if not video_links:
                    video_links = re.findall(r'href=\\\\"(/video/\d+)\\\\"', html_content)
                
                logger.info(f"   📊 提取到 {len(video_links)} 个视频链接")
                
                # 去重并限制数量
                seen = set()
                for i, video_link in enumerate(video_links):
                    if len(videos) >= max_videos:
                        break
                    
                    vid_match = re.search(r'/video/(\d+)', video_link)
                    if not vid_match:
                        continue
                    
                    video_id = vid_match.group(1)
                    if video_id in seen:
                        continue
                    seen.add(video_id)
                    
                    video_url = f'https://www.douyin.com/video/{video_id}'
                    
                    # ========== Step 6: 使用OCR结果判断是否置顶 ==========
                    # ⚠️ HTML中不包含"置顶"文字，只能靠OCR识别！
                    is_pinned = False

                    if ocr_videos:
                        # 仅由OCR决定置顶（HTML不参与置顶判断）
                        if i < len(ocr_videos):
                            ov = ocr_videos[i]
                            is_pinned = bool(ov.get('is_pinned'))

                    videos.append({
                        'video_url': video_url,
                        'video_id': video_id,
                        'is_pinned': is_pinned
                    })
                    
                    logger.info(f"   {'📌' if is_pinned else '📹'} 视频{i+1}: {video_id[:12]}... {'[置顶]' if is_pinned else ''}")
                
                logger.info(f"   ✅ 成功提取 {len(videos)} 个视频（OCR标记置顶）")
                return videos
                
            except Exception as e:
                logger.error(f"   ❌ 解析HTML失败: {e}")
                import traceback
                traceback.print_exc()
                return []
            
        except Exception as e:
            logger.error(f"   ❌ 提取视频信息失败: {e}")
            import traceback
            traceback.print_exc()
            return []
            
    async def _call_deepseek_vl2_ocr(self, image_base64: str) -> Dict:
        """调用deepseek-vl2 OCR识别图片文字（压缩图片+便宜模型）
        
        Args:
            image_base64: 压缩后的base64图片数据
        
        Returns:
            {"success": True/False, "content": "OCR文本", "error": "错误信息"}
        """
        try:
            # 🔥 直接读取配置文件（绕过config_util，因为VPN环境下导入可能失败）
            project_root = Path(__file__).parent.parent.parent.parent
            config_path = project_root / "system.conf"
            config_dict = {}
            with open(config_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        config_dict[key.strip()] = value.strip()
            
            logger.info(f"   ✅ 直接读取system.conf配置")
            
            # 读取OCR配置（允许环境变量覆盖key/base_url便于快速排查401）
            ocr_model = os.environ.get('DOUYIN_MARKETING_OCR_MODEL') or config_dict.get('douyin_marketing_ocr_model', 'Pro/Qwen/Qwen2.5-VL-7B-Instruct')
            ocr_api_key = os.environ.get('DOUYIN_MARKETING_OCR_API_KEY') or config_dict.get('douyin_marketing_ocr_api_key', '')
            ocr_base_url = os.environ.get('DOUYIN_MARKETING_OCR_BASE_URL') or config_dict.get('douyin_marketing_ocr_base_url', 'https://api.siliconflow.cn/v1')
            ocr_temperature = float(config_dict.get('douyin_marketing_ocr_temperature', '0.1'))
            ocr_max_tokens = int(config_dict.get('douyin_marketing_ocr_max_tokens', '2000'))
            # 关键配置掩码日志（便于核对与单测一致）
            try:
                mk = (ocr_api_key[:4] + '...' + ocr_api_key[-4:]) if isinstance(ocr_api_key, str) and len(ocr_api_key) > 8 else 'N/A'
                logger.info(f"   🧭 OCR配置校验: model={ocr_model}, base_url={ocr_base_url}, key={mk}")
            except Exception:
                pass
            
            prompt = """
你是一个精确的OCR识别助手。请识别抖音主页截图中的视频，并判断是否有"置顶"标签。

【置顶标签的识别规则】
1. **位置**：视频缩略图的左上角
2. **外观**：一个独立的小矩形标签（不是视频封面本身的颜色）
3. **颜色**：黄色或橙色背景
4. **文字**：标签上必须有"置顶"两个清晰的中文字

【⚠️ 严格规则 - 防止误判】
- ❌ 如果只是视频封面本身是黄色/橙色 → 不是置顶
- ❌ 如果看不到"置顶"两个字 → 不是置顶
- ❌ 如果不确定 → 标记为 false
- ✅ 只有同时满足：独立标签 + 黄/橙色 + "置顶"文字 → 才是置顶

【输出格式】严格JSON，按从上到下、从左到右的顺序
{
  "videos": [
    {"title": "视频标题或描述", "is_pinned": false, "position": 1},
    {"title": "视频标题或描述", "is_pinned": false, "position": 2}
  ]
}

【示例】
// 有置顶的情况（能清楚看到左上角的"置顶"标签）
{"videos": [
  {"title": "店铺介绍", "is_pinned": true, "position": 1},
  {"title": "产品展示", "is_pinned": true, "position": 2},
  {"title": "日常", "is_pinned": false, "position": 3}
]}

// 没有置顶的情况（所有视频都没有"置顶"标签）
{"videos": [
  {"title": "视频1", "is_pinned": false, "position": 1},
  {"title": "视频2", "is_pinned": false, "position": 2},
  {"title": "视频3", "is_pinned": false, "position": 3}
]}

【重要提醒】
- 只输出JSON，不要任何其他文字
- 识别至少10个视频（如果页面有的话）
- is_pinned 只能是 true 或 false
- 🔥 如果不确定是否置顶，必须标记为 false（宁可漏掉也不要误判）
- 🔥 大部分主播都没有置顶视频，这是正常的！
"""
            
            payload = {
                "model": ocr_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ],
                "max_tokens": ocr_max_tokens,
                "temperature": ocr_temperature,
                "top_p": 0.7
            }
            
            headers = {
                "Authorization": f"Bearer {ocr_api_key}",
                "Content-Type": "application/json"
            }
            
            # 🔥 创建ClientSession时禁用代理
            connector = aiohttp.TCPConnector()
            async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
                async with session.post(
                    f"{ocr_base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=120)  # 增加到120秒
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                        usage = result.get('usage', {})
                        logger.info(f"   ✅ OCR成功: tokens={usage.get('total_tokens', 0)}, model={ocr_model}")
                        return {"success": True, "content": content}
                    else:
                        error_text = await resp.text()
                        logger.error(f"   ❌ OCR API错误: {resp.status} - {error_text}")
                        return {"success": False, "error": f"API错误: {resp.status}"}
        
        except Exception as e:
            logger.error(f"   ❌ OCR调用失败: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    
    async def run_daily_task(self):
        """每日营销任务（主逻辑）"""
        import re
        import json as json_module
        
        logger.info("🚀 启动每日营销任务...")
        
        stats = {
            'start_time': datetime.now().isoformat(),
            'accounts_processed': 0,
            'comments_posted': 0,
            'users_analyzed': 0,
            'targets_found': 0,
            'success': False
        }
        
        try:
            # ==================== 正确的业务流程 ====================
            # 你的业务：娱乐场所人力资源服务商（足浴/KTV/按摩/台球厅等）
            # 目标：找这些行业的老板、管理者、从业者
            
            # 读取主播列表并逐个处理
            broadcasters = self.read_broadcaster_urls(max_count=20)
            if not broadcasters:
                logger.warning("未读取到主播URL，尝试使用当前页")
                broadcasters = ["https://www.douyin.com/?recommend=1"]

            video_comment_count: Dict[str, int] = {}

            for idx, profile_url in enumerate(broadcasters, start=1):
                logger.info(f"\n{'='*60}")
                logger.info(f"📌 打开主播主页[{idx}/{len(broadcasters)}]: {profile_url}")
                logger.info(f"{'='*60}")

                # ========== 步骤1：打开主播主页 ==========
                nav_result = await self.browser.call_tool("navigate", {"url": profile_url})
                homepage_tab_id = None  # 主播主页的tabId（需要保留）
                
                try:
                    if isinstance(nav_result, dict):
                        if 'tabId' in nav_result:
                            homepage_tab_id = nav_result['tabId']
                        elif 'content' in nav_result and isinstance(nav_result['content'], list):
                            if len(nav_result['content']) > 0:
                                text_str = nav_result['content'][0].get('text', '')
                                import json as json_module
                                parsed1 = json_module.loads(text_str)
                                if 'data' in parsed1 and 'content' in parsed1['data']:
                                    inner_content = parsed1['data']['content']
                                    if isinstance(inner_content, list) and len(inner_content) > 0:
                                        inner_text = inner_content[0].get('text', '')
                                        parsed2 = json_module.loads(inner_text)
                                        homepage_tab_id = parsed2.get('tabId')
                    
                    if homepage_tab_id:
                        self.browser.current_tab_id = homepage_tab_id
                        logger.info(f"   [主播主页tabId] 已保存: {homepage_tab_id}")
                except Exception as e:
                    logger.error(f"   [tabId] 解析失败: {e}")
                
                # ========== 人类化等待（打开主页后） ==========
                await self.random_sleep(2.5, 4.0)

                # ========== 步骤2+3：✅ 从主页一次性提取视频信息（链接+时间+置顶标记） ==========
                all_videos = await self.get_videos_with_time_from_homepage(max_videos=10)
                if not all_videos:
                    logger.warning("该主播主页未找到视频信息，跳过")
                    # 关闭主播主页
                    await self.browser.close_current_tab()
                    await self.random_sleep(0.5, 1.0)
                    continue
                                
                # ========== 过滤视频：跳过置顶，选择前2个非置顶视频 ==========
                videos_to_process = []
                for video in all_videos:
                    # 跳过置顶视频
                    if video.get('is_pinned'):
                        logger.info(f"   📌 跳过置顶视频: {video['video_id']}")
                        continue

                    # 选择前2个非置顶视频
                    if len(videos_to_process) < 2:
                        videos_to_process.append(video)
                        logger.info(f"   ✅ 选中视频: {video['video_id']} (当前{len(videos_to_process)}/2个)")
                    else:
                        logger.info(f"   ⛔ 已满2个，跳过: {video['video_id']}")
                        break  # 已经满了，不再检查
                
                # ========== 步骤4：处理筛选出的视频 ==========
                if not videos_to_process:
                    logger.warning("该主播没有符合条件的视频，关闭主页")
                    # 恢复到主播主页的tabId并关闭
                    self.browser.current_tab_id = homepage_tab_id
                    await self.browser.close_current_tab()
                    await self.random_sleep(0.5, 1.0)
                    continue
                
                logger.info(f"\n{'='*60}")
                logger.info(f"🎯 开始处理 {len(videos_to_process)} 个视频")
                logger.info(f"{'='*60}")
                
                for video_idx, video in enumerate(videos_to_process, start=1):
                    try:
                        video_url = video['video_url']
                        video_id = re.search(r'/video/(\d+)', video_url).group(1) if re.search(r'/video/(\d+)', video_url) else ''
                        
                        logger.info(f"\n{'─'*60}")
                        logger.info(f"🎬 处理视频 [{video_idx}/{len(videos_to_process)}]")
                        logger.info(f"   视频ID: {video_id}")
                        logger.info(f"   发布时间: {video.get('time_text', '未知')}")
                        logger.info(f"{'─'*60}")
                        
                        # ========== 打开视频详情页 ==========
                        logger.info("   📺 打开视频详情页...")
                        nav_result = await self.browser.call_tool("navigate", {"url": video_url})
                        
                        # 保存视频页的tabId
                        video_tab_id = None
                        try:
                            # 🔥 调试：打印navigate返回的原始结果
                            logger.info(f"   [调试] navigate返回类型: {type(nav_result)}")

                            if isinstance(nav_result, dict):
                                # 方法1：直接返回tabId
                                if 'tabId' in nav_result:
                                    video_tab_id = nav_result['tabId']
                                    logger.info(f"   [tabId] 方法1成功: {video_tab_id}")
                                # 方法2：嵌套在content里
                                elif 'content' in nav_result:
                                    text_str = nav_result['content'][0].get('text', '')
                                    import json as json_module
                                    parsed1 = json_module.loads(text_str)
                                    if 'data' in parsed1 and 'content' in parsed1['data']:
                                        inner_text = parsed1['data']['content'][0].get('text', '')
                                        parsed2 = json_module.loads(inner_text)
                                        video_tab_id = parsed2.get('tabId')
                                        logger.info(f"   [tabId] 方法2成功: {video_tab_id}")
                                # 方法3：直接在顶层
                                elif 'data' in nav_result:
                                    video_tab_id = nav_result.get('data', {}).get('tabId')
                                    logger.info(f"   [tabId] 方法3成功: {video_tab_id}")

                            if video_tab_id:
                                self.browser.current_tab_id = video_tab_id
                                logger.info(f"   ✅ 视频tabId已更新: {video_tab_id}")
                            else:
                                logger.warning(f"   ⚠️ 未能解析出tabId，将使用当前tabId: {self.browser.current_tab_id}")
                        except Exception as e:
                            logger.warning(f"   [视频tabId] 解析失败: {e}")
                            logger.warning(f"   将使用当前tabId: {self.browser.current_tab_id}")

                        # ========== 🔥 等待视频详情页加载并滚动加载评论 ==========
                        logger.info("   ⏳ 等待视频详情页加载...")
                        await asyncio.sleep(3)  # 先等3秒基础加载

                        # 滚动页面加载评论区
                        logger.info("   📜 滚动加载评论区...")
                        try:
                            for _ in range(3):  # 滚动3次
                                await self.browser.call_mcp("chrome_keyboard", {"keys": ["PageDown"]})
                                await asyncio.sleep(1.5)
                            # 滚回顶部查看评论
                            await self.browser.call_mcp("chrome_keyboard", {"keys": ["Home"]})
                            await asyncio.sleep(2)
                        except Exception as e:
                            logger.warning(f"   ⚠️ 滚动失败: {e}")

                        logger.info("   ✅ 视频详情页已加载")
                        video_page_loaded = True

                        # ========== 人类化等待（视频详情页加载完成后） ==========
                        await self.random_sleep(1.0, 2.0)

                        # 1. 获取视频评论区（使用独立CommentFetcher）
                        logger.info(f"   📊 开始抓取评论...")

                        # 🔥 调试：先用JS检查DOM结构
                        try:
                            check_dom_js = """
                            (() => {
                                const allDataE2e = new Set();
                                document.querySelectorAll('[data-e2e]').forEach(el => {
                                    allDataE2e.add(el.getAttribute('data-e2e'));
                                });
                                return {
                                    allDataE2eAttrs: Array.from(allDataE2e),
                                    hasCommentItem: !!document.querySelector('[data-e2e="comment-item"]'),
                                    commentRelated: Array.from(allDataE2e).filter(attr => attr.includes('comment'))
                                };
                            })()
                            """
                            dom_result = await self.browser.call_mcp("chrome_inject_script", {"script": check_dom_js})
                            if isinstance(dom_result, dict) and 'content' in dom_result:
                                try:
                                    import json as json_mod
                                    text_str = dom_result['content'][0].get('text', '{}')
                                    dom_info = json_mod.loads(text_str)
                                    logger.info(f"   [调试] DOM检查结果: {dom_info}")
                                except:
                                    pass
                        except Exception as e:
                            logger.warning(f"   [调试] DOM检查失败: {e}")

                        if COMMENT_FETCHER_AVAILABLE and CommentFetcher:
                            fetcher = CommentFetcher(
                                mcp_chrome_url=self.browser.mcp_url,
                                chrome_debug_port=9222
                            )
                            # 传入session和tab（mcp-chrome方案需要）
                            fetcher.session_id = self.browser.session_id
                            fetcher.current_tab_id = self.browser.current_tab_id

                            # 调用get_comments，获取最多500条评论
                            video_comments = await fetcher.get_comments(
                                video_url=video_url,
                                limit=500,
                                method="auto"  # 自动切换：chrome-devtools-mcp -> mcp-chrome
                            )
                            fetcher.cleanup()
                        else:
                            logger.error("❌ CommentFetcher不可用")
                            video_comments = []

                        logger.info(f"   ✅ 评论抓取完成: 共 {len(video_comments)} 条")
                        if video_comments:
                            logger.info(f"      📝 预览前3条评论:")
                            for i, c in enumerate(video_comments[:3], 1):
                                nick = c.get('nickname', 'N/A')[:15]
                                text = c.get('comment_text', 'N/A')[:40]
                                logger.info(f"         [{i}] {nick}: {text}")
                        else:
                            logger.info("   ⚠️ 无评论，执行保底：发布1条基础评论，然后跳过回复与AI分析")
                            # 生成保底评论（优先AI，失败用固定文案）
                            fallback_comment = "路过打个招呼，祝生意兴隆！"
                            try:
                                if self.ai:
                                    gen = await self.ai.generate_comment(
                                        video_info=video,
                                        my_name="亚洲之夜",
                                        video_comments=[]
                                    )
                                    if isinstance(gen, dict):
                                        fallback_comment = str(gen.get('comment') or fallback_comment)
                                    elif isinstance(gen, str) and gen.strip():
                                        fallback_comment = gen.strip()
                            except Exception:
                                pass
                            # 发布一条评论
                            try:
                                if await self.browser.post_comment(video_url, fallback_comment):
                                    video_comment_count[video_id] = 1
                                    stats['comments_posted'] += 1
                                    self.db.save_comment(fallback_comment)
                                    if video_id:
                                        self.db.record_video_comment(video_id, video_url, fallback_comment)
                                    logger.info("   ✅ 保底评论已发布")
                                else:
                                    logger.warning("   ⚠️ 保底评论发布失败")
                            except Exception:
                                logger.warning("   ⚠️ 保底评论流程异常")
                            # 关闭视频页后继续下一个（不做回复/分析）
                            await self.browser.close_current_tab()
                            await self.random_sleep(1, 2)
                            continue

                        # 2. 使用AI引擎生成评论
                        # Type safety: check AI engine
                        if self.ai is None:
                            logger.warning("AI engine not initialized, using fallback comment")
                            comment_text = "Great content, keep it up!"
                        else:
                            comment_text = await self.ai.generate_comment(
                            video_info=video,
                            my_name="亚洲之夜",
                            video_comments=video_comments
                        )

                        # 3. 发表评论（使用原有方法）
                        current_cnt = video_comment_count.get(video_id, 0)
                        if current_cnt < 2:
                            if not self.db.is_similar_comment(comment_text):
                                if await self.browser.post_comment(video_url, comment_text):
                                    video_comment_count[video_id] = current_cnt + 1
                                    stats['comments_posted'] += 1
                                    self.db.save_comment(comment_text)
                                    if video_id:
                                        self.db.record_video_comment(video_id, video_url, comment_text)
                                    logger.info(f"   ✅ 评论成功: {comment_text}")
                                    await self.random_sleep(2.5, 4.0)
                            else:
                                logger.info("   ⚠️ 评论与历史过于相似，跳过本次")
                        else:
                            logger.info("   ⛔ 已达到该视频2条评论上限，跳过评论")

                        # ========== 人类化等待（评论和回复之间） ==========
                        await self.random_sleep(2.0, 3.5)

                        # 4a. 策略2：在评论者的评论下回复（最多3个）
                        for comment in video_comments[:3]:
                            try:
                                nick = comment.get('nickname', '')
                                if not nick:
                                    continue
                                # ✅ 使用回复模式生成评论
                                # Type safety: check AI engine
                                if self.ai is None:
                                    logger.warning("AI engine not initialized, using fallback reply")
                                    reply_text = "Thanks for sharing!"
                                else:
                                    reply_text = await self.ai.generate_comment(
                                    video_info=video,
                                    my_name="亚洲之夜",
                                    is_reply=True,  # 标记为回复模式
                                    target_comment=comment  # 传入要回复的评论
                                )
                                reply_text = f"@{nick} " + reply_text[:80]
                                await self.browser.reply_to_comment(video_url, nick, reply_text)
                                await self.random_sleep(1.5, 2.5)
                            except Exception as e:
                                logger.warning(f"   回复评论失败: {e}")
                                continue
                                        
                        # 4b. 分析评论区用户（深度分析）
                        logger.info(f"\n   🧠 开始AI分析评论用户（前10个）...")
                        analyzed_count = 0
                        high_intent_count = 0
                        medium_intent_count = 0
                        low_intent_count = 0
                        
                        for idx, comment in enumerate(video_comments[:10], 1):
                            try:
                                user = {
                                    'nickname': comment.get('nickname', ''),
                                    'signature': comment.get('signature', ''),
                                    'comment_text': comment.get('comment_text', '')
                                }
                                logger.info(f"   [{idx}/10] 预筛选: {user['nickname'][:15]}...")
                                
                                # Type safety: check AI engine
                                if self.ai is None:
                                    logger.warning("AI engine not initialized, skipping profile check")
                                    should_visit = {"should_visit": False}
                                else:
                                    should_visit = await self.ai.should_visit_profile(user, context={
                                    'video': video,
                                    'account': {'nickname': '主播', 'industry': '娱乐服务'}
                                })
                                
                                if should_visit.get('should_visit'):
                                    logger.info(f"      ✅ 通过初筛，开始深度分析...")
                                    profile_url = comment.get('profile_url', '')
                                    user_id = comment.get('user_id', '')
                                    if profile_url:
                                        profile_data = await self.browser.get_user_profile_data(profile_url)
                                        analyzed_count += 1
                                        stats['users_analyzed'] += 1
                                        
                                        # Type safety: check AI engine
                                        if self.ai is None:
                                            logger.warning("AI engine not initialized, skipping analysis")
                                            analysis = {"is_target": False, "confidence": 0.0, "reason": "AI not available"}
                                        else:
                                            analysis = await self.ai.analyze_user_profile(
                                            user_comment_data=comment,
                                            profile_data=profile_data,
                                            target_category="娱乐行业"
                                        )
                                        
                                        is_target = bool(analysis.get('is_target'))
                                        confidence = float(analysis.get('confidence', 0.0))
                                        reason = analysis.get('reason', '无')
                                        
                                        # 统计意向度
                                        if confidence >= 0.7:
                                            high_intent_count += 1
                                            intent_label = "🔥 高意向"
                                        elif confidence >= 0.4:
                                            medium_intent_count += 1
                                            intent_label = "⚡ 中意向"
                                        else:
                                            low_intent_count += 1
                                            intent_label = "❄️ 低意向"
                                        
                                        logger.info(f"      {intent_label} | 置信度: {confidence:.2f} | 原因: {reason[:30]}")
                                        
                                        if user_id:
                                            self.db.record_user_analysis(user_id, is_target, confidence)
                                        
                                        if is_target and not self.db.already_messaged(user_id or profile_url):
                                            logger.info(f"      💬 准备私信...")
                                            message = (
                                                "老板您好！我们专做娱乐场所人力资源服务（招聘/培训/管理）。"
                                                "若您近期有人才需求或管理升级，欢迎聊聊，我们有成熟方案。"
                                            )
                                            if await self.browser.send_private_message(profile_url, message):
                                                stats['targets_found'] += 1
                                                self.db.record_message(user_id or profile_url, message, account_source=profile_url)
                                                logger.info(f"      ✅ 私信发送成功")
                                                if user_id:
                                                    self.db.save_client({
                                                        'douyin_id': user_id,
                                                        'nickname': user.get('nickname') or profile_data.get('nickname', ''),
                                                        'confidence': confidence,
                                                        'venue_type': None,
                                                        'tags': ['娱乐行业']
                                                    })
                                        else:
                                            logger.info(f"      ⏭️ 跳过私信（低意向或已联系）")
                                else:
                                    logger.info(f"      ⏭️ 未通过初筛，跳过")
                                    
                            except Exception as e:
                                logger.error(f"   ❌ 分析用户失败: {e}")
                                continue
                        
                        # 输出本视频的分析统计
                        logger.info(f"\n   📊 本视频分析统计:")
                        logger.info(f"      - 总评论数: {len(video_comments)}")
                        logger.info(f"      - 深度分析: {analyzed_count} 个用户")
                        logger.info(f"      - 🔥 高意向: {high_intent_count} 个 (≥0.7)")
                        logger.info(f"      - ⚡ 中意向: {medium_intent_count} 个 (0.4-0.7)")
                        logger.info(f"      - ❄️ 低意向: {low_intent_count} 个 (<0.4)")
                        logger.info(f"      - 💬 发送私信: {stats['targets_found']} 个\n")
                                    
                        stats['accounts_processed'] += 1
                        
                        # ========== 处理完成，关闭视频详情页 ==========
                        logger.info(f"   🔙 视频处理完成，关闭视频页...")
                        await self.browser.close_current_tab()
                        await self.random_sleep(1, 2)
                        
                    except Exception as e:
                        logger.error(f"处理视频失败: {e}")
                        # 即使出错也要关闭视频页
                        try:
                            await self.browser.close_current_tab()
                        except:
                            pass
                        continue
                
                # ========== 所有视频处理完成，关闭主播主页 ==========
                logger.info(f"\n✅ 主播 [{idx}/{len(broadcasters)}] 所有视频处理完成，关闭主播主页")
                self.browser.current_tab_id = homepage_tab_id
                await self.browser.close_current_tab()
                await self.random_sleep(1, 2)
            
            stats['end_time'] = datetime.now().isoformat()
            stats['success'] = True
            
            logger.info(f"\n=== 任务完成 ===")
            logger.info(json.dumps(stats, ensure_ascii=False, indent=2))
            return stats
            
        except Exception as e:
            stats['error'] = str(e)
            logger.error(f"任务失败: {e}", exc_info=True)
            return stats
    
    def cleanup(self):
        """清理资源"""
        self.mcp_manager.cleanup()


# ==================== A2A工具接口 ====================
def a2a_tool_douyin_marketing(query: str, **kwargs) -> str:
    """A2A工具接口"""
    import asyncio
    
    try:
        if isinstance(query, str):
            params = json.loads(query) if query.startswith('{') else {"action": "get_stats"}
        else:
            params = query
        
        action = params.get('action', 'run_daily_task')
        
    except Exception as e:
        return json.dumps({"error": f"参数错误: {e}"}, ensure_ascii=False)
    
    # 创建智能体
    agent = DouyinMarketingAgent()
    
    # 执行
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # 初始化
        if not loop.run_until_complete(agent.initialize()):
            return json.dumps({"error": "初始化失败"}, ensure_ascii=False)
        
        # 执行任务
        if action == "run_daily_task":
            result = loop.run_until_complete(agent.run_daily_task())
        else:
            result = {"error": f"未知操作: {action}"}
        
        agent.cleanup()
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    finally:
        loop.close()


# ==================== 命令行启动 ====================
if __name__ == "__main__":
    async def main():
        """主函数 - 一键启动完整系统"""
        print("\n" + "=" * 80)
        print("║" + " " * 78 + "║")
        print("║" + "    🚀 抖音评论区获客智能体 - 自媒体营销自动化系统".center(76) + "║")
        print("║" + " " * 78 + "║")
        print("║" + "    ToB服务商专用 | 娱乐行业获客 | 多平台扩展".center(76) + "║")
        print("║" + " " * 78 + "║")
        print("=" * 80)
        
        # 检查环境
        print("\n📦 环境检查...")
        
        # 确保目录存在
        base_dir = Path(__file__).parent / "media_marketing"
        from utils import util
        logs_dir = Path(util.ensure_log_dir("tools", "douyin_marketing"))
        cookies_dir = base_dir / "cookies"
        
        base_dir.mkdir(exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        cookies_dir.mkdir(exist_ok=True)
        
        print(f"✅ 数据目录: {base_dir}")
        print(f"✅ 日志目录: {logs_dir}")
        print(f"✅ Cookie目录: {cookies_dir}")
        
        # 简化提示
        print("\n💡 智能体将自动启动Chrome（最小化窗口）并加载mcp-chrome扩展")
        
        # 从system.conf加载配置
        try:
            from SmartSisi.utils import config_util as cfg
            cfg.load_config()
            config = {
                'api_key': cfg.douyin_marketing_text_api_key,
                'base_url': cfg.douyin_marketing_text_base_url,
                'text_model': cfg.douyin_marketing_text_model,
                'vision_api_key': cfg.douyin_marketing_vision_api_key,
                'vision_base_url': cfg.douyin_marketing_vision_base_url,
                'vision_model': cfg.douyin_marketing_vision_model,
                'db_path': str(base_dir / "douyin_marketing.db")
            }
            print(f"✅ 配置已从system.conf加载")
        except ImportError as ie:
            # 尝试添加项目根路径
            # 路径: douyin_marketing_agent_tool.py -> tools -> a2a -> llm -> SmartSisi -> liusisi
            project_root = Path(__file__).parent.parent.parent.parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            
            try:
                from SmartSisi.utils import config_util as cfg
                cfg.load_config()
                config = {
                    'api_key': cfg.douyin_marketing_text_api_key,
                    'base_url': cfg.douyin_marketing_text_base_url,
                    'text_model': cfg.douyin_marketing_text_model,
                    'vision_api_key': cfg.douyin_marketing_vision_api_key,
                    'vision_base_url': cfg.douyin_marketing_vision_base_url,
                    'vision_model': cfg.douyin_marketing_vision_model,
                    'db_path': str(base_dir / "douyin_marketing.db")
                }
                print(f"✅ 配置已从system.conf加载（项目根: {project_root}）")
            except Exception as e:
                print(f"❌ 配置加载失败: {e}")
                print(f"   项目根路径: {project_root}")
                print(f"   sys.path: {sys.path[:3]}...")
                raise
        
        agent = DouyinMarketingAgent(config)
        
        # 显示数据库统计
        print("\n📊 数据库统计:")
        conn = agent.db.get_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM target_accounts")
        target_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM potential_clients")
        client_count = c.fetchone()[0]
        conn.close()
        
        print(f"   目标账号: {target_count} 个")
        print(f"   潜在客户: {client_count} 个")
        
        # 自动清理过期数据
        json_config_path = Path(__file__).parent / "media_marketing" / "目标主播配置.json"
        if json_config_path.exists():
            print("\n🗑️  执行数据清理...")
            agent.db.cleanup_old_data(str(json_config_path))
        
        # 如果没有目标账号，批量导入
        if target_count == 0:
            print("\n⚠️  没有目标账号，开始批量导入...")
            
            # 导入JSON配置
            if json_config_path.exists():
                count = agent.db.batch_import_from_json(str(json_config_path))
                print(f"✅ 已导入 {count} 个主播账号")
            else:
                # 手动添加几个测试账号
                agent.db.add_target_account(
                    "MS4wLjABAAAAKAg9TZkPCXyWVSWpcAE6SUnEfvOqbjvu7FH5HoHcqmE",
                    category="测试"
                )
                print("✅ 已添加1个测试账号")
        
        # 初始化（启动MCP和浏览器）
        print("\n🌐 初始化MCP服务和浏览器...")
        if not await agent.initialize():
            print("\n❌ 初始化失败")
            return
        
        # 执行每日任务
        print("\n" + "=" * 80)
        print("▶️  开始执行每日营销任务...")
        print("=" * 80)
        
        result = await agent.run_daily_task()
        
        # 显示结果
        print("\n" + "=" * 80)
        print("📈 任务执行完成！")
        print("=" * 80)
        print(f"✅ 检查账号数: {result.get('accounts_checked', 0)}")
        print(f"✅ 查看视频数: {result.get('videos_viewed', 0)}")
        print(f"✅ 发表评论数: {result.get('comments_posted', 0)}")
        print(f"✅ 分析用户数: {result.get('users_analyzed', 0)}")
        print(f"✅ 发现目标数: {result.get('targets_found', 0)}")
        print("=" * 80)
        
        # 清理
        agent.cleanup()
        
        print("\n程序结束")
    
    # 设置UTF-8编码（Windows兼容）
    if sys.platform == 'win32':
        try:
            import codecs
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
        except:
            pass
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()

