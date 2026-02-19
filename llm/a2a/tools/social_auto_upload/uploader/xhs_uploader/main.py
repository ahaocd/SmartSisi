# -*- coding: utf-8 -*-
"""
小红书智能图片上传器 + 监控系统 - 完整增强版
功能：
1. 自动上传图片（指纹浏览器）
2. 窗口最小化 + 自动关闭
3. 完善错误处理 + 重试机制
4. 私信监控 + 自动回复
5. 关注名单管理
6. 拉黑名单管理
"""
import asyncio
import os
import random
import json
import requests
import traceback
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict

from playwright.async_api import Playwright, async_playwright, TimeoutError as PlaywrightTimeout

# 相对导入修复 - 添加上层目录到 sys.path
current_dir = Path(__file__).parent.resolve()
social_auto_upload_dir = current_dir.parent.parent
sys.path.insert(0, str(social_auto_upload_dir))

from conf import BASE_DIR
from utils.log import xhs_logger
from uploader.xhs_uploader.auto_cover_workflow import generate_png_cover
from uploader.xhs_uploader.llm_title_generator import generate_cover_titles


# ==================== 指纹浏览器API管理 ====================

class FingerprintBrowserAPI:
    """指纹浏览器API（支持AdsPower/比特/MoreLogin/Dolphin/ixBrowser）"""
    
    def __init__(self, browser_type: str = "adspower", api_url: str = "http://local.adspower.net:50325"):
        self.browser_type = browser_type.lower()
        self.api_url = api_url
        
        # 默认API地址
        if not api_url:
            if browser_type == "dolphin":
                self.api_url = "http://localhost:3001"
            elif browser_type == "ixbrowser":
                self.api_url = "http://localhost:39978"
            elif browser_type == "nstbrowser":
                self.api_url = "http://localhost:8848"
    
    def start_bitbrowser_app(self) -> bool:
        """自动启动比特浏览器主程序"""
        try:
            import subprocess
            import time
            import configparser
            
            # 先尝试从配置文件读取路径
            bit_paths = []
            config_file = Path(__file__).parent.parent.parent.parent.parent / "bitbrowser_config.ini"
            if config_file.exists():
                try:
                    config = configparser.ConfigParser()
                    config.read(config_file, encoding='utf-8')
                    custom_path = config.get('BitBrowser', 'exe_path', fallback='').strip()
                    if custom_path and os.path.exists(custom_path):
                        bit_paths.append(custom_path)
                        xhs_logger.info(f"[+] 从配置文件读取路径: {custom_path}")
                except:
                    pass
            
            # 添加默认搜索路径（包含英文和中文文件名）
            bit_paths.extend([
                # 英文名 BitBrowser.exe
                r"C:\Program Files\BitBrowser\BitBrowser.exe",
                r"C:\Program Files (x86)\BitBrowser\BitBrowser.exe",
                r"D:\Program Files\BitBrowser\BitBrowser.exe",
                r"E:\Program Files\BitBrowser\BitBrowser.exe",
                r"D:\BitBrowser\BitBrowser.exe",
                r"E:\BitBrowser\BitBrowser.exe",
                r"C:\Program Files\bitbrowser\BitBrowser.exe",
                r"C:\Program Files (x86)\bitbrowser\BitBrowser.exe",
                r"D:\Program Files\bitbrowser\BitBrowser.exe",
                r"E:\Program Files\bitbrowser\BitBrowser.exe",
                r"D:\bitbrowser\BitBrowser.exe",
                r"E:\bitbrowser\BitBrowser.exe",
                # 中文名 比特浏览器.exe（实际文件名）
                r"C:\Program Files\BitBrowser\比特浏览器.exe",
                r"C:\Program Files (x86)\BitBrowser\比特浏览器.exe",
                r"D:\Program Files\BitBrowser\比特浏览器.exe",
                r"E:\Program Files\BitBrowser\比特浏览器.exe",
                r"D:\BitBrowser\比特浏览器.exe",
                r"E:\BitBrowser\比特浏览器.exe",
                r"C:\Program Files\bitbrowser\比特浏览器.exe",
                r"C:\Program Files (x86)\bitbrowser\比特浏览器.exe",
                r"D:\Program Files\bitbrowser\比特浏览器.exe",  # ✅ 用户的路径
                r"E:\Program Files\bitbrowser\比特浏览器.exe",
                r"D:\bitbrowser\比特浏览器.exe",
                r"E:\bitbrowser\比特浏览器.exe"
            ])
            
            # 检查是否已经在运行（支持中英文进程名）
            xhs_logger.info("[+] 检查比特浏览器进程...")
            result_en = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq BitBrowser.exe'], 
                                     capture_output=True, text=True, encoding='gbk')
            result_cn = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq 比特浏览器.exe'], 
                                     capture_output=True, text=True, encoding='gbk')
            
            if 'BitBrowser.exe' in result_en.stdout or '比特浏览器.exe' in result_cn.stdout:
                xhs_logger.warning("[!] 比特浏览器进程已存在，但API未响应")
                xhs_logger.warning("[!] 可能正在启动中，等待10秒...")
                time.sleep(10)
                return True
            
            # 查找并启动比特浏览器
            xhs_logger.info("[+] 正在搜索比特浏览器...")
            xhs_logger.info(f"[+] 将检查 {len(bit_paths)} 个可能的路径")
            
            for i, path in enumerate(bit_paths, 1):
                xhs_logger.info(f"[{i}/{len(bit_paths)}] 检查: {path}")
                if os.path.exists(path):
                    xhs_logger.success(f"[+] ✅ 找到比特浏览器: {path}")
                    try:
                        subprocess.Popen([path], shell=True)
                        xhs_logger.success("[+] 比特浏览器启动命令已发送！")
                        xhs_logger.info("[+] 等待10秒让浏览器初始化...")
                        time.sleep(10)
                        return True
                    except Exception as e:
                        xhs_logger.error(f"[!] 启动失败: {e}")
                        continue
                else:
                    xhs_logger.warning(f"[!] ❌ 路径不存在")
            
            xhs_logger.error("[!] 未找到比特浏览器安装路径")
            xhs_logger.error("[!] 请手动启动比特浏览器")
            return False
            
        except Exception as e:
            xhs_logger.error(f"[!] 启动比特浏览器失败: {e}")
            return False
    
    def check_browser_running(self, auto_start: bool = True, max_retries: int = 3) -> bool:
        """检查比特浏览器是否正在运行（可自动启动，支持重试）"""
        import time
        
        try:
            if self.browser_type == "bitbrowser":
                # 使用空请求测试API（任何接口都会返回响应，表示API在运行）
                test_url = f"{self.api_url}/browser/list"
                
                # 尝试连接API（重试机制）
                for retry in range(max_retries):
                    try:
                        xhs_logger.info(f"[+] 尝试连接比特浏览器API [{retry+1}/{max_retries}]...")
                        response = requests.post(test_url, json={}, headers={'Content-Type': 'application/json'}, timeout=5)
                        # 只要能连接上就OK（不管返回什么状态码）
                        xhs_logger.success(f"[+] ✅ 比特浏览器API运行正常！(状态码: {response.status_code})")
                        return True
                    except requests.exceptions.ConnectionError:
                        xhs_logger.warning(f"[!] 连接失败，3秒后重试...")
                        time.sleep(3)
                    except Exception as e:
                        xhs_logger.warning(f"[!] 连接异常: {e}")
                        time.sleep(3)
                
                # 所有重试都失败，尝试启动
                xhs_logger.warning("[!] 比特浏览器API未响应")
                if auto_start:
                    xhs_logger.info("[+] 尝试自动启动比特浏览器...")
                    if self.start_bitbrowser_app():
                        # 启动后快速重试连接（最多20次，每次等待2秒）
                        xhs_logger.info("[+] 比特浏览器已启动，正在快速检测API...")
                        for retry in range(20):
                            try:
                                xhs_logger.info(f"[+] 检查API [{retry+1}/20]...")
                                response = requests.post(test_url, json={}, headers={'Content-Type': 'application/json'}, timeout=3)
                                
                                # 只要能连接上就表示API已就绪
                                xhs_logger.success(f"[+] ✅ 比特浏览器API已就绪! (状态码: {response.status_code})")
                                return True
                                
                            except requests.exceptions.ConnectionError:
                                pass  # 静默失败，快速重试
                            except Exception as e:
                                pass  # 静默失败，快速重试
                            time.sleep(2)  # 每次等待2秒
                        
                        xhs_logger.error("[!] 比特浏览器已启动但API仍未就绪")
                        xhs_logger.error("[!] 可能需要更长时间，请稍后手动重试")
                        return False
                return False
                
            return True  # 其他浏览器默认返回True
            
        except Exception as e:
            xhs_logger.error(f"[!] 检查浏览器异常: {e}")
            return False
        
    def start_browser(self, profile_id: str, headless: bool = False) -> dict:
        """
        启动指纹浏览器
        
        Args:
            profile_id: 环境ID
            headless: 是否无头模式（最小化）
            
        Returns:
            dict: {'ws': str, 'debug_port': int, 'success': bool}
        """
        try:
            if self.browser_type == "adspower":
                # AdsPower API
                params = {
                    'user_id': profile_id,
                    'headless': '1' if headless else '0'  # 1=最小化
                }
                url = f"{self.api_url}/api/v1/browser/start"
                response = requests.get(url, params=params, timeout=30)
                data = response.json()
                
                if data['code'] == 0:
                    xhs_logger.success(f"[+] 浏览器启动成功 (最小化={headless})")
                    return {
                        'ws': data['data']['ws']['puppeteer'],
                        'debug_port': data['data']['debug_port'],
                        'success': True
                    }
                else:
                    xhs_logger.error(f"[!] 启动失败: {data['msg']}")
                    return {'success': False, 'error': data['msg']}
                    
            elif self.browser_type == "bitbrowser":
                # 比特浏览器 API
                url = f"{self.api_url}/browser/open"
                params = {
                    'id': profile_id,
                    'headless': headless
                }
                response = requests.post(url, json=params, timeout=30)
                data = response.json()
                
                if data.get('success'):
                    return {
                        'ws': data['data']['ws'],
                        'debug_port': data['data']['http'],
                        'success': True
                    }
                else:
                    return {'success': False, 'error': data.get('msg')}
                    
        except Exception as e:
            xhs_logger.error(f"[!] 启动浏览器异常: {e}")
            return {'success': False, 'error': str(e)}
    
    def close_browser(self, profile_id: str) -> bool:
        """关闭指纹浏览器"""
        try:
            if self.browser_type == "adspower":
                url = f"{self.api_url}/api/v1/browser/stop"
                params = {'user_id': profile_id}
                response = requests.get(url, params=params, timeout=10)
                data = response.json()
                success = data['code'] == 0
                
            elif self.browser_type == "bitbrowser":
                url = f"{self.api_url}/browser/close"
                params = {'id': profile_id}
                response = requests.post(url, json=params, timeout=10)
                data = response.json()
                success = data['success']
            
            if success:
                xhs_logger.success(f"[+] 浏览器已关闭: {profile_id}")
            return success
                
        except Exception as e:
            xhs_logger.error(f"[!] 关闭浏览器失败: {e}")
            return False


