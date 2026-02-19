#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
抖音下载器 - 统一增强版
支持视频、图文、用户主页、合集等多种内容的批量下载
"""

# 🔥 Windows UTF-8 编码修复（必须在所有导入之前）
import sys
import os

# 强制设置stdout/stderr为UTF-8编码（修复emoji显示和GBK编码错误）
if os.name == 'nt':  # Windows系统
    os.system('chcp 65001 >nul 2>&1')
    import codecs
    # 检查是否有buffer属性（避免重复包装）
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# 首先禁用所有HTTP代理（必须在import其他模块之前）
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'
if 'HTTP_PROXY' in os.environ:
    del os.environ['HTTP_PROXY']
if 'HTTPS_PROXY' in os.environ:
    del os.environ['HTTPS_PROXY']
if 'http_proxy' in os.environ:
    del os.environ['http_proxy']
if 'https_proxy' in os.environ:
    del os.environ['https_proxy']

import asyncio
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse
import argparse
import yaml
try:
    from utils import util
except Exception:
    util = None

# 第三方库
try:
    import aiohttp
    import requests
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
    from rich.table import Table
    from rich.panel import Panel
    from rich.live import Live
    from rich import print as rprint
except ImportError as e:
    print(f"请安装必要的依赖: pip install aiohttp requests rich pyyaml")
    sys.exit(1)

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入项目模块
from apiproxy.douyin import douyin_headers
from apiproxy.douyin.urls import Urls
from apiproxy.douyin.result import Result
from apiproxy.common.utils import Utils
from apiproxy.douyin.auth.cookie_manager import AutoCookieManager
from apiproxy.douyin.database import DataBase

# 配置日志 - 统一日志目录（优先 SmartSisi/logs）
_current_dir = Path(__file__).resolve().parent
try:
    if util:
        _log_dir = Path(util.ensure_log_dir("tools", "tiktok_batch"))
        _log_file = _log_dir / "douyin_downloader.log"
    else:
        _log_file = _current_dir / "downloader.log"
except Exception:
    _log_file = _current_dir / "downloader.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(str(_log_file), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Rich console
console = Console()


class ContentType:
    """内容类型枚举"""
    VIDEO = "video"
    IMAGE = "image" 
    USER = "user"
    MIX = "mix"
    MUSIC = "music"
    LIVE = "live"


class DownloadStats:
    """下载统计"""
    def __init__(self):
        self.total = 0
        self.success = 0
        self.failed = 0
        self.skipped = 0
        self.start_time = time.time()
    
    @property
    def success_rate(self):
        return (self.success / self.total * 100) if self.total > 0 else 0
    
    @property
    def elapsed_time(self):
        return time.time() - self.start_time
    
    def to_dict(self):
        return {
            'total': self.total,
            'success': self.success,
            'failed': self.failed,
            'skipped': self.skipped,
            'success_rate': f"{self.success_rate:.1f}%",
            'elapsed_time': f"{self.elapsed_time:.1f}s"
        }


class RateLimiter:
    """速率限制器 - 随机2-8秒间隔（模拟真人行为）"""
    def __init__(self, min_interval: float = 2.0, max_interval: float = 8.0):
        self.min_interval = min_interval  # 最小间隔2秒
        self.max_interval = max_interval  # 最大间隔8秒
        self.last_request = 0
    
    async def acquire(self):
        """获取许可 - 使用随机间隔"""
        import random
        
        current = time.time()
        time_since_last = current - self.last_request
        
        # 生成随机间隔时间（2-8秒）
        random_interval = random.uniform(self.min_interval, self.max_interval)
        
        if time_since_last < random_interval:
            wait_time = random_interval - time_since_last
            logger.debug(f"⏱️ 等待 {wait_time:.1f} 秒后继续...")
            await asyncio.sleep(wait_time)
        
        self.last_request = time.time()


class RetryManager:
    """重试管理器"""
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.retry_delays = [1, 2, 5]  # 重试延迟
    
    async def execute_with_retry(self, func, *args, **kwargs):
        """执行函数并自动重试"""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delays[min(attempt, len(self.retry_delays) - 1)]
                    logger.warning(f"第 {attempt + 1} 次尝试失败: {e}, {delay}秒后重试...")
                    await asyncio.sleep(delay)
        raise last_error


class UnifiedDownloader:
    """统一下载器"""
    
    def __init__(self, config_path: str = "config.yml"):
        self.config = self._load_config(config_path)
        self.urls_helper = Urls()
        self.result_helper = Result()
        self.utils = Utils()
        
        # 组件初始化
        self.stats = DownloadStats()
        self.rate_limiter = RateLimiter(min_interval=2.0)  # 使用正确的参数名
        self.retry_manager = RetryManager(max_retries=self.config.get('retry_times', 3))
        
        # Cookie与请求头（延迟初始化，支持自动获取）
        self.cookies = self.config.get('cookies') if 'cookies' in self.config else self.config.get('cookie')
        self.auto_cookie = bool(self.config.get('auto_cookie')) or (isinstance(self.config.get('cookie'), str) and self.config.get('cookie') == 'auto') or (isinstance(self.config.get('cookies'), str) and self.config.get('cookies') == 'auto')
        self.headers = {**douyin_headers}
        # 避免服务端使用brotli导致aiohttp无法解压（未安装brotli库时会出现空响应）
        self.headers['accept-encoding'] = 'gzip, deflate'
        # 增量下载与数据库
        self.increase_cfg: Dict[str, Any] = self.config.get('increase', {}) or {}
        self.enable_database: bool = bool(self.config.get('database', True))
        self.db: Optional[DataBase] = DataBase() if self.enable_database else None
        
        # 保存路径 - 修复：相对路径转为绝对路径（基于douyin-downloader目录）
        path_config = self.config.get('path', './Downloaded')
        self.save_path = Path(path_config)
        if not self.save_path.is_absolute():
            # 如果是相对路径，转换为基于douyin-downloader目录的绝对路径
            downloader_dir = Path(__file__).resolve().parent
            self.save_path = (downloader_dir / self.save_path).resolve()
        self.save_path.mkdir(parents=True, exist_ok=True)
        
    def _load_config(self, config_path: str) -> Dict:
        """加载配置文件"""
        if not os.path.exists(config_path):
            # 兼容配置文件命名：优先 config.yml，其次 config_simple.yml
            alt_path = 'config_simple.yml'
            if os.path.exists(alt_path):
                config_path = alt_path
            else:
                # 返回一个空配置，由命令行参数决定
                return {}
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 简化配置兼容：links/link, output_dir/path, cookie/cookies
        if 'links' in config and 'link' not in config:
            config['link'] = config['links']
        if 'output_dir' in config and 'path' not in config:
            config['path'] = config['output_dir']
        if 'cookie' in config and 'cookies' not in config:
            config['cookies'] = config['cookie']
        if isinstance(config.get('cookies'), str) and config.get('cookies') == 'auto':
            config['auto_cookie'] = True
        
        # 允许无 link（通过命令行传入）
        # 如果两者都没有，后续会在运行时提示
        
        return config
    
    def _build_cookie_string(self) -> str:
        """构建Cookie字符串"""
        if isinstance(self.cookies, str):
            return self.cookies
        elif isinstance(self.cookies, dict):
            return '; '.join([f'{k}={v}' for k, v in self.cookies.items()])
        elif isinstance(self.cookies, list):
            # 支持来自AutoCookieManager的cookies列表
            try:
                kv = {c.get('name'): c.get('value') for c in self.cookies if c.get('name') and c.get('value')}
                return '; '.join([f'{k}={v}' for k, v in kv.items()])
            except Exception:
                return ''
        return ''

    async def _initialize_cookies_and_headers(self):
        """初始化Cookie与请求头（支持自动获取）"""
        # 若配置为字符串 'auto'，视为未提供，触发自动获取
        if isinstance(self.cookies, str) and self.cookies.strip().lower() == 'auto':
            self.cookies = None
        
        # 若已显式提供cookies，则直接使用
        cookie_str = self._build_cookie_string()
        if cookie_str:
            self.headers['Cookie'] = cookie_str
            # 同时设置到全局 douyin_headers，确保所有 API 请求都能使用
            from apiproxy.douyin import douyin_headers
            douyin_headers['Cookie'] = cookie_str
            return
        
        # 自动获取Cookie
        if self.auto_cookie:
            try:
                console.print("[cyan]🔐 正在自动获取Cookie...[/cyan]")
                # 使用绝对路径保存Cookie到douyin-downloader目录
                import os
                cookie_path = os.path.join(os.path.dirname(__file__), 'cookies.pkl')
                async with AutoCookieManager(cookie_file=cookie_path, headless=False) as cm:
                    cookies_list = await cm.get_cookies()
                    if cookies_list:
                        self.cookies = cookies_list
                        cookie_str = self._build_cookie_string()
                        if cookie_str:
                            self.headers['Cookie'] = cookie_str
                            # 同时设置到全局 douyin_headers，确保所有 API 请求都能使用
                            from apiproxy.douyin import douyin_headers
                            douyin_headers['Cookie'] = cookie_str
                            console.print("[green]✅ Cookie获取成功[/green]")
                            return
                console.print("[yellow]⚠️ 自动获取Cookie失败或为空，继续尝试无Cookie模式[/yellow]")
            except Exception as e:
                logger.warning(f"自动获取Cookie失败: {e}")
                console.print("[yellow]⚠️ 自动获取Cookie失败，继续尝试无Cookie模式[/yellow]")
        
        # 未能获取Cookie则不设置，使用默认headers
    
    def detect_content_type(self, url: str) -> ContentType:
        """检测URL内容类型"""
        if '/user/' in url:
            return ContentType.USER
        elif '/video/' in url or 'v.douyin.com' in url:
            return ContentType.VIDEO
        elif '/note/' in url:
            return ContentType.IMAGE
        elif '/collection/' in url or '/mix/' in url:
            return ContentType.MIX
        elif '/music/' in url:
            return ContentType.MUSIC
        elif 'live.douyin.com' in url:
            return ContentType.LIVE
        else:
            return ContentType.VIDEO  # 默认当作视频
    
    async def resolve_short_url(self, url: str) -> str:
        """解析短链接"""
        if 'v.douyin.com' in url:
            try:
                # 使用同步请求获取重定向
                response = requests.get(url, headers=self.headers, allow_redirects=True, timeout=10, proxies={'http': None, 'https': None})
                final_url = response.url
                logger.info(f"解析短链接: {url} -> {final_url}")
                return final_url
            except Exception as e:
                logger.warning(f"解析短链接失败: {e}")
        return url
    
    def extract_id_from_url(self, url: str, content_type: ContentType = None) -> Optional[str]:
        """从URL提取ID
        
        Args:
            url: 要解析的URL
            content_type: 内容类型（可选，用于指导提取）
        """
        # 如果已知是用户页面，直接提取用户ID
        if content_type == ContentType.USER or '/user/' in url:
            user_patterns = [
                r'/user/([\w-]+)',
                r'sec_uid=([\w-]+)'
            ]
            
            for pattern in user_patterns:
                match = re.search(pattern, url)
                if match:
                    user_id = match.group(1)
                    logger.info(f"提取到用户ID: {user_id}")
                    return user_id
        
        # 视频ID模式（优先）
        video_patterns = [
            r'/video/(\d+)',
            r'/note/(\d+)',
            r'modal_id=(\d+)',
            r'aweme_id=(\d+)',
            r'item_id=(\d+)'
        ]
        
        for pattern in video_patterns:
            match = re.search(pattern, url)
            if match:
                video_id = match.group(1)
                logger.info(f"提取到视频ID: {video_id}")
                return video_id
        
        # 其他模式
        other_patterns = [
            r'/collection/(\d+)',
            r'/music/(\d+)'
        ]
        
        for pattern in other_patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        # 尝试从URL中提取数字ID
        number_match = re.search(r'(\d{15,20})', url)
        if number_match:
            video_id = number_match.group(1)
            logger.info(f"从URL提取到数字ID: {video_id}")
            return video_id
        
        logger.error(f"无法从URL提取ID: {url}")
        return None

    def _get_aweme_id_from_info(self, info: Dict) -> Optional[str]:
        """从 aweme 信息中提取 aweme_id"""
        try:
            if 'aweme_id' in info:
                return str(info.get('aweme_id'))
            # aweme_detail 结构
            return str(info.get('aweme', {}).get('aweme_id') or info.get('aweme_id'))
        except Exception:
            return None

    def _get_sec_uid_from_info(self, info: Dict) -> Optional[str]:
        """从 aweme 信息中提取作者 sec_uid"""
        try:
            return info.get('author', {}).get('sec_uid')
        except Exception:
            return None

    def _should_skip_increment(self, context: str, info: Dict, mix_id: Optional[str] = None, music_id: Optional[str] = None, sec_uid: Optional[str] = None) -> bool:
        """根据增量配置、数据库记录和文件夹判断是否跳过下载"""
        aweme_id = self._get_aweme_id_from_info(info)
        if not aweme_id:
            return False
        
        # 先检查文件是否已存在（优先级最高）
        try:
            from pathlib import Path
            # 获取作者昵称
            author = info.get('author', {}).get('nickname', 'unknown')
            # 构造可能的文件路径模式
            download_path = Path(self.save_path) / author
            if download_path.exists():
                # 检查是否有包含aweme_id的文件/文件夹
                for item in download_path.iterdir():
                    if aweme_id in item.name:
                        logger.info(f"⏭️ 文件已存在，跳过: {item.name}")
                        return True
        except Exception as e:
            logger.debug(f"文件检查失败: {e}")
        
        # 再检查数据库
        if not self.db:
            return False

        try:
            if context == 'post' and self.increase_cfg.get('post', False):
                sec = sec_uid or self._get_sec_uid_from_info(info) or ''
                return bool(self.db.get_user_post(sec, int(aweme_id)) if aweme_id.isdigit() else None)
            if context == 'like' and self.increase_cfg.get('like', False):
                sec = sec_uid or self._get_sec_uid_from_info(info) or ''
                return bool(self.db.get_user_like(sec, int(aweme_id)) if aweme_id.isdigit() else None)
            if context == 'mix' and self.increase_cfg.get('mix', False):
                sec = sec_uid or self._get_sec_uid_from_info(info) or ''
                mid = mix_id or ''
                return bool(self.db.get_mix(sec, mid, int(aweme_id)) if aweme_id.isdigit() else None)
            if context == 'music' and self.increase_cfg.get('music', False):
                mid = music_id or ''
                return bool(self.db.get_music(mid, int(aweme_id)) if aweme_id.isdigit() else None)
        except Exception:
            return False
        return False

    def _record_increment(self, context: str, info: Dict, mix_id: Optional[str] = None, music_id: Optional[str] = None, sec_uid: Optional[str] = None):
        """下载成功后写入数据库记录"""
        if not self.db:
            return
        aweme_id = self._get_aweme_id_from_info(info)
        if not aweme_id or not aweme_id.isdigit():
            return
        try:
            if context == 'post':
                sec = sec_uid or self._get_sec_uid_from_info(info) or ''
                self.db.insert_user_post(sec, int(aweme_id), info)
            elif context == 'like':
                sec = sec_uid or self._get_sec_uid_from_info(info) or ''
                self.db.insert_user_like(sec, int(aweme_id), info)
            elif context == 'mix':
                sec = sec_uid or self._get_sec_uid_from_info(info) or ''
                mid = mix_id or ''
                self.db.insert_mix(sec, mid, int(aweme_id), info)
            elif context == 'music':
                mid = music_id or ''
                self.db.insert_music(mid, int(aweme_id), info)
        except Exception:
            pass
    
    async def download_single_video(self, url: str, progress=None) -> bool:
        """下载单个视频/图文"""
        try:
            # 解析短链接
            url = await self.resolve_short_url(url)
            
            # 提取ID
            video_id = self.extract_id_from_url(url, ContentType.VIDEO)
            if not video_id:
                logger.error(f"无法从URL提取ID: {url}")
                return False
            
            # 如果没有提取到视频ID，尝试作为视频ID直接使用
            if not video_id and '/user/' not in url:
                # 可能短链接直接包含了视频ID
                video_id = url.split('/')[-2] if url.endswith('/') else url.split('/')[-1]
                logger.info(f"尝试从短链接路径提取ID: {video_id}")
            
            if not video_id:
                logger.error(f"无法从URL提取视频ID: {url}")
                return False
            
            # 限速
            await self.rate_limiter.acquire()
            
            # 获取视频信息
            if progress:
                progress.update(task_id=progress.task_ids[-1], description="获取视频信息...")
            
            video_info = await self.retry_manager.execute_with_retry(
                self._fetch_video_info, video_id
            )
            
            if not video_info:
                logger.error(f"无法获取视频信息: {video_id}")
                self.stats.failed += 1
                return False
            
            # 下载视频文件
            if progress:
                progress.update(task_id=progress.task_ids[-1], description="下载视频文件...")
            
            success = await self._download_media_files(video_info, progress)
            
            # 统计在 _download_media_files 内已更新，这里只输出汇总信息
            if success:
                logger.info(f"✅ 下载就绪(新/已存在): {url}")
            else:
                logger.error(f"❌ 下载失败: {url}")
            
            return success
            
        except Exception as e:
            logger.error(f"下载视频异常 {url}: {e}")
            self.stats.failed += 1
            return False
        finally:
            self.stats.total += 1
    
    async def _fetch_video_info(self, video_id: str) -> Optional[Dict]:
        """获取视频信息"""
        try:
            # 直接使用 DouYinCommand.py 中成功的 Douyin 类
            from apiproxy.douyin.douyin import Douyin
            
            # 创建 Douyin 实例
            dy = Douyin(database=False)
            
            # 设置我们的 cookies 到 douyin_headers
            if hasattr(self, 'cookies') and self.cookies:
                cookie_str = self._build_cookie_string()
                if cookie_str:
                    from apiproxy.douyin import douyin_headers
                    douyin_headers['Cookie'] = cookie_str
                    logger.info(f"设置 Cookie 到 Douyin 类: {cookie_str[:100]}...")
            
            try:
                # 使用现有的成功实现
                result = dy.getAwemeInfo(video_id)
                if result:
                    logger.info(f"Douyin 类成功获取视频信息: {result.get('desc', '')[:30]}")
                    return result
                else:
                    logger.error("Douyin 类返回空结果")
                    
            except Exception as e:
                logger.error(f"Douyin 类获取视频信息失败: {e}")
                
        except Exception as e:
            logger.error(f"导入或使用 Douyin 类失败: {e}")
            import traceback
            traceback.print_exc()
        
        # 如果 Douyin 类失败，尝试备用接口（iesdouyin，无需X-Bogus）
        try:
            fallback_url = f"https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={video_id}"
            logger.info(f"尝试备用接口获取视频信息: {fallback_url}")
            
            # 设置更通用的请求头
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.douyin.com/',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(fallback_url, headers=headers, timeout=15) as response:
                    logger.info(f"备用接口响应状态: {response.status}")
                    if response.status != 200:
                        logger.error(f"备用接口请求失败，状态码: {response.status}")
                        return None
                    
                    text = await response.text()
                    logger.info(f"备用接口响应内容长度: {len(text)}")
                    
                    if not text:
                        logger.error("备用接口响应为空")
                        return None
                    
                    try:
                        data = json.loads(text)
                        logger.info(f"备用接口返回数据: {data}")
                        
                        item_list = (data or {}).get('item_list') or []
                        if item_list:
                            aweme_detail = item_list[0]
                            logger.info("备用接口成功获取视频信息")
                            return aweme_detail
                        else:
                            logger.error("备用接口返回的数据中没有 item_list")
                            
                    except json.JSONDecodeError as e:
                        logger.error(f"备用接口JSON解析失败: {e}")
                        logger.error(f"原始响应内容: {text}")
                        return None
                        
        except Exception as e:
            logger.error(f"备用接口获取视频信息失败: {e}")
        
        return None
    
    def _build_detail_params(self, aweme_id: str) -> str:
        """构建详情API参数"""
        # 使用与现有 douyinapi.py 相同的参数格式
        params = [
            f'aweme_id={aweme_id}',
            'device_platform=webapp',
            'aid=6383'
        ]
        return '&'.join(params)
    
    async def _download_media_files(self, video_info: Dict, progress=None) -> bool:
        """下载媒体文件
        返回True表示最终就绪（已存在或新下载成功）；
        由调用方根据是否实际下载来统计success或skipped。
        """
        try:
            # 判断类型
            is_image = bool(video_info.get('images'))
            
            # 构建保存路径
            author_name = video_info.get('author', {}).get('nickname', 'unknown')
            desc = video_info.get('desc', '')[:50].replace('/', '_')
            # 兼容 create_time 为时间戳或格式化字符串
            raw_create_time = video_info.get('create_time')
            dt_obj = None
            if isinstance(raw_create_time, (int, float)):
                dt_obj = datetime.fromtimestamp(raw_create_time)
            elif isinstance(raw_create_time, str) and raw_create_time:
                for fmt in ('%Y-%m-%d %H.%M.%S', '%Y-%m-%d_%H-%M-%S', '%Y-%m-%d %H:%M:%S'):
                    try:
                        dt_obj = datetime.strptime(raw_create_time, fmt)
                        break
                    except Exception:
                        pass
            if dt_obj is None:
                dt_obj = datetime.fromtimestamp(time.time())
            create_time = dt_obj.strftime('%Y-%m-%d_%H-%M-%S')
            
            folder_name = f"{create_time}_{desc}" if desc else create_time
            save_dir = self.save_path / author_name / folder_name
            save_dir.mkdir(parents=True, exist_ok=True)
            
            success = True
            actually_downloaded = False
            
            if is_image:
                # 下载图文（无水印）
                images = video_info.get('images', [])
                for i, img in enumerate(images):
                    img_url = self._get_best_quality_url(img.get('url_list', []))
                    if img_url:
                        file_path = save_dir / f"image_{i+1}.jpg"
                        if await self._download_file(img_url, file_path):
                            logger.info(f"下载图片 {i+1}/{len(images)}: {file_path.name}")
                        else:
                            success = False
            else:
                # 下载视频（无水印）
                video_url = self._get_no_watermark_url(video_info)
                if video_url:
                    file_path = save_dir / f"{folder_name}.mp4"
                    # 先判断是否已存在，用于统计skipped
                    already_exists = file_path.exists()
                    if await self._download_file(video_url, file_path):
                        if not already_exists:
                            actually_downloaded = True
                        logger.info(f"下载视频: {file_path.name}")
                    else:
                        success = False
                
                # 下载音频
                if self.config.get('music', True):
                    music_url = self._get_music_url(video_info)
                    if music_url:
                        file_path = save_dir / f"{folder_name}_music.mp3"
                        await self._download_file(music_url, file_path)
            
            # 下载封面
            if self.config.get('cover', True):
                cover_url = self._get_cover_url(video_info)
                if cover_url:
                    file_path = save_dir / f"{folder_name}_cover.jpg"
                    await self._download_file(cover_url, file_path)
            
            # 保存JSON数据
            if self.config.get('json', True):
                json_path = save_dir / f"{folder_name}_data.json"
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(video_info, f, ensure_ascii=False, indent=2)
            
            # 根据实际下载与否更新统计（避免把已存在计为成功）
            if success:
                if actually_downloaded:
                    self.stats.success += 1
                else:
                    self.stats.skipped += 1
            else:
                self.stats.failed += 1

            return success
            
        except Exception as e:
            logger.error(f"下载媒体文件失败: {e}")
            return False
    
    def _get_no_watermark_url(self, video_info: Dict) -> Optional[str]:
        """获取无水印视频URL"""
        try:
            # 优先使用play_addr_h264
            play_addr = video_info.get('video', {}).get('play_addr_h264') or \
                       video_info.get('video', {}).get('play_addr')
            
            if play_addr:
                url_list = play_addr.get('url_list', [])
                if url_list:
                    # 替换URL以获取无水印版本
                    url = url_list[0]
                    url = url.replace('playwm', 'play')
                    url = url.replace('720p', '1080p')
                    return url
            
            # 备用：download_addr
            download_addr = video_info.get('video', {}).get('download_addr')
            if download_addr:
                url_list = download_addr.get('url_list', [])
                if url_list:
                    return url_list[0]
                    
        except Exception as e:
            logger.error(f"获取无水印URL失败: {e}")
        
        return None
    
    def _get_best_quality_url(self, url_list: List[str]) -> Optional[str]:
        """获取最高质量的URL"""
        if not url_list:
            return None
        
        # 优先选择包含特定关键词的URL
        for keyword in ['1080', 'origin', 'high']:
            for url in url_list:
                if keyword in url:
                    return url
        
        # 返回第一个
        return url_list[0]
    
    def _get_music_url(self, video_info: Dict) -> Optional[str]:
        """获取音乐URL"""
        try:
            music = video_info.get('music', {})
            play_url = music.get('play_url', {})
            url_list = play_url.get('url_list', [])
            return url_list[0] if url_list else None
        except:
            return None
    
    def _get_cover_url(self, video_info: Dict) -> Optional[str]:
        """获取封面URL"""
        try:
            cover = video_info.get('video', {}).get('cover', {})
            url_list = cover.get('url_list', [])
            return self._get_best_quality_url(url_list)
        except:
            return None
    
    async def _download_file(self, url: str, save_path: Path, max_retries: int = 3) -> bool:
        """下载文件（带重试机制）"""
        if save_path.exists():
            logger.info(f"文件已存在，跳过: {save_path.name}")
            return True
        
        for attempt in range(max_retries):
            try:
                timeout = aiohttp.ClientTimeout(total=300, connect=30)  # 5分钟总超时
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 200:
                            content = await response.read()
                            with open(save_path, 'wb') as f:
                                f.write(content)
                            return True
                        else:
                            logger.error(f"下载失败，状态码: {response.status}")
                            
            except Exception as e:
                logger.error(f"下载文件失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 * (attempt + 1))  # 递增等待
                    continue
        
        return False
    
    async def download_user_page(self, url: str) -> bool:
        """下载用户主页内容"""
        try:
            # 初始化Cookie（重要！）
            await self._initialize_cookies_and_headers()
            
            # 提取用户ID
            user_id = self.extract_id_from_url(url, ContentType.USER)
            if not user_id:
                logger.error(f"无法从URL提取用户ID: {url}")
                return False
            
            console.print(f"\n[cyan]正在获取用户 {user_id} 的作品列表...[/cyan]")
            
            # 根据配置下载不同类型的内容
            mode = self.config.get('mode', ['post'])
            if isinstance(mode, str):
                mode = [mode]
            
            # 增加总任务数统计
            total_posts = 0
            if 'post' in mode:
                total_posts += self.config.get('number', {}).get('post', 0) or 1
            if 'like' in mode:
                total_posts += self.config.get('number', {}).get('like', 0) or 1
            if 'mix' in mode:
                total_posts += self.config.get('number', {}).get('allmix', 0) or 1
            
            self.stats.total += total_posts
            
            for m in mode:
                if m == 'post':
                    await self._download_user_posts(user_id)
                elif m == 'like':
                    await self._download_user_likes(user_id)
                elif m == 'mix':
                    await self._download_user_mixes(user_id)
            
            return True
            
        except Exception as e:
            logger.error(f"下载用户主页失败: {e}")
            return False
    
    async def _download_user_posts(self, user_id: str):
        """下载用户发布的作品"""
        max_count = self.config.get('number', {}).get('post', 0)
        min_pages = self.config.get('min_fetch_pages', 3)  # 最少获取3页作品列表
        cursor = 0
        downloaded = 0
        page_num = 0
        
        # 第一阶段：先获取至少min_pages页的作品列表
        all_aweme_list = []
        console.print(f"\n[green]开始获取用户作品列表（至少{min_pages}页）...[/green]")
        
        while True:
            await self.rate_limiter.acquire()
            posts_data = await self._fetch_user_posts(user_id, cursor)
            if not posts_data:
                break
            
            aweme_list = posts_data.get('aweme_list', [])
            if not aweme_list:
                break
            
            page_num += 1
            all_aweme_list.extend(aweme_list)
            console.print(f"[cyan]📄 第{page_num}页: 获取到 {len(aweme_list)} 个作品（累计 {len(all_aweme_list)} 个）[/cyan]")
            
            has_more = posts_data.get('has_more', False)
            if not has_more:
                console.print(f"[green]✅ 已获取所有作品[/green]")
                break
            
            # 至少获取min_pages页，或者已经够下载数量了
            if page_num >= min_pages and (max_count > 0 and len(all_aweme_list) >= max_count):
                break
            
            cursor = posts_data.get('max_cursor', 0)
            import random
            delay = random.uniform(2.0, 4.0)
            console.print(f"[dim]⏳ 等待 {delay:.1f} 秒后获取下一页...[/dim]")
            await asyncio.sleep(delay)
        
        console.print(f"[green]✅ 共获取 {len(all_aweme_list)} 个作品，开始下载...[/green]")
        
        # 第二阶段：下载作品
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            
            for aweme in all_aweme_list:
                if max_count > 0 and downloaded >= max_count:
                    console.print(f"[yellow]已达到下载数量限制: {max_count}[/yellow]")
                    break
                
                # 时间过滤
                if not self._check_time_filter(aweme):
                    continue
                
                # 创建下载任务
                task_id = progress.add_task(
                    f"下载作品 {downloaded + 1}", 
                    total=100
                )
                
                # 增量判断
                if self._should_skip_increment('post', aweme, sec_uid=user_id):
                    continue
                
                # 下载
                success = await self._download_media_files(aweme, progress)
                
                if success:
                    downloaded += 1
                    progress.update(task_id, completed=100)
                    self._record_increment('post', aweme, sec_uid=user_id)
                    import random
                    await asyncio.sleep(random.uniform(1.0, 3.0))
                else:
                    progress.update(task_id, description="[red]下载失败[/red]")
                    await asyncio.sleep(2.0)
        
        console.print(f"[green]✅ 用户作品下载完成，共下载 {downloaded} 个[/green]")
    
    async def _fetch_user_posts(self, user_id: str, cursor: int = 0) -> Optional[Dict]:
        """获取用户作品列表（支持真正的分页）+ 重试机制"""
        max_retries = 3  # 最多重试3次
        retry_delay = 3.0  # 每次重试等待3秒
        
        for attempt in range(max_retries):
            try:
                from apiproxy.douyin import douyin_headers
                from apiproxy.douyin.urls import Urls
                from apiproxy.common.utils import Utils
                import json
                
                urls = Urls()
                utils = Utils()
                
                # 每次获取35个作品（一页）
                count = 35
                
                # 构建请求参数
                base_params = f'sec_user_id={user_id}&count={count}&max_cursor={cursor}&device_platform=webapp&aid=6383&channel=channel_pc_web&pc_client_type=1&version_code=170400&version_name=17.4.0&cookie_enabled=true&screen_width=1920&screen_height=1080&browser_language=zh-CN&browser_platform=MacIntel&browser_name=Chrome&browser_version=122.0.0.0&browser_online=true&engine_name=Blink&engine_version=122.0.0.0&os_name=Mac&os_version=10.15.7&cpu_core_num=8&device_memory=8&platform=PC&downlink=10&effective_type=4g&round_trip_time=50'
                
                url = urls.USER_POST + utils.getXbogus(base_params)
                
                # 使用异步请求（超时时间加长到15秒）
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=douyin_headers, timeout=aiohttp.ClientTimeout(total=15)) as res:
                        if res.status != 200:
                            logger.error(f"HTTP请求失败: {res.status}，尝试 {attempt + 1}/{max_retries}")
                            if attempt < max_retries - 1:
                                await asyncio.sleep(retry_delay)
                                continue
                            return None
                        
                        text = await res.text()
                
                # 解析响应
                datadict = json.loads(text)
                
                if datadict.get("status_code") != 0:
                    logger.error(f"API返回错误: status_code={datadict.get('status_code')}，尝试 {attempt + 1}/{max_retries}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    return None
                
                # 检查aweme_list
                if "aweme_list" not in datadict:
                    logger.warning(f"响应中缺少aweme_list字段，尝试 {attempt + 1}/{max_retries}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    return None
                
                aweme_list = datadict.get("aweme_list", [])
                has_more = datadict.get("has_more", False)
                max_cursor = datadict.get("max_cursor", cursor)
                
                logger.info(f"✅ 成功获取 {len(aweme_list)} 个作品，has_more={has_more}, cursor={max_cursor}")
                
                # 转换数据格式（兼容旧格式）
                from apiproxy.douyin.douyin import Douyin
                from apiproxy.douyin.result import Result
                
                dy = Douyin(database=False)
                result_obj = Result()
                converted_list = []
                
                for aweme in aweme_list:
                    result_obj.clearDict(result_obj.awemeDict)
                    aweme_type = 1 if aweme.get("images") else 0
                    result_obj.dataConvert(aweme_type, result_obj.awemeDict, aweme)
                    import copy
                    converted_list.append(copy.deepcopy(result_obj.awemeDict))
                
                return {
                    'status_code': 0,
                    'aweme_list': converted_list,
                    'max_cursor': max_cursor,
                    'has_more': has_more  # ✅ 真实的has_more值
                }
                    
            except Exception as e:
                logger.error(f"获取用户作品列表失败（尝试 {attempt + 1}/{max_retries}）: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"等待 {retry_delay} 秒后重试...")
                    await asyncio.sleep(retry_delay)
                    continue
                import traceback
                traceback.print_exc()
        
        logger.error(f"重试 {max_retries} 次后仍然失败")
        return None
    
    async def _download_user_likes(self, user_id: str):
        """下载用户喜欢的作品"""
        max_count = 0
        try:
            max_count = int(self.config.get('number', {}).get('like', 0))
        except Exception:
            max_count = 0
        cursor = 0
        downloaded = 0

        console.print(f"\n[green]开始下载用户喜欢的作品...[/green]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        ) as progress:

            while True:
                # 限速
                await self.rate_limiter.acquire()

                # 获取喜欢列表
                likes_data = await self._fetch_user_likes(user_id, cursor)
                if not likes_data:
                    break

                aweme_list = likes_data.get('aweme_list', [])
                if not aweme_list:
                    break

                # 下载作品
                for aweme in aweme_list:
                    if max_count > 0 and downloaded >= max_count:
                        console.print(f"[yellow]已达到下载数量限制: {max_count}[/yellow]")
                        return

                    if not self._check_time_filter(aweme):
                        continue

                    task_id = progress.add_task(
                        f"下载喜欢 {downloaded + 1}",
                        total=100
                    )

                    # 增量判断
                    if self._should_skip_increment('like', aweme, sec_uid=user_id):
                        continue

                    success = await self._download_media_files(aweme, progress)

                    if success:
                        downloaded += 1
                        progress.update(task_id, completed=100)
                        self._record_increment('like', aweme, sec_uid=user_id)
                    else:
                        progress.update(task_id, description="[red]下载失败[/red]")

                # 翻页
                if not likes_data.get('has_more'):
                    break
                cursor = likes_data.get('max_cursor', 0)

        console.print(f"[green]✅ 喜欢作品下载完成，共下载 {downloaded} 个[/green]")

    async def _fetch_user_likes(self, user_id: str, cursor: int = 0) -> Optional[Dict]:
        """获取用户喜欢的作品列表"""
        try:
            params_list = [
                f'sec_user_id={user_id}',
                f'max_cursor={cursor}',
                'count=35',
                'aid=6383',
                'device_platform=webapp',
                'channel=channel_pc_web',
                'pc_client_type=1',
                'version_code=170400',
                'version_name=17.4.0',
                'cookie_enabled=true',
                'screen_width=1920',
                'screen_height=1080',
                'browser_language=zh-CN',
                'browser_platform=MacIntel',
                'browser_name=Chrome',
                'browser_version=122.0.0.0',
                'browser_online=true'
            ]
            params = '&'.join(params_list)

            api_url = self.urls_helper.USER_FAVORITE_A

            try:
                xbogus = self.utils.getXbogus(params)
                full_url = f"{api_url}{params}&X-Bogus={xbogus}"
            except Exception as e:
                logger.warning(f"获取X-Bogus失败: {e}, 尝试不带X-Bogus")
                full_url = f"{api_url}{params}"

            logger.info(f"请求用户喜欢列表: {full_url[:100]}...")

            async with aiohttp.ClientSession() as session:
                async with session.get(full_url, headers=self.headers, timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"请求失败，状态码: {response.status}")
                        return None

                    text = await response.text()
                    if not text:
                        logger.error("响应内容为空")
                        return None

                    data = json.loads(text)
                    if data.get('status_code') == 0:
                        return data
                    else:
                        logger.error(f"API返回错误: {data.get('status_msg', '未知错误')}")
                        return None
        except Exception as e:
            logger.error(f"获取用户喜欢列表失败: {e}")
        return None

    async def _download_user_mixes(self, user_id: str):
        """下载用户的所有合集（按配置可限制数量）"""
        max_allmix = 0
        try:
            # 兼容旧键名 allmix 或 mix
            number_cfg = self.config.get('number', {}) or {}
            max_allmix = int(number_cfg.get('allmix', number_cfg.get('mix', 0)) or 0)
        except Exception:
            max_allmix = 0

        cursor = 0
        fetched = 0

        console.print(f"\n[green]开始获取用户合集列表...[/green]")
        while True:
            await self.rate_limiter.acquire()
            mix_list_data = await self._fetch_user_mix_list(user_id, cursor)
            if not mix_list_data:
                break

            mix_infos = mix_list_data.get('mix_infos') or []
            if not mix_infos:
                break

            for mix in mix_infos:
                if max_allmix > 0 and fetched >= max_allmix:
                    console.print(f"[yellow]已达到合集数量限制: {max_allmix}[/yellow]")
                    return
                mix_id = mix.get('mix_id')
                mix_name = mix.get('mix_name', '')
                console.print(f"[cyan]下载合集[/cyan]: {mix_name} ({mix_id})")
                await self._download_mix_by_id(mix_id)
                fetched += 1

            if not mix_list_data.get('has_more'):
                break
            cursor = mix_list_data.get('cursor', 0)

        console.print(f"[green]✅ 用户合集下载完成，共处理 {fetched} 个[/green]")

    async def _fetch_user_mix_list(self, user_id: str, cursor: int = 0) -> Optional[Dict]:
        """获取用户合集列表"""
        try:
            params_list = [
                f'sec_user_id={user_id}',
                f'cursor={cursor}',
                'count=35',
                'aid=6383',
                'device_platform=webapp',
                'channel=channel_pc_web',
                'pc_client_type=1',
                'version_code=170400',
                'version_name=17.4.0',
                'cookie_enabled=true',
                'screen_width=1920',
                'screen_height=1080',
                'browser_language=zh-CN',
                'browser_platform=MacIntel',
                'browser_name=Chrome',
                'browser_version=122.0.0.0',
                'browser_online=true'
            ]
            params = '&'.join(params_list)

            api_url = self.urls_helper.USER_MIX_LIST
            try:
                xbogus = self.utils.getXbogus(params)
                full_url = f"{api_url}{params}&X-Bogus={xbogus}"
            except Exception as e:
                logger.warning(f"获取X-Bogus失败: {e}, 尝试不带X-Bogus")
                full_url = f"{api_url}{params}"

            logger.info(f"请求用户合集列表: {full_url[:100]}...")
            async with aiohttp.ClientSession() as session:
                async with session.get(full_url, headers=self.headers, timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"请求失败，状态码: {response.status}")
                        return None
                    text = await response.text()
                    if not text:
                        logger.error("响应内容为空")
                        return None
                    data = json.loads(text)
                    if data.get('status_code') == 0:
                        return data
                    else:
                        logger.error(f"API返回错误: {data.get('status_msg', '未知错误')}")
                        return None
        except Exception as e:
            logger.error(f"获取用户合集列表失败: {e}")
        return None

    async def download_mix(self, url: str) -> bool:
        """根据合集链接下载合集内所有作品"""
        try:
            mix_id = None
            for pattern in [r'/collection/(\d+)', r'/mix/detail/(\d+)']:
                m = re.search(pattern, url)
                if m:
                    mix_id = m.group(1)
                    break
            if not mix_id:
                logger.error(f"无法从合集链接提取ID: {url}")
                return False
            await self._download_mix_by_id(mix_id)
            return True
        except Exception as e:
            logger.error(f"下载合集失败: {e}")
            return False

    async def _download_mix_by_id(self, mix_id: str):
        """按合集ID下载全部作品"""
        cursor = 0
        downloaded = 0

        console.print(f"\n[green]开始下载合集 {mix_id} ...[/green]")

        while True:
            await self.rate_limiter.acquire()
            data = await self._fetch_mix_awemes(mix_id, cursor)
            if not data:
                break

            aweme_list = data.get('aweme_list') or []
            if not aweme_list:
                break

            for aweme in aweme_list:
                success = await self._download_media_files(aweme)
                if success:
                    downloaded += 1

            if not data.get('has_more'):
                break
            cursor = data.get('cursor', 0)

        console.print(f"[green]✅ 合集下载完成，共下载 {downloaded} 个[/green]")

    async def _fetch_mix_awemes(self, mix_id: str, cursor: int = 0) -> Optional[Dict]:
        """获取合集下作品列表"""
        try:
            params_list = [
                f'mix_id={mix_id}',
                f'cursor={cursor}',
                'count=35',
                'aid=6383',
                'device_platform=webapp',
                'channel=channel_pc_web',
                'pc_client_type=1',
                'version_code=170400',
                'version_name=17.4.0',
                'cookie_enabled=true',
                'screen_width=1920',
                'screen_height=1080',
                'browser_language=zh-CN',
                'browser_platform=MacIntel',
                'browser_name=Chrome',
                'browser_version=122.0.0.0',
                'browser_online=true'
            ]
            params = '&'.join(params_list)

            api_url = self.urls_helper.USER_MIX
            try:
                xbogus = self.utils.getXbogus(params)
                full_url = f"{api_url}{params}&X-Bogus={xbogus}"
            except Exception as e:
                logger.warning(f"获取X-Bogus失败: {e}, 尝试不带X-Bogus")
                full_url = f"{api_url}{params}"

            logger.info(f"请求合集作品列表: {full_url[:100]}...")
            async with aiohttp.ClientSession() as session:
                async with session.get(full_url, headers=self.headers, timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"请求失败，状态码: {response.status}")
                        return None
                    text = await response.text()
                    if not text:
                        logger.error("响应内容为空")
                        return None
                    data = json.loads(text)
                    # USER_MIX 返回没有统一的 status_code，这里直接返回
                    return data
        except Exception as e:
            logger.error(f"获取合集作品失败: {e}")
        return None

    async def download_music(self, url: str) -> bool:
        """根据音乐页链接下载音乐下的所有作品（支持增量）"""
        try:
            # 提取 music_id
            music_id = None
            m = re.search(r'/music/(\d+)', url)
            if m:
                music_id = m.group(1)
            if not music_id:
                logger.error(f"无法从音乐链接提取ID: {url}")
                return False

            cursor = 0
            downloaded = 0
            limit_num = 0
            try:
                limit_num = int((self.config.get('number', {}) or {}).get('music', 0))
            except Exception:
                limit_num = 0

            console.print(f"\n[green]开始下载音乐 {music_id} 下的作品...[/green]")

            while True:
                await self.rate_limiter.acquire()
                data = await self._fetch_music_awemes(music_id, cursor)
                if not data:
                    break
                aweme_list = data.get('aweme_list') or []
                if not aweme_list:
                    break

                for aweme in aweme_list:
                    if limit_num > 0 and downloaded >= limit_num:
                        console.print(f"[yellow]已达到音乐下载数量限制: {limit_num}[/yellow]")
                        return True
                    if self._should_skip_increment('music', aweme, music_id=music_id):
                        continue
                    success = await self._download_media_files(aweme)
                    if success:
                        downloaded += 1
                        self._record_increment('music', aweme, music_id=music_id)

                if not data.get('has_more'):
                    break
                cursor = data.get('cursor', 0)

            console.print(f"[green]✅ 音乐作品下载完成，共下载 {downloaded} 个[/green]")
            return True
        except Exception as e:
            logger.error(f"下载音乐页失败: {e}")
            return False

    async def _fetch_music_awemes(self, music_id: str, cursor: int = 0) -> Optional[Dict]:
        """获取音乐下作品列表"""
        try:
            params_list = [
                f'music_id={music_id}',
                f'cursor={cursor}',
                'count=35',
                'aid=6383',
                'device_platform=webapp',
                'channel=channel_pc_web',
                'pc_client_type=1',
                'version_code=170400',
                'version_name=17.4.0',
                'cookie_enabled=true',
                'screen_width=1920',
                'screen_height=1080',
                'browser_language=zh-CN',
                'browser_platform=MacIntel',
                'browser_name=Chrome',
                'browser_version=122.0.0.0',
                'browser_online=true'
            ]
            params = '&'.join(params_list)

            api_url = self.urls_helper.MUSIC
            try:
                xbogus = self.utils.getXbogus(params)
                full_url = f"{api_url}{params}&X-Bogus={xbogus}"
            except Exception as e:
                logger.warning(f"获取X-Bogus失败: {e}, 尝试不带X-Bogus")
                full_url = f"{api_url}{params}"

            logger.info(f"请求音乐作品列表: {full_url[:100]}...")
            async with aiohttp.ClientSession() as session:
                async with session.get(full_url, headers=self.headers, timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"请求失败，状态码: {response.status}")
                        return None
                    text = await response.text()
                    if not text:
                        logger.error("响应内容为空")
                        return None
                    data = json.loads(text)
                    return data
        except Exception as e:
            logger.error(f"获取音乐作品失败: {e}")
        return None
    
    def _check_time_filter(self, aweme: Dict) -> bool:
        """检查时间过滤"""
        start_time = self.config.get('start_time')
        end_time = self.config.get('end_time')
        
        if not start_time and not end_time:
            return True
        
        raw_create_time = aweme.get('create_time')
        if not raw_create_time:
            return True
        
        create_date = None
        if isinstance(raw_create_time, (int, float)):
            try:
                create_date = datetime.fromtimestamp(raw_create_time)
            except Exception:
                create_date = None
        elif isinstance(raw_create_time, str):
            for fmt in ('%Y-%m-%d %H.%M.%S', '%Y-%m-%d_%H-%M-%S', '%Y-%m-%d %H:%M:%S'):
                try:
                    create_date = datetime.strptime(raw_create_time, fmt)
                    break
                except Exception:
                    pass
        
        if create_date is None:
            return True
        
        if start_time:
            start_date = datetime.strptime(start_time, '%Y-%m-%d')
            if create_date < start_date:
                return False
        
        if end_time:
            end_date = datetime.strptime(end_time, '%Y-%m-%d')
            if create_date > end_date:
                return False
        
        return True
    
    async def run(self):
        """运行下载器"""
        # 显示启动信息
        console.print(Panel.fit(
            "[bold cyan]抖音下载器 v3.0 - 统一增强版[/bold cyan]\n"
            "[dim]支持视频、图文、用户主页、合集批量下载[/dim]",
            border_style="cyan"
        ))
        
        # 初始化Cookie与请求头
        await self._initialize_cookies_and_headers()
        
        # 获取URL列表
        urls = self.config.get('link', [])
        # 兼容：单条字符串
        if isinstance(urls, str):
            urls = [urls]
        if not urls:
            console.print("[red]没有找到要下载的链接！[/red]")
            return
        
        # 分析URL类型
        console.print(f"\n[cyan]📊 链接分析[/cyan]")
        url_types = {}
        for url in urls:
            content_type = self.detect_content_type(url)
            url_types[url] = content_type
            console.print(f"  • {content_type.upper()}: {url[:50]}...")
        
        # 开始下载
        console.print(f"\n[green]⏳ 开始下载 {len(urls)} 个链接...[/green]\n")
        
        for i, url in enumerate(urls, 1):
            content_type = url_types[url]
            console.print(f"[{i}/{len(urls)}] 处理: {url}")
            
            if content_type == ContentType.VIDEO or content_type == ContentType.IMAGE:
                await self.download_single_video(url)
            elif content_type == ContentType.USER:
                await self.download_user_page(url)
                # 若配置包含 like 或 mix，顺带处理
                modes = self.config.get('mode', ['post'])
                if 'like' in modes:
                    user_id = self.extract_id_from_url(url, ContentType.USER)
                    if user_id:
                        await self._download_user_likes(user_id)
                if 'mix' in modes:
                    user_id = self.extract_id_from_url(url, ContentType.USER)
                    if user_id:
                        await self._download_user_mixes(user_id)
            elif content_type == ContentType.MIX:
                await self.download_mix(url)
            elif content_type == ContentType.MUSIC:
                await self.download_music(url)
            else:
                console.print(f"[yellow]不支持的内容类型: {content_type}[/yellow]")
            
            # 显示进度
            console.print(f"进度: {i}/{len(urls)} | 成功: {self.stats.success} | 失败: {self.stats.failed}")
            console.print("-" * 60)
        
        # 显示统计
        self._show_stats()
    
    def _show_stats(self):
        """显示下载统计"""
        console.print("\n" + "=" * 60)
        
        # 创建统计表格
        table = Table(title="📊 下载统计", show_header=True, header_style="bold magenta")
        table.add_column("项目", style="cyan", width=12)
        table.add_column("数值", style="green")
        
        stats = self.stats.to_dict()
        table.add_row("总任务数", str(stats['total']))
        table.add_row("成功", str(stats['success']))
        table.add_row("失败", str(stats['failed']))
        table.add_row("跳过", str(stats['skipped']))
        table.add_row("成功率", stats['success_rate'])
        table.add_row("用时", stats['elapsed_time'])
        
        console.print(table)
        console.print("\n[bold green]✅ 下载任务完成！[/bold green]")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='抖音下载器 - 统一增强版',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '-c', '--config',
        default='config.yml',
        help='配置文件路径 (默认: config.yml，自动兼容 config_simple.yml)'
    )
    
    parser.add_argument(
        '-u', '--url',
        nargs='+',
        help='直接指定要下载的URL'
    )
    parser.add_argument(
        '-p', '--path',
        default=None,
        help='保存路径 (覆盖配置文件)'
    )
    parser.add_argument(
        '--auto-cookie',
        action='store_true',
        help='自动获取Cookie（需要已安装Playwright）'
    )
    parser.add_argument(
        '--cookie',
        help='手动指定Cookie字符串，例如 "msToken=xxx; ttwid=yyy"'
    )
    
    args = parser.parse_args()
    
    # 组合配置来源：优先命令行
    temp_config = {}
    if args.url:
        temp_config['link'] = args.url
    
    # 覆盖保存路径
    if args.path:
        temp_config['path'] = args.path
    
    # Cookie配置
    if args.auto_cookie:
        temp_config['auto_cookie'] = True
        temp_config['cookies'] = 'auto'
    if args.cookie:
        temp_config['cookies'] = args.cookie
        temp_config['auto_cookie'] = False
    
    # 如果存在临时配置，则生成一个临时文件供现有构造函数使用
    if temp_config:
        # 合并文件配置（如存在）
        file_config = {}
        if os.path.exists(args.config):
            try:
                with open(args.config, 'r', encoding='utf-8') as f:
                    file_config = yaml.safe_load(f) or {}
            except Exception:
                file_config = {}
        
        # 兼容简化键名
        if 'links' in file_config and 'link' not in file_config:
            file_config['link'] = file_config['links']
        if 'output_dir' in file_config and 'path' not in file_config:
            file_config['path'] = file_config['output_dir']
        if 'cookie' in file_config and 'cookies' not in file_config:
            file_config['cookies'] = file_config['cookie']
        
        merged = {**(file_config or {}), **temp_config}
        with open('temp_config.yml', 'w', encoding='utf-8') as f:
            yaml.dump(merged, f, allow_unicode=True)
        config_path = 'temp_config.yml'
    else:
        config_path = args.config
    
    # 运行下载器
    try:
        downloader = UnifiedDownloader(config_path)
        asyncio.run(downloader.run())
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️ 用户中断下载[/yellow]")
    except Exception as e:
        console.print(f"\n[red]❌ 程序异常: {e}[/red]")
        logger.exception("程序异常")
    finally:
        # 清理临时配置
        if args.url and os.path.exists('temp_config.yml'):
            os.remove('temp_config.yml')


if __name__ == '__main__':
    main()
