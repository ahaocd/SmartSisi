import os
from abc import ABC
from typing import Union, Optional
from pathlib import Path

import yt_dlp

from app.downloaders.base import Downloader, DownloadQuality
from app.models.notes_model import AudioDownloadResult
from app.utils.path_helper import get_data_dir
from app.utils.url_parser import extract_video_id

# YouTube cookies 文件路径
YOUTUBE_COOKIES_FILE = Path(__file__).parent.parent.parent / "youtube_cookies.txt"


class YoutubeDownloader(Downloader, ABC):
    def __init__(self):
        super().__init__()
        # 检查 cookies 文件是否存在
        if YOUTUBE_COOKIES_FILE.exists():
            print(f"✅ YouTube cookies 文件已加载: {YOUTUBE_COOKIES_FILE}")
        else:
            print(f"⚠️ YouTube cookies 文件不存在: {YOUTUBE_COOKIES_FILE}")

    def download(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
        quality: DownloadQuality = "fast",
        need_video:Optional[bool]=False
    ) -> AudioDownloadResult:
        if output_dir is None:
            output_dir = get_data_dir()
        if not output_dir:
            output_dir=self.cache_data
        os.makedirs(output_dir, exist_ok=True)

        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'outtmpl': output_path,
            'noplaylist': True,
            'quiet': False,
        }
        # 使用 cookies 文件
        if YOUTUBE_COOKIES_FILE.exists():
            ydl_opts['cookiefile'] = str(YOUTUBE_COOKIES_FILE)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_id = info.get("id")
            title = info.get("title")
            duration = info.get("duration", 0)
            cover_url = info.get("thumbnail")
            ext = info.get("ext", "m4a")  # 兜底用 m4a
            audio_path = os.path.join(output_dir, f"{video_id}.{ext}")
        print('os.path.join(output_dir, f"{video_id}.{ext}")',os.path.join(output_dir, f"{video_id}.{ext}"))

        return AudioDownloadResult(
            file_path=audio_path,
            title=title,
            duration=duration,
            cover_url=cover_url,
            platform="youtube",
            video_id=video_id,
            raw_info={'tags':info.get('tags')}, #全部返回会报错
            video_path=None  # ❗音频下载不包含视频路径
        )

    def download_video(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
    ) -> str:
        """
        下载视频，返回视频文件路径
        """
        if output_dir is None:
            output_dir = get_data_dir()
        video_id = extract_video_id(video_url, "youtube")
        video_path = os.path.join(output_dir, f"{video_id}.mp4")
        if os.path.exists(video_path):
            return video_path
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
            'outtmpl': output_path,
            'noplaylist': True,
            'quiet': False,
            'merge_output_format': 'mp4',  # 确保合并成 mp4
        }
        # 优先使用 cookies 文件，如果不存在则尝试从 Edge 浏览器读取
        if YOUTUBE_COOKIES_FILE.exists():
            ydl_opts['cookiefile'] = str(YOUTUBE_COOKIES_FILE)
        else:
            # 尝试从 Edge 浏览器读取 cookies（Edge 通常比 Chrome 更稳定）
            ydl_opts['cookiesfrombrowser'] = ('edge',)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_id = info.get("id")
            video_path = os.path.join(output_dir, f"{video_id}.mp4")

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件未找到: {video_path}")

        return video_path

    def download_video_and_audio(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
    ) -> tuple:
        """
        一次性下载视频和音频，避免多次请求触发 YouTube 验证
        返回 (video_path, audio_path, info)
        """
        if output_dir is None:
            output_dir = get_data_dir()
        video_id = extract_video_id(video_url, "youtube")
        video_path = os.path.join(output_dir, f"{video_id}.mp4")
        audio_path = os.path.join(output_dir, f"{video_id}.m4a")
        
        os.makedirs(output_dir, exist_ok=True)

        # 下载视频（包含音频）
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
            'outtmpl': os.path.join(output_dir, "%(id)s.%(ext)s"),
            'noplaylist': True,
            'quiet': False,
            'merge_output_format': 'mp4',
            'keepvideo': True,  # 保留原始文件
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
            }],
        }
        if YOUTUBE_COOKIES_FILE.exists():
            ydl_opts['cookiefile'] = str(YOUTUBE_COOKIES_FILE)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)

        return video_path, audio_path, info