# ==================== 元素定位器（统一管理）====================

class XHSElementLocators:
    """小红书页面元素定位器（统一管理，便于维护）"""
    
    # 发布页面
    PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish?from=tab_switch&target=image"  # 直接访问图文页面
    VIDEO_URL = "https://creator.xiaohongshu.com/publish/publish?from=tab_switch&target=video"   # 视频页面
    IMAGE_TAB = 'text=上传图文'              # 图文选项卡（备用）
    IMAGE_INPUT = "input[accept*='image'], input[type='file']"  # 图片上传按钮（更宽松）
    EDITOR_TEXTAREA = "#post-textarea"      # 文本编辑器（旧）
    EDITOR_FALLBACK = "div[contenteditable='true']"  # 文本编辑器（新）
    PUBLISH_BUTTON = 'button:has-text("发布笔记")'
    SCHEDULE_LABEL = "label:has-text('定时发布')"
    DATETIME_INPUT = '.el-input__inner[placeholder="选择日期和时间"]'
    
    # 私信页面
    MESSAGE_URL = "https://creator.xiaohongshu.com/creator-micro/content/message"
    MESSAGE_LIST = ".message-list-item"
    MESSAGE_INPUT = ".message-input-box"
    SEND_BUTTON = 'button:has-text("发送")'
    
    # 关注页面
    FOLLOW_URL = "https://creator.xiaohongshu.com/creator-micro/content/follow"
    FOLLOW_BUTTON = 'button:has-text("关注")'
    UNFOLLOW_BUTTON = 'button:has-text("取消关注")'
    BLOCK_BUTTON = 'button:has-text("拉黑")'


# ==================== 旧版硬编码已删除，统一使用 llm_title_generator.py ====================
# 所有标题、标签、文案生成由 llm_title_generator.py 的 generate_cover_titles() 处理


# ==================== 图片上传器（完善版）====================

class XHSImageUploader:
    """小红书图片上传器 - 完善版"""
    
    def __init__(
        self, 
        title: str,
        image_path: str,
        tags: List[str],
        content: str,
        publish_date: datetime,
        profile_id: str,
        browser_api: FingerprintBrowserAPI,
        theme: str = "情感陪伴类",
        max_retries: int = 1  # 默认不重试，失败直接停止
    ):
        self.title = title
        self.image_path = image_path
        self.tags = tags
        self.content = content
        self.publish_date = publish_date
        self.profile_id = profile_id
        self.browser_api = browser_api
        self.theme = theme
        self.max_retries = max_retries
        self.locators = XHSElementLocators()
    
    async def safe_operation(self, operation, operation_name: str, *args, **kwargs):
        """安全执行操作（失败直接抛异常，不重试）"""
        try:
            result = await operation(*args, **kwargs)
            return result
        except Exception as e:
            xhs_logger.error(f"[!] {operation_name} 失败: {e}")
            raise  # 直接抛出异常，不重试
    
    async def upload_image(self, page):
        """上传图片（多策略更稳健）"""
        xhs_logger.info(f"[+] 上传图片: {os.path.basename(self.image_path)}")
        
        async def _upload():
            # 策略 A：当前页面直传 input[type=file]
            try:
                input_locator = page.locator("input[type='file']").first
                await input_locator.wait_for(state="attached", timeout=5000)
                await input_locator.set_input_files(self.image_path)
                await asyncio.sleep(2)
                xhs_logger.success("[+] 图片上传成功 (input[type=file])")
                return
            except Exception as e:
                xhs_logger.warning(f"[!] 直接定位 input[type=file] 失败: {e}")
            
            # 策略 B：遍历所有 frame 查找 input[type=file]
            try:
                for frame in page.frames:
                    try:
                        locator = frame.locator("input[type='file']").first
                        await locator.wait_for(state="attached", timeout=3000)
                        await locator.set_input_files(self.image_path)
                        await asyncio.sleep(2)
                        xhs_logger.success("[+] 图片上传成功 (frame input[type=file])")
                        return
                    except Exception:
                        continue
            except Exception as e:
                xhs_logger.warning(f"[!] 遍历 frame 上传失败: {e}")
            
            # 策略 C：使用文件选择器（点击可能的上传按钮触发）
            try:
                async with page.expect_file_chooser(timeout=5000) as fc_info:
                    candidates = [
                        'text=上传图片',
                        'text=添加图片',
                        'text=点击上传',
                        'text=选择文件',
                        "[class*='upload']",
                        "button:has-text('上传')"
                    ]
                    clicked = False
                    for sel in candidates:
                        try:
                            await page.locator(sel).first.click(force=True, timeout=1500)
                            clicked = True
                            break
                        except Exception:
                            continue
                    if not clicked:
                        raise RuntimeError("未找到可点击的上传按钮")
                file_chooser = await fc_info.value
                await file_chooser.set_files(self.image_path)
                await asyncio.sleep(2)
                xhs_logger.success("[+] 图片上传成功 (file chooser)")
                return
            except Exception as e:
                xhs_logger.error(f"[!] 触发文件选择器失败: {e}")
            
            raise RuntimeError("未找到可用的图片上传控件")
        
        await self.safe_operation(_upload, "上传图片")
    
    async def fill_content(self, page):
        """填充内容（按元素定位）"""
        xhs_logger.info(f"[+] 填充内容")
        
        async def _fill():
            # 定位编辑器：优先页面内，再遍历 frame，最后用 contenteditable 兜底
            editor = None
            try:
                editor = page.locator(self.locators.EDITOR_TEXTAREA).first
                await editor.wait_for(state="visible", timeout=4000)
            except Exception:
                editor = None
            
            if editor is None or await editor.count() == 0:
                # 尝试 contenteditable 兜底
                try:
                    editor = page.locator(self.locators.EDITOR_FALLBACK).first
                    await editor.wait_for(state="visible", timeout=4000)
                except Exception:
                    editor = None
            
            if editor is None or await editor.count() == 0:
                # 遍历 frames 查找
                for frame in page.frames:
                    try:
                        ed = frame.locator(self.locators.EDITOR_TEXTAREA).first
                        if await ed.count() > 0:
                            await ed.wait_for(state="visible", timeout=3000)
                            editor = ed
                            break
                        ed2 = frame.locator(self.locators.EDITOR_FALLBACK).first
                        if await ed2.count() > 0:
                            await ed2.wait_for(state="visible", timeout=3000)
                            editor = ed2
                            break
                    except Exception:
                        continue
            
            if editor is None or await editor.count() == 0:
                raise RuntimeError("未找到编辑器，无法填充内容")
            
            # 滚动到视口并点击聚焦
            try:
                await editor.scroll_into_view_if_needed()
            except Exception:
                pass
            await asyncio.sleep(0.3)
            await editor.click(force=True, timeout=6000)
            await asyncio.sleep(0.2)
            
            # 清空
            await page.keyboard.press("Control+KeyA")
            await page.keyboard.press("Delete")
            
            # 标题
            await page.keyboard.type(self.title, delay=40)
            await page.keyboard.press("Enter")
            await page.keyboard.press("Enter")
            await asyncio.sleep(random.uniform(0.4, 0.8))
            
            # 正文
            if self.content:
                await page.keyboard.type(self.content, delay=35)
                await page.keyboard.press("Enter")
                await asyncio.sleep(random.uniform(0.4, 0.8))
            
            # 标签（每个标签之间随机延迟2-5秒，模拟人工操作）
            for i, tag in enumerate(self.tags):
                await page.keyboard.type("#" + tag, delay=35)
                await page.keyboard.press("Space")
                if i < len(self.tags) - 1:  # 最后一个标签后不延迟
                    delay = random.uniform(2.0, 5.0)
                    xhs_logger.info(f"[+] 标签 {i+1}/{len(self.tags)} 添加完成，等待 {delay:.1f}秒...")
                    await asyncio.sleep(delay)
            
            xhs_logger.success(f"[+] 添加了 {len(self.tags)} 个标签")
        
        await self.safe_operation(_fill, "填充内容")
    
    async def click_publish(self, page):
        """点击发布（多重兜底+失败截图）"""
        async def _publish():
            if self.publish_date != 0:
                # 定时发布
                await page.locator(self.locators.SCHEDULE_LABEL).click()
                await asyncio.sleep(1)
                
                publish_str = self.publish_date.strftime("%Y-%m-%d %H:%M")
                await page.locator(self.locators.DATETIME_INPUT).click()
                await page.keyboard.press("Control+KeyA")
                await page.keyboard.type(publish_str, delay=50)
                await page.keyboard.press("Enter")
                await asyncio.sleep(1)
            
            # 多种发布按钮选择器（基于实际页面验证）
            publish_button = None
            selectors = [
                'button:has-text("发布")',  # 当前实际文字
                'button:has-text("发 布")',  # 可能有空格
                'button:text("发布")',
                'button:has-text("发布笔记")',  # 旧版
                'button.publish',
                'button.submit',
                'button[type="submit"]',
                '.publish-btn',
                'div.publish-container button',
                'button[class*="publish"]',
            ]
            
            xhs_logger.info(f"[+] 尝试 {len(selectors)} 种发布按钮定位...")
            for i, selector in enumerate(selectors, 1):
                try:
                    xhs_logger.info(f"[{i}/{len(selectors)}] {selector}")
                    btn = page.locator(selector).first
                    count = await btn.count()
                    if count > 0:
                        await btn.wait_for(state="visible", timeout=3000)
                        publish_button = btn
                        xhs_logger.success(f"[+] ✅ 找到: {selector}")
                        break
                except Exception:
                    continue
            
            # 在 frames 中查找
            if publish_button is None:
                xhs_logger.info(f"[+] 主页面未找到，搜索 frames...")
                for frame in page.frames:
                    for selector in selectors[:4]:
                        try:
                            btn = frame.locator(selector).first
                            if await btn.count() > 0:
                                await btn.wait_for(state="visible", timeout=2000)
                                publish_button = btn
                                xhs_logger.success(f"[+] ✅ frame 中找到: {selector}")
                                break
                        except Exception:
                            continue
                    if publish_button:
                        break
            
            if publish_button is None:
                # 失败前截图保存
                from pathlib import Path
                screenshot_path = Path(__file__).parent / f"debug_publish_fail_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                await page.screenshot(path=str(screenshot_path), full_page=True)
                xhs_logger.error(f"[!] 未找到发布按钮！已保存截图: {screenshot_path.name}")
                xhs_logger.error(f"[!] 请把截图发给开发者排查")
                raise RuntimeError(f"未找到发布按钮，截图已保存: {screenshot_path}")
            
            # 滚动到视口并点击
            try:
                await publish_button.scroll_into_view_if_needed()
            except Exception:
                pass
            
            # 点击发布前随机延迟2-5秒，模拟人工确认
            pre_click_delay = random.uniform(2.0, 5.0)
            xhs_logger.info(f"[+] 准备点击发布，等待 {pre_click_delay:.1f}秒...")
            await asyncio.sleep(pre_click_delay)
            
            await publish_button.click(force=True, timeout=8000)
            
            # 发布后停留3-8秒再关闭，模拟人工查看发布结果
            post_publish_delay = random.uniform(3.0, 8.0)
            xhs_logger.success(f"[+] ✅ 发布成功！停留 {post_publish_delay:.1f}秒后关闭...")
            await asyncio.sleep(post_publish_delay)
        
        await self.safe_operation(_publish, "点击发布")
    
    async def upload(self, playwright: Playwright) -> bool:
        """主上传流程（完善错误处理）"""
        browser = None
        
        try:
            # 1. 启动指纹浏览器（最小化窗口）
            xhs_logger.info(f"[+] 启动浏览器: {self.profile_id}")
            browser_info = self.browser_api.start_browser(
                self.profile_id,
                headless=False  # False=显示窗口但最小化，True=完全无头
            )
            
            if not browser_info['success']:
                raise Exception(f"启动失败: {browser_info.get('error')}")
            
            # 2. 连接指纹浏览器
            browser = await playwright.chromium.connect_over_cdp(browser_info['ws'])
            context = browser.contexts[0]
            
            # 等待浏览器完全就绪
            await asyncio.sleep(2)
            
            # 始终新建一个干净页面，关闭其他页面，避免多标签干扰
            page = await context.new_page()
            try:
                for p in list(context.pages):
                    if p is not page:
                        try:
                            await p.close()
                        except Exception:
                            pass
            except Exception:
                pass
            xhs_logger.info(f"[+] 创建新页面并清理其他标签页")
            
            # 3. 直接访问图文发布页面
            xhs_logger.info(f"[+] 访问小红书图文发布页面")
            try:
                await page.goto(self.locators.PUBLISH_URL, timeout=30000, wait_until="domcontentloaded")
                await asyncio.sleep(2)  # 等待页面稳定
                xhs_logger.success(f"[+] ✅ 图文发布页面加载完成")
            except Exception as e:
                xhs_logger.error(f"[!] 页面加载失败: {e}")
                # 重试一次
                xhs_logger.info(f"[+] 重试访问页面...")
                await asyncio.sleep(2)
                await page.goto(self.locators.PUBLISH_URL, timeout=30000, wait_until="domcontentloaded")
                await asyncio.sleep(2)
                xhs_logger.success(f"[+] ✅ 重试成功，页面加载完成")
            
            # 4. 上传图片
            await self.upload_image(page)
            
            # 5. 填充内容
            await self.fill_content(page)
            
            # 6. 发布
            await self.click_publish(page)
            
            xhs_logger.success(f"[+] 环境 [{self.profile_id}] 发布完成")
            return True
            
        except Exception as e:
            xhs_logger.error(f"[!] 上传失败: {e}")
            xhs_logger.error(f"[!] 详细错误: {traceback.format_exc()}")
            return False
            
        finally:
            # ✅ 发布后停留30-120秒，随机滚动，然后关闭浏览器
            try:
                if browser and page:
                    # 随机停留时间：30-120秒
                    browse_time = random.uniform(30, 120)
                    xhs_logger.info(f"[+] 发布完成，停留 {browse_time:.1f} 秒后关闭...")
                    
                    start_time = asyncio.get_event_loop().time()
                    scroll_count = 0
                    
                    # 持续滚动当前页面（发布页面），直到达到停留时间
                    while (asyncio.get_event_loop().time() - start_time) < browse_time:
                        # 随机滚动（向下或向上）
                        direction = random.choice([1, -1])  # 1=向下, -1=向上
                        distance = random.randint(200, 500) * direction
                        await page.mouse.wheel(0, distance)
                        scroll_count += 1
                        
                        # 每次滚动后等待3-8秒
                        await asyncio.sleep(random.uniform(3, 8))
                    
                    xhs_logger.success(f"[+] 停留完成（滚动{scroll_count}次，耗时{browse_time:.1f}秒）")
            except Exception as e:
                xhs_logger.warning(f"[!] 停留操作异常: {e}")
            
            # ✅ 无论如何都关闭浏览器
            try:
                if browser:
                    await browser.close()
                    xhs_logger.info(f"[+] 浏览器已关闭")
            except:
                pass
            
            try:
                self.browser_api.close_browser(self.profile_id)
                xhs_logger.info(f"[+] 环境已关闭: {self.profile_id}")
            except:
                pass
    
    async def main(self):
        async with async_playwright() as playwright:
            return await self.upload(playwright)


# ==================== 私信监控系统 ====================

class XHSMessageMonitor:
    """小红书私信监控 + 自动回复"""
    
    def __init__(
        self,
        profile_id: str,
        browser_api: FingerprintBrowserAPI,
        auto_reply_keywords: Dict[str, str] = None,
        check_interval: int = 60
    ):
        """
        Args:
            profile_id: 环境ID
            browser_api: 浏览器API
            auto_reply_keywords: 自动回复关键词 {'关键词': '回复内容'}
            check_interval: 检查间隔（秒）
        """
        self.profile_id = profile_id
        self.browser_api = browser_api
        self.auto_reply_keywords = auto_reply_keywords or {
            '了解': '您好！感谢关注，详情请看主页置顶~',
            '怎么': '您好！请看主页简介哦~',
            '在吗': '在的！请问有什么可以帮您？'
        }
        self.check_interval = check_interval
        self.locators = XHSElementLocators()
    
    async def check_new_messages(self, page) -> List[Dict]:
        """检查新私信"""
        try:
            await page.goto(self.locators.MESSAGE_URL, timeout=30000)
            await asyncio.sleep(2)
            
            # 获取未读消息列表
            messages = await page.locator(self.locators.MESSAGE_LIST).all()
            new_messages = []
            
            for msg in messages[:10]:  # 只检查前10条
                try:
                    # 检查是否未读
                    is_unread = await msg.locator('.unread-badge').count() > 0
                    if is_unread:
                        text = await msg.inner_text()
                        new_messages.append({
                            'element': msg,
                            'text': text
                        })
                except:
                    continue
            
            return new_messages
            
        except Exception as e:
            xhs_logger.error(f"[!] 检查私信失败: {e}")
            return []
    
    async def auto_reply(self, page, message: Dict):
        """自动回复私信"""
        try:
            message_text = message['text']
            
            # 匹配关键词
            reply_text = None
            for keyword, reply in self.auto_reply_keywords.items():
                if keyword in message_text:
                    reply_text = reply
                    break
            
            if reply_text:
                # 点击消息打开对话
                await message['element'].click()
                await asyncio.sleep(1)
                
                # 输入回复
                await page.locator(self.locators.MESSAGE_INPUT).fill(reply_text)
                await asyncio.sleep(0.5)
                
                # 发送
                await page.locator(self.locators.SEND_BUTTON).click()
                await asyncio.sleep(1)
                
                xhs_logger.success(f"[+] 已自动回复: {reply_text[:20]}...")
                return True
            
            return False
            
        except Exception as e:
            xhs_logger.error(f"[!] 自动回复失败: {e}")
            return False
    
    async def start_monitor(self, playwright: Playwright):
        """启动监控循环"""
        browser = None
        
        try:
            # 启动浏览器
            browser_info = self.browser_api.start_browser(self.profile_id, headless=False)
            if not browser_info['success']:
                raise Exception(f"启动失败")
            
            browser = await playwright.chromium.connect_over_cdp(browser_info['ws'])
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else await context.new_page()
            
            xhs_logger.info(f"[+] 私信监控已启动，间隔 {self.check_interval} 秒")
            
            while True:
                # 检查新消息
                new_messages = await self.check_new_messages(page)
                
                if new_messages:
                    xhs_logger.info(f"[+] 发现 {len(new_messages)} 条新私信")
                    
                    # 自动回复
                    for msg in new_messages:
                        await self.auto_reply(page, msg)
                
                # 等待下次检查
                await asyncio.sleep(self.check_interval)
                
        except Exception as e:
            xhs_logger.error(f"[!] 监控异常: {e}")
        finally:
            if browser:
                await browser.close()
            self.browser_api.close_browser(self.profile_id)


# ==================== 多账号调度系统（完善版）====================

class XHSMultiAccountScheduler:
    """多账号调度器 - 智能体版"""
    
    def __init__(
        self,
        profile_ids: List[str],
        browser_type: str = "adspower",
        api_url: str = "http://local.adspower.net:50325",
        posts_per_day: int = 6,  # ✅ 改为每天最多6条
        interval_minutes: tuple = (30, 50),  # ✅ 改为30-50分钟间隔
        random_delay_range: tuple = (5, 15),
        enable_monitor: bool = False
    ):
        self.profile_ids = profile_ids
        self.browser_api = FingerprintBrowserAPI(browser_type, api_url)
        self.posts_per_day = posts_per_day
        self.interval_minutes = interval_minutes  # 存储分钟范围
        self.random_delay_range = random_delay_range
        self.enable_monitor = enable_monitor
        
        self.schedule_file = Path(BASE_DIR / "db" / "xhs_schedule.json")
        self.schedule_file.parent.mkdir(exist_ok=True, parents=True)
        self.schedule_state = self.load_schedule_state()
        
        # 停止信号文件
        self.stop_signal_file = Path(BASE_DIR / "db" / "xhs_stop.signal")
        self.is_stopped = False
        # 本轮运行中失败的环境（如需登录/异常），跳过之
        self.failed_profiles = set()
    
    def load_schedule_state(self) -> Dict:
        if self.schedule_file.exists():
            with open(self.schedule_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            'last_publish_times': {},
            'daily_count': 0,
            'last_reset_date': datetime.now().strftime('%Y-%m-%d'),
            'total_success': 0,
            'total_fail': 0
        }
    
    def save_schedule_state(self):
        with open(self.schedule_file, 'w', encoding='utf-8') as f:
            json.dump(self.schedule_state, f, ensure_ascii=False, indent=2)
    
    def reset_daily_count_if_needed(self):
        today = datetime.now().strftime('%Y-%m-%d')
        if self.schedule_state['last_reset_date'] != today:
            xhs_logger.info(f"[+] 新的一天，重置计数")
            self.schedule_state['daily_count'] = 0
            self.schedule_state['last_reset_date'] = today
            self.save_schedule_state()
    
    def get_next_profile(self) -> str:
        last_times = self.schedule_state['last_publish_times']
        failed = getattr(self, 'failed_profiles', set())
        # 先选未发布且未标记失败的
        for pid in self.profile_ids:
            if pid in failed:
                continue
            if pid not in last_times:
                return pid
        # 再从未失败的里选最早发布的
        candidates = [pid for pid in self.profile_ids if pid not in failed]
        if not candidates:
            candidates = list(self.profile_ids)
        return sorted(candidates, key=lambda x: last_times.get(x, '1970-01-01 00:00:00'))[0]
    
    def can_publish_now(self, profile_id: str) -> bool:
        last_times = self.schedule_state['last_publish_times']
        if profile_id not in last_times:
            return True
        
        last_time = datetime.strptime(last_times[profile_id], '%Y-%m-%d %H:%M:%S')
        elapsed = datetime.now() - last_time
        # ✅ 使用随机间隔（30-50分钟）
        min_interval = random.randint(self.interval_minutes[0], self.interval_minutes[1])
        return elapsed >= timedelta(minutes=min_interval)
    
    def get_wait_time(self, profile_id: str) -> float:
        last_times = self.schedule_state['last_publish_times']
        if profile_id not in last_times:
            return 0
        
        last_time = datetime.strptime(last_times[profile_id], '%Y-%m-%d %H:%M:%S')
        elapsed = datetime.now() - last_time
        # ✅ 使用随机间隔（30-50分钟）
        min_interval = random.randint(self.interval_minutes[0], self.interval_minutes[1])
        remaining = timedelta(minutes=min_interval) - elapsed
        return remaining.total_seconds() if remaining.total_seconds() > 0 else 0
    
    def add_random_delay(self) -> int:
        min_delay, max_delay = self.random_delay_range
        delay_minutes = random.uniform(min_delay, max_delay)
        delay_seconds = int(delay_minutes * 60)
        xhs_logger.info(f"[+] 随机延迟: {delay_minutes:.1f} 分钟")
        return delay_seconds
    
    def check_stop_signal(self) -> bool:
        """检查停止信号"""
        if self.stop_signal_file.exists():
            xhs_logger.warning("[!] 检测到停止信号，准备停止...")
            self.stop_signal_file.unlink()  # 删除信号文件
            self.is_stopped = True
            return True
        return False
    
    def send_stop_signal(self):
        """发送停止信号"""
        self.stop_signal_file.touch()
        xhs_logger.info("[+] 已发送停止信号")
    
    def update_publish_record(self, profile_id: str, success: bool):
        # ✅ 修复：无论成功失败，都记录时间戳，避免短时间内重复尝试
        self.schedule_state['last_publish_times'][profile_id] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if success:
            self.schedule_state['daily_count'] += 1
            self.schedule_state['total_success'] = self.schedule_state.get('total_success', 0) + 1
        else:
            self.schedule_state['total_fail'] = self.schedule_state.get('total_fail', 0) + 1
        
        self.save_schedule_state()
    
    async def publish_single_post(
        self,
        profile_id: str,
        image_path: str = None,
        title: str = None,
        tags: List[str] = None,
        content: str = None,
        theme: str = "情感陪伴类"
    ) -> bool:
        """发布单个帖子（完善版）"""
        try:
            # 智能生成内容（统一使用 llm_title_generator.generate_cover_titles）
            if not (title and tags and content):
                gen = generate_cover_titles(theme=theme)
                if not title:
                    title = gen.get('main_title', '简单陪伴')
                if not tags:
                    tags = [f"#{w}" for w in ["陪伴","情感","聊天","放轻松","随便聊"]][:6]
                if not content:
                    content = gen.get('body', f"{title}｜你会怎么做？")
            else:
                gen = None

            # 自动生成封面（启用AI背景），使用与内容一致的文案
            if not image_path:
                xhs_logger.info(f"[+] 生成AI封面（约需15-20秒）...")
                main_title_for_cover = (title or (gen.get('main_title') if gen else '温暖陪伴'))[:15]
                subtitle_for_cover = (gen.get('subtitle') if gen else "")
                tagline_for_cover = (gen.get('tagline') if gen else "遇见更好的自己")
                image_path = await generate_png_cover(
                    main_title=main_title_for_cover,
                    subtitle=subtitle_for_cover,
                    tagline=tagline_for_cover,
                    emoji="💖",
                    use_ai_bg=True
                )
            
            xhs_logger.info(f"[+] 标题: {title}")
            xhs_logger.info(f"[+] 标签: {', '.join(tags)}")
            
            # 随机延迟（改为10-30秒，更快测试）
            delay_seconds = random.uniform(10, 30)
            xhs_logger.info(f"[+] 随机延迟: {delay_seconds:.1f} 秒")
            await asyncio.sleep(delay_seconds)
            
            # 上传
            uploader = XHSImageUploader(
                title=title,
                image_path=image_path,
                tags=tags,
                content=content,
                publish_date=0,
                profile_id=profile_id,
                browser_api=self.browser_api,
                theme=theme,
                max_retries=1  # 失败不重试
            )
            
            xhs_logger.info(f"[+] 环境 [{profile_id}] 开始发布")
            success = await uploader.main()
            
            # 更新记录
            self.update_publish_record(profile_id, success)
            
            if success:
                xhs_logger.success(f"[+] 环境 [{profile_id}] 发布成功！")
            else:
                xhs_logger.error(f"[!] 环境 [{profile_id}] 发布失败")
            
            return success
            
        except Exception as e:
            xhs_logger.error(f"[!] 发布异常: {e}")
            self.update_publish_record(profile_id, False)
            return False
    
    async def schedule_publish(self, post_queue: List[Dict], auto_loop: bool = False):
        """调度发布（智能体版 - 支持停止信号）"""
        
        # ✅ 启动前检查比特浏览器
        xhs_logger.info("🔍 检查比特浏览器状态...")
        if not self.browser_api.check_browser_running():
            xhs_logger.error("❌ 比特浏览器未运行！请先启动比特浏览器")
            xhs_logger.error("💡 启动后再次运行此脚本")
            return
        
        xhs_logger.info("="*60)
        xhs_logger.info("🚀 小红书智能调度器启动")
        xhs_logger.info("="*60)
        xhs_logger.info(f"环境数: {len(self.profile_ids)}")
        xhs_logger.info(f"浏览器: {self.browser_api.browser_type.upper()}")
        xhs_logger.info(f"每日目标: {self.posts_per_day} 个")
        xhs_logger.info(f"间隔: {self.interval_minutes[0]}-{self.interval_minutes[1]} 分钟（随机）")
        xhs_logger.info(f"发布时段: 24小时全天（不限制）")
        xhs_logger.info(f"自动循环: {'是' if auto_loop else '否'}")
        xhs_logger.info(f"历史成功: {self.schedule_state.get('total_success', 0)}")
        xhs_logger.info(f"历史失败: {self.schedule_state.get('total_fail', 0)}")
        xhs_logger.info("="*60)
        xhs_logger.info("💡 发送停止信号: 创建文件 db/xhs_stop.signal")
        xhs_logger.info("="*60)
        
        post_index = 0
        
        while True:
            # 检查停止信号
            if self.check_stop_signal():
                xhs_logger.success("[+] 已收到停止信号，调度器已停止")
                break
            
            self.reset_daily_count_if_needed()
            
            if self.schedule_state['daily_count'] >= self.posts_per_day:
                if not auto_loop:
                    xhs_logger.success(f"[+] 今日任务完成！")
                    break
                else:
                    now = datetime.now()
                    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0)
                    wait_seconds = (tomorrow - now).total_seconds()
                    xhs_logger.info(f"[+] 等待明天，剩余 {wait_seconds/3600:.1f} 小时")
                    
                    # 在等待期间也检查停止信号（每分钟检查一次）
                    for _ in range(int(wait_seconds / 60)):
                        if self.check_stop_signal():
                            xhs_logger.success("[+] 已收到停止信号，调度器已停止")
                            return
                        await asyncio.sleep(60)
                    continue
            
            if post_index >= len(post_queue):
                if auto_loop:
                    post_index = 0
                else:
                    break
            
            profile_id = self.get_next_profile()
            
            if not self.can_publish_now(profile_id):
                wait_time = self.get_wait_time(profile_id)
                xhs_logger.info(f"[+] 等待 {wait_time/60:.1f} 分钟")
                
                # 在等待期间也检查停止信号（每10秒检查一次）
                for _ in range(int(wait_time / 10)):
                    if self.check_stop_signal():
                        xhs_logger.success("[+] 已收到停止信号，调度器已停止")
                        return
                    await asyncio.sleep(10)
            
            post_info = post_queue[post_index]
            
            try:
                success = await self.publish_single_post(
                    profile_id=profile_id,
                    image_path=post_info.get('image_path'),
                    title=post_info.get('title'),
                    tags=post_info.get('tags'),
                    content=post_info.get('content'),
                    theme=post_info.get('theme', '情感陪伴类')
                )
                
                if success:
                    post_index += 1
                    xhs_logger.info(f"[+] 进度: {self.schedule_state['daily_count']}/{self.posts_per_day}")
                else:
                    # 标记该环境失败（可能需登录/异常），本轮跳过，继续下一个
                    self.failed_profiles.add(profile_id)
                    xhs_logger.error(f"[!] 环境 {profile_id} 发布失败，跳过该环境")
                    # 如果所有环境都失败，才停止
                    if len(self.failed_profiles) >= len(self.profile_ids):
                        xhs_logger.error(f"[!] 所有环境均失败，调度器停止")
                        break
                    
            except Exception as e:
                # 任何异常直接停止
                xhs_logger.error(f"[!] 发布异常: {e}")
                # 标记失败并尝试下一个
                self.failed_profiles.add(profile_id)
                if len(self.failed_profiles) >= len(self.profile_ids):
                    xhs_logger.error(f"[!] 所有环境均异常，调度器停止")
                    raise
            
            if post_index < len(post_queue):
                await asyncio.sleep(random.randint(10, 30))


# ==================== 统一对外接口 ====================

async def quick_publish_xhs(
    profile_ids: List[str],
    browser_type: str = "adspower",
    api_url: str = "http://local.adspower.net:50325",
    theme: str = "情感陪伴类",
    interval_minutes: tuple = (30, 50),  # ✅ 改为分钟间隔
    posts_per_day: int = 6,  # ✅ 改为每天6条
    auto_loop: bool = False  # 默认不循环，智能体版本
):
    """快速发布接口（智能体版 - 支持停止）"""
    scheduler = XHSMultiAccountScheduler(
        profile_ids=profile_ids,
        browser_type=browser_type,
        api_url=api_url,
        posts_per_day=posts_per_day,
        interval_minutes=interval_minutes  # ✅ 使用分钟间隔
    )
    
    post_queue = [{'theme': theme} for _ in range(posts_per_day)]
    await scheduler.schedule_publish(post_queue, auto_loop=auto_loop)


def stop_xhs_scheduler():
    """停止调度器（智能体调用）"""
    stop_file = Path(BASE_DIR / "db" / "xhs_stop.signal")
    stop_file.parent.mkdir(exist_ok=True, parents=True)
    stop_file.touch()
    xhs_logger.info("[+] 已发送停止信号到调度器")
    return {"success": True, "message": "停止信号已发送"}


def get_xhs_status():
    """获取调度器状态（智能体调用）"""
    schedule_file = Path(BASE_DIR / "db" / "xhs_schedule.json")
    if schedule_file.exists():
        with open(schedule_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
        return {
            "success": True,
            "daily_count": state.get('daily_count', 0),
            "total_success": state.get('total_success', 0),
            "total_fail": state.get('total_fail', 0),
            "last_publish_times": state.get('last_publish_times', {})
        }
    return {"success": False, "message": "未找到状态文件"}


# ==================== 示例用法 ====================

if __name__ == "__main__":
    # ✅ 使用实际配置（从xiaohongshu_auto_upload_tool.py同步）
    profile_ids = [
        "6f60ef87c8744b9caf8c6d9a12f50732",  # XIAOHONGSHU3
        "ab3974b9e3094d7fa3db31afab24b40a",  # XIAOHONGSHU2
        "9d8cb03a23144c0c82b4ce82d9fa398f"   # xiaohongshu1
    ]
    
    # 发布模式
    asyncio.run(quick_publish_xhs(
        profile_ids=profile_ids,
        browser_type="bitbrowser",  # ✅ 比特浏览器
        api_url="http://127.0.0.1:54345",  # ✅ 比特浏览器API地址
        theme="情感陪伴类",
        interval_minutes=(30, 50),  # ✅ 30-50分钟随机间隔
        posts_per_day=6  # ✅ 每天最多6条
    ))
