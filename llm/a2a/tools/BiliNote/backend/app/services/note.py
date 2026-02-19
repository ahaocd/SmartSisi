import json
import logging
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional, Tuple, Union, Any

from fastapi import HTTPException
from pydantic import HttpUrl
from dotenv import load_dotenv

from app.downloaders.base import Downloader
from app.downloaders.bilibili_downloader import BilibiliDownloader
from app.downloaders.douyin_downloader import DouyinDownloader
from app.downloaders.local_downloader import LocalDownloader
from app.downloaders.youtube_downloader import YoutubeDownloader
from app.db.video_task_dao import delete_task_by_video, insert_video_task
from app.enmus.exception import NoteErrorEnum, ProviderErrorEnum
from app.enmus.task_status_enums import TaskStatus
from app.enmus.note_enums import DownloadQuality
from app.exceptions.note import NoteError
from app.exceptions.provider import ProviderError
from app.gpt.base import GPT
from app.gpt.gpt_factory import GPTFactory
from app.models.audio_model import AudioDownloadResult
from app.models.gpt_model import GPTSource
from app.models.model_config import ModelConfig
from app.models.notes_model import AudioDownloadResult, NoteResult
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.services.constant import SUPPORT_PLATFORM_MAP
from app.services.provider import ProviderService
from app.transcriber.base import Transcriber
from app.transcriber.transcriber_provider import get_transcriber, _transcribers
from app.utils.note_helper import replace_content_markers
from app.utils.status_code import StatusCode
from app.utils.video_helper import generate_screenshot
from app.utils.video_reader import VideoReader

# ------------------ 环境变量与全局配置 ------------------

# 从 .env 文件中加载环境变量
load_dotenv()

# 后端 API 地址与端口（若有需要可以在代码其他部分使用 BACKEND_BASE_URL）
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost")
BACKEND_PORT = os.getenv("BACKEND_PORT", "8483")
BACKEND_BASE_URL = f"{API_BASE_URL}:{BACKEND_PORT}"

# 输出目录（用于缓存音频、转写、Markdown 文件，以及存储截图）
NOTE_OUTPUT_DIR = Path(os.getenv("NOTE_OUTPUT_DIR", "note_results"))
NOTE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_OUTPUT_DIR = os.getenv("OUT_DIR", "./static/screenshots")
# 图片基础 URL（用于生成 Markdown 中的图片链接，需前端静态目录对应）
IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL", "/static/screenshots")

# 日志配置
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class NoteGenerator:
    """
    NoteGenerator 用于执行视频/音频下载、转写、GPT 生成笔记、插入截图/链接、
    以及将任务信息写入状态文件与数据库等功能。
    """

    def __init__(self):
        self.model_size: str = "base"
        self.device: Optional[str] = None
        self.transcriber_type: str = os.getenv("TRANSCRIBER_TYPE", "fast-whisper")
        self.transcriber: Transcriber = self._init_transcriber()
        self.video_path: Optional[Path] = None
        self.video_img_urls=[]
        logger.info("NoteGenerator 初始化完成")


    # ---------------- 公有方法 ----------------

    def generate(
        self,
        video_url: Union[str, HttpUrl],
        platform: str,
        quality: DownloadQuality = DownloadQuality.medium,
        task_id: Optional[str] = None,
        model_name: Optional[str] = None,
        provider_id: Optional[str] = None,
        vision_model_name: Optional[str] = None,
        vision_provider_id: Optional[str] = None,
        link: bool = False,
        screenshot: bool = False,
        _format: Optional[List[str]] = None,
        style: Optional[str] = None,
        extras: Optional[str] = None,
        output_path: Optional[str] = None,
        video_understanding: bool = False,
        video_interval: int = 0,
        grid_size: Optional[List[int]] = None,
    ) -> NoteResult | None:
        """
        主流程：按步骤依次下载、转写、GPT 总结、截图/链接处理、存库、返回 NoteResult。
        
        【优化后的流程】：
        1. 下载视频
        2. Whisper 转文字（本地，0 Token）
        3. 【文本模型】只根据文字生成文章 + 截图标记（不发图片！）
        4. 根据标记截图（本地 ffmpeg，0 Token）
        5. 【视觉模型】分析截图是否合适（可选，如果用户选了视觉模型）
        6. 输出最终文章

        :param video_url: 视频或音频链接
        :param platform: 平台名称，对应 SUPPORT_PLATFORM_MAP 中的键
        :param quality: 下载音频的质量枚举
        :param task_id: 用于标识本次任务的唯一 ID，亦用于状态文件和缓存文件命名
        :param model_name: 文本模型名称（用于生成文章）
        :param provider_id: 文本模型供应商 ID
        :param vision_model_name: 视觉模型名称（可选，用于分析截图）
        :param vision_provider_id: 视觉模型供应商 ID（可选）
        :param link: 是否在笔记中插入视频片段链接
        :param screenshot: 是否在笔记中替换 Screenshot 标记为图片
        :param _format: 包含 'link' 或 'screenshot' 等字符串的列表，决定后续处理
        :param style: GPT 生成笔记的风格
        :param extras: 额外参数，传递给 GPT
        :param output_path: 下载输出目录（可选）
        :param video_understanding: 是否需要视频理解（启用视觉模型分析截图）
        :param video_interval: 视频帧截取间隔（秒），仅在 video_understanding 为 True 时生效
        :param grid_size: 生成缩略图时的网格大小，如 [3, 3]（已废弃，不再使用网格图）
        :return: NoteResult 对象，包含 markdown 文本、转写结果和音频元信息
        """
        if grid_size is None:
            grid_size = []

        try:
            logger.info(f"开始生成笔记 (task_id={task_id})")
            logger.info(f"📋 参数检查: platform={platform}, screenshot={screenshot}, _format={_format}, video_understanding={video_understanding}")
            self._update_status(task_id, TaskStatus.PARSING)

            # 获取下载器与文本模型 GPT 实例
            downloader = self._get_downloader(platform)
            logger.info(f"📋 使用下载器: {type(downloader).__name__}")
            text_gpt = self._get_gpt(model_name, provider_id)
            
            # 获取视觉模型 GPT 实例（可选）
            vision_gpt = None
            if vision_model_name and vision_provider_id and vision_model_name != "none":
                vision_gpt = self._get_gpt(vision_model_name, vision_provider_id)
                logger.info(f"已启用视觉模型: {vision_model_name}")

            # 缓存文件路径
            audio_cache_file = NOTE_OUTPUT_DIR / f"{task_id}_audio.json"
            transcript_cache_file = NOTE_OUTPUT_DIR / f"{task_id}_transcript.json"
            markdown_cache_file = NOTE_OUTPUT_DIR / f"{task_id}_markdown.md"
            print(audio_cache_file)
            
            # 1. 下载视频（如果需要截图）
            # 【优化】：不再生成网格图，只下载视频备用
            audio_meta = self._download_media(
                downloader=downloader,
                video_url=video_url,
                quality=quality,
                audio_cache_file=audio_cache_file,
                status_phase=TaskStatus.DOWNLOADING,
                platform=platform,
                output_path=output_path,
                screenshot=screenshot,
                video_understanding=False,  # 【优化】：不再提前生成网格图
                video_interval=video_interval,
                grid_size=[],  # 【优化】：不再使用网格图
            )

            # 2. 转写文字（本地 Whisper，0 Token）
            transcript = self._transcribe_audio(
                audio_file=audio_meta.file_path,
                transcript_cache_file=transcript_cache_file,
                status_phase=TaskStatus.TRANSCRIBING,
            )

            # 3. 【文本模型】生成文章（只发文字，不发图片！）
            # 【优化】：不再传 video_img_urls，大幅节省 Token
            markdown = self._summarize_text(
                audio_meta=audio_meta,
                transcript=transcript,
                gpt=text_gpt,
                markdown_cache_file=markdown_cache_file,
                link=link,
                screenshot=screenshot,
                formats=_format or [],
                style=style,
                extras=extras,
                video_img_urls=[],  # 【优化】：不传图片给文本模型！
            )

            # 4. 截图 & 链接替换
            # 【优化】：先截图，再用视觉模型分析
            if _format:
                markdown = self._post_process_markdown(
                    markdown=markdown,
                    video_path=self.video_path,
                    formats=_format,
                    audio_meta=audio_meta,
                    platform=platform,
                    vision_gpt=vision_gpt,  # 【新增】：传入视觉模型
                )

            # 5. 保存记录到数据库
            self._update_status(task_id, TaskStatus.SAVING)
            self._save_metadata(video_id=audio_meta.video_id, platform=platform, task_id=task_id)

            # 6. 完成
            self._update_status(task_id, TaskStatus.SUCCESS)
            logger.info(f"笔记生成成功 (task_id={task_id})")
            return NoteResult(markdown=markdown, transcript=transcript, audio_meta=audio_meta)

        except Exception as exc:
            logger.error(f"生成笔记流程异常 (task_id={task_id})：{exc}", exc_info=True)
            self._update_status(task_id, TaskStatus.FAILED, message=str(exc))
            return None

    @staticmethod
    def delete_note(video_id: str, platform: str) -> int:
        """
        删除数据库中对应 video_id 与 platform 的任务记录

        :param video_id: 视频 ID
        :param platform: 平台标识
        :return: 删除的记录数
        """
        logger.info(f"删除笔记记录 (video_id={video_id}, platform={platform})")
        return delete_task_by_video(video_id, platform)

    # ---------------- 私有方法 ----------------

    def _init_transcriber(self) -> Transcriber:
        """
        根据环境变量 TRANSCRIBER_TYPE 动态获取并实例化转写器
        """
        if self.transcriber_type not in _transcribers:
            logger.error(f"未找到支持的转写器：{self.transcriber_type}")
            raise Exception(f"不支持的转写器：{self.transcriber_type}")

        logger.info(f"使用转写器：{self.transcriber_type}")
        return get_transcriber(transcriber_type=self.transcriber_type)

    def _get_gpt(self, model_name: Optional[str], provider_id: Optional[str]) -> GPT:
        """
        根据 provider_id 获取对应的 GPT 实例
        :param model_name: GPT 模型名称
        :param provider_id: 供应商 ID
        :return: GPT 实例
        """
        provider = ProviderService.get_provider_by_id(provider_id)
        if not provider:
            logger.error(f"[get_gpt] 未找到模型供应商: provider_id={provider_id}")
            raise ProviderError(code=ProviderErrorEnum.NOT_FOUND,message=ProviderErrorEnum.NOT_FOUND.message)
        logger.info(f"创建 GPT 实例 {provider_id}")
        config = ModelConfig(
            api_key=provider["api_key"],
            base_url=provider["base_url"],
            model_name=model_name,
            provider=provider["type"],
            name=provider["name"],
        )
        return GPTFactory().from_config(config)

    def _get_downloader(self, platform: str) -> Downloader:
        """
        根据平台名称获取对应的下载器实例

        :param platform: 平台标识，需在 SUPPORT_PLATFORM_MAP 中
        :return: 对应的 Downloader 子类实例
        """
        downloader_cls = SUPPORT_PLATFORM_MAP.get(platform)
        logger.debug(f"实例化下载器 -  {platform}")
        instance = None
        if not downloader_cls:
            logger.error(f"不支持的平台：{platform}")
            raise NoteError(code=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.code,
                            message=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.message)
        try:
            instance = downloader_cls
        except Exception as e:
            logger.error(f"实例化下载器失败：{e}")


        logger.info(f"使用下载器：{downloader_cls.__class__}")
        return instance

    def _update_status(self, task_id: Optional[str], status: Union[str, TaskStatus], message: Optional[str] = None):
        """
        创建或更新 {task_id}.status.json，记录当前任务状态

        :param task_id: 任务唯一 ID
        :param status: TaskStatus 枚举或自定义状态字符串
        :param message: 可选消息，用于记录失败原因等
        """
        if not task_id:
            return

        NOTE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        status_file = NOTE_OUTPUT_DIR / f"{task_id}.status.json"
        print(f"写入状态文件: {status_file} 当前状态: {status}")
        data = {"status": status.value if isinstance(status, TaskStatus) else status}
        if message:
            data["message"] = message

        try:
            # First create a temporary file
            temp_file = status_file.with_suffix('.tmp')

            # Write to temporary file
            with temp_file.open('w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # Atomic rename operation
            temp_file.replace(status_file)

            print(f"状态文件写入成功: {status_file}")
        except Exception as e:
            logger.error(f"写入状态文件失败 (task_id={task_id})：{e}")
            # Try to write error to file directly as fallback
            try:
                with status_file.open('w', encoding='utf-8') as f:
                    f.write(f"Error writing status: {str(e)}")
            except:
                logger.error(f"写入错误  {e}")

    def _handle_exception(self, task_id, exc):
        logger.error(f"任务异常 (task_id={task_id})", exc_info=True)
        error_message = getattr(exc, 'detail', str(exc))
        if isinstance(error_message, dict):
            try:
                error_message = json.dumps(error_message, ensure_ascii=False)
            except:
                error_message = str(error_message)
        self._update_status(task_id, TaskStatus.FAILED, message=error_message)

    def _download_media(
        self,
        downloader: Downloader,
        video_url: Union[str, HttpUrl],
        quality: DownloadQuality,
        audio_cache_file: Path,
        status_phase: TaskStatus,
        platform: str,
        output_path: Optional[str],
        screenshot: bool,
        video_understanding: bool,
        video_interval: int,
        grid_size: List[int],
    ) -> AudioDownloadResult | None:
        """
        1. 检查音频缓存；若不存在，则根据需要下载音频或视频（若需截图/可视化）。
        2. 如果需要视频，则先下载视频并生成缩略图集，再下载音频。
        3. 返回 AudioDownloadResult

        :param downloader: Downloader 实例
        :param video_url: 视频/音频链接
        :param quality: 音频下载质量
        :param audio_cache_file: 本地缓存 JSON 文件路径
        :param status_phase: 对应的状态枚举，如 TaskStatus.DOWNLOADING
        :param platform: 平台标识
        :param output_path: 下载输出目录（可为 None）
        :param screenshot: 是否需要在笔记中插入截图
        :param video_understanding: 是否需要生成缩略图
        :param video_interval: 视频截帧间隔
        :param grid_size: 缩略图网格尺寸
        :return: AudioDownloadResult 对象
        """
        task_id = audio_cache_file.stem.split("_")[0]
        self._update_status(task_id, status_phase)



        # 判断是否需要下载视频
        # YouTube 特殊处理：强制下载视频，避免多次请求触发验证
        need_video = screenshot or video_understanding or platform == "youtube"
        if need_video:
            try:
                logger.info(f"开始下载视频 (platform={platform}, screenshot={screenshot})")
                video_path_str = downloader.download_video(video_url)
                self.video_path = Path(video_path_str)
                logger.info(f"视频下载完成：{self.video_path}")

                # 若指定了 grid_size，则生成缩略图
                if grid_size:
                    self.video_img_urls=VideoReader(
                        video_path=str(self.video_path),
                        grid_size=tuple(grid_size),
                        frame_interval=video_interval,
                        unit_width=1280,
                        unit_height=720,
                        save_quality=90,
                    ).run()
                else:
                    logger.info("未指定 grid_size，跳过缩略图生成")
            except Exception as exc:
                logger.error(f"视频下载失败：{exc}")

                self._handle_exception(task_id, exc)
                raise
        # 已有缓存，尝试加载
        if audio_cache_file.exists():
            logger.info(f"检测到音频缓存 ({audio_cache_file})，直接读取")
            try:
                data = json.loads(audio_cache_file.read_text(encoding="utf-8"))
                audio_result = AudioDownloadResult(**data)
                # 【修复】：如果需要截图但 video_path 还没设置，尝试恢复
                if need_video and not self.video_path:
                    # 优先用 video_path，否则用 file_path（如果是视频文件）
                    if audio_result.video_path:
                        self.video_path = Path(audio_result.video_path)
                    elif audio_result.file_path and audio_result.file_path.endswith('.mp4'):
                        self.video_path = Path(audio_result.file_path)
                    if self.video_path:
                        logger.info(f"从缓存恢复视频路径：{self.video_path}")
                return audio_result
            except Exception as e:
                logger.warning(f"读取音频缓存失败，将重新下载：{e}")
        # 下载音频
        try:
            # 如果已经下载了视频，直接从视频提取音频（避免再次请求 YouTube 触发验证）
            if self.video_path and self.video_path.exists() and platform == "youtube":
                logger.info("从已下载的视频中提取音频（避免重复请求 YouTube）")
                # 使用视频所在目录作为输出目录
                audio_output_dir = Path(output_path) if output_path else self.video_path.parent
                audio_path = audio_output_dir / f"{self.video_path.stem}.m4a"
                
                # 用 ffmpeg 提取音频
                import subprocess
                ffmpeg_cmd = [
                    "ffmpeg", "-y", "-i", str(self.video_path),
                    "-vn", "-acodec", "copy", str(audio_path)
                ]
                result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    logger.warning(f"ffmpeg 提取音频失败，尝试重新编码: {result.stderr}")
                    # 如果 copy 失败，尝试重新编码
                    ffmpeg_cmd = [
                        "ffmpeg", "-y", "-i", str(self.video_path),
                        "-vn", "-acodec", "aac", "-b:a", "128k", str(audio_path)
                    ]
                    subprocess.run(ffmpeg_cmd, check=True)
                
                # 获取视频信息（从之前下载时的 info）
                from app.utils.url_parser import extract_video_id
                video_id = extract_video_id(video_url, platform)
                
                audio = AudioDownloadResult(
                    file_path=str(audio_path),
                    title=self.video_path.stem,  # 临时用文件名
                    duration=0,
                    cover_url=None,
                    platform=platform,
                    video_id=video_id,
                    raw_info={},
                    video_path=str(self.video_path)
                )
            else:
                logger.info("开始下载音频")
                audio = downloader.download(
                    video_url=video_url,
                    quality=quality,
                    output_dir=output_path,
                    need_video=need_video,
                )
            # 缓存 audio 元信息到本地 JSON
            audio_cache_file.write_text(json.dumps(asdict(audio), ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"音频下载并缓存成功 ({audio_cache_file})")
            return audio
        except Exception as exc:
            logger.error(f"音频下载失败：{exc}")
            self._handle_exception(task_id, exc)
            raise


    def _transcribe_audio(
        self,
        audio_file: str,
        transcript_cache_file: Path,
        status_phase: TaskStatus,
    ) -> TranscriptResult | None:
        """
        1. 检查转写缓存；若存在则尝试加载，否则调用转写器生成并缓存。
        2. 返回 TranscriptResult 对象

        :param audio_file: 音频文件本地路径
        :param transcript_cache_file: 转写结果缓存路径
        :param status_phase: 对应的状态枚举，如 TaskStatus.TRANSCRIBING
        :return: TranscriptResult 对象
        """
        task_id = transcript_cache_file.stem.split("_")[0]
        self._update_status(task_id, status_phase)

        # 已有缓存，尝试加载
        if transcript_cache_file.exists():
            logger.info(f"检测到转写缓存 ({transcript_cache_file})，尝试读取")
            try:
                data = json.loads(transcript_cache_file.read_text(encoding="utf-8"))
                segments = [TranscriptSegment(**seg) for seg in data.get("segments", [])]
                return TranscriptResult(language=data["language"], full_text=data["full_text"], segments=segments)
            except Exception as e:
                logger.warning(f"加载转写缓存失败，将重新转写：{e}")

        # 调用转写器
        try:
            logger.info("开始转写音频")
            transcript = self.transcriber.transcript(file_path=audio_file)
            transcript_cache_file.write_text(json.dumps(asdict(transcript), ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"转写并缓存成功 ({transcript_cache_file})")
            return transcript
        except Exception as exc:
            logger.error(f"音频转写失败：{exc}")
            self._handle_exception(task_id, exc)
            raise

    def _summarize_text(
        self,
        audio_meta: AudioDownloadResult,
        transcript: TranscriptResult,
        gpt: GPT,
        markdown_cache_file: Path,
        link: bool,
        screenshot: bool,
        formats: List[str],
        style: Optional[str],
        extras: Optional[str],
            video_img_urls: List[str],
    ) -> str | None:
        """
        调用 GPT 对转写结果进行总结，生成 Markdown 文本并缓存。

        :param audio_meta: AudioDownloadResult 元信息
        :param transcript: TranscriptResult 转写结果
        :param gpt: GPT 实例
        :param markdown_cache_file: Markdown 缓存路径
        :param link: 是否在笔记中插入链接
        :param screenshot: 是否在笔记中生成截图占位
        :param formats: 包含 'link' 或 'screenshot' 的列表
        :param style: GPT 输出风格
        :param extras: GPT 额外参数
        :return: 生成的 Markdown 字符串
        """
        task_id = markdown_cache_file.stem
        self._update_status(task_id, TaskStatus.SUMMARIZING)

        source = GPTSource(
            title=audio_meta.title,
            segment=transcript.segments,
            tags=audio_meta.raw_info.get("tags", []),
            screenshot=screenshot,
            video_img_urls=video_img_urls,
            link=link,
            _format=formats,
            style=style,
            extras=extras,
        )

        try:
            markdown = gpt.summarize(source)
            markdown_cache_file.write_text(markdown, encoding="utf-8")
            logger.info(f"GPT 总结并缓存成功 ({markdown_cache_file})")
            return markdown
        except Exception as exc:
            logger.error(f"GPT 总结失败：{exc}")
            self._handle_exception(task_id, exc)
            raise

    def _post_process_markdown(
        self,
        markdown: str,
        video_path: Optional[Path],
        formats: List[str],
        audio_meta: AudioDownloadResult,
        platform: str,
        vision_gpt: Optional[GPT] = None,
    ) -> str:
        """
        对生成的 Markdown 做后期处理：插入截图和/或插入链接。
        
        【优化后的流程】：
        1. 根据 *Screenshot-[mm:ss] 标记截图
        2. 如果有视觉模型，用视觉模型分析截图是否合适
        3. 替换标记为最终图片

        :param markdown: 原始 Markdown 字符串
        :param video_path: 本地视频路径（可为 None）
        :param formats: 包含 'link' 或 'screenshot' 的列表
        :param audio_meta: AudioDownloadResult 元信息，用于链接替换
        :param platform: 平台标识，用于链接替换
        :param vision_gpt: 视觉模型 GPT 实例（可选，用于分析截图）
        :return: 处理后的 Markdown 字符串
        """
        logger.info(f"📸 后处理检查: formats={formats}, video_path={video_path}, 'screenshot' in formats={'screenshot' in formats}")
        if "screenshot" in formats and video_path:
            try:
                markdown = self._insert_screenshots(markdown, video_path, vision_gpt)
            except Exception as exc:
                logger.warning(f"截图插入失败，跳过该步骤: {exc}")

        if "link" in formats:
            try:
                markdown = replace_content_markers(markdown, video_id=audio_meta.video_id, platform=platform)
            except Exception as e:
                logger.warning(f"链接插入失败，跳过该步骤：{e}")

        return markdown

    def _insert_screenshots(self, markdown: str, video_path: Path, vision_gpt: Optional[GPT] = None) -> str | None | Any:
        """
        扫描 Markdown 文本中所有 Screenshot 标记，并替换为实际生成的截图链接。
        
        【优化后的流程】：
        1. 根据标记截图（本地 ffmpeg，0 Token）
        2. 如果有视觉模型，分析截图是否合适
        3. 替换标记为最终图片

        :param markdown: 含有 *Screenshot-mm:ss 或 Screenshot-[mm:ss] 标记的 Markdown 文本
        :param video_path: 本地视频文件路径
        :param vision_gpt: 视觉模型 GPT 实例（可选）
        :return: 替换后的 Markdown 字符串
        """
        matches: List[Tuple[str, int]] = self._extract_screenshot_timestamps(markdown)
        logger.info(f"找到 {len(matches)} 个截图标记")
        
        for idx, (marker, ts) in enumerate(matches):
            try:
                # 1. 截图
                img_path = generate_screenshot(str(video_path), str(IMAGE_OUTPUT_DIR), ts, idx)
                filename = Path(img_path).name
                img_url = f"{IMAGE_BASE_URL.rstrip('/')}/{filename}"
                
                # 2. 如果有视觉模型，分析截图质量
                if vision_gpt:
                    try:
                        analysis = self._analyze_screenshot_with_vision(vision_gpt, img_path, marker)
                        logger.info(f"视觉模型分析截图 {idx}: {analysis[:100]}...")
                        # 如果视觉模型认为截图不合适，可以在这里重新截图
                        # 目前先简单记录分析结果，后续可以扩展
                    except Exception as ve:
                        logger.warning(f"视觉模型分析失败: {ve}")
                
                # 3. 替换标记
                markdown = markdown.replace(marker, f"![]({img_url})", 1)
                logger.info(f"截图 {idx} 完成: {img_url}")
                
            except Exception as exc:
                logger.warning(f"生成截图失败 (timestamp={ts})：{exc}，移除该截图标记")
                markdown = markdown.replace(marker, "", 1)
        return markdown
    
    def _analyze_screenshot_with_vision(self, vision_gpt: GPT, img_path: str, context: str) -> str:
        """
        使用视觉模型分析截图是否合适
        
        :param vision_gpt: 视觉模型 GPT 实例
        :param img_path: 截图本地路径
        :param context: 截图上下文（标记内容）
        :return: 分析结果
        """
        import base64
        
        # 读取图片并转为 base64
        with open(img_path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode("utf-8")
        
        # 构建视觉模型请求
        messages = [{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"请分析这张截图的质量。这是一个视频教程的截图，用于文章配图。\n\n请简要回答：\n1. 图片是否清晰？\n2. 图片内容是否有意义（不是空白、过渡画面）？\n3. 如果不合适，建议向前或向后调整几秒？\n\n请用一句话总结。"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{img_base64}",
                        "detail": "low"  # 使用低分辨率节省 Token
                    }
                }
            ]
        }]
        
        response = vision_gpt.client.chat.completions.create(
            model=vision_gpt.model,
            messages=messages,
            max_tokens=100  # 限制输出长度
        )
        
        return response.choices[0].message.content.strip()

    @staticmethod
    def _extract_screenshot_timestamps(markdown: str) -> List[Tuple[str, int]]:
        """
        从 Markdown 文本中提取所有截图标记，支持多种格式：
        - *Screenshot-[mm:ss]*
        - *Screenshot-mm:ss*
        - Screenshot-[mm:ss]
        - 截图-[mm:ss]
        - 截图[mm:ss]
        
        返回 [(原始标记文本, 时间戳秒数), ...] 列表。

        :param markdown: 原始 Markdown 文本
        :return: 标记与对应时间戳秒数的列表
        """
        # 支持英文和中文格式：
        # 英文: *Screenshot-[00:23]* 或 Screenshot-00:23
        # 中文: 截图-[00:23] 或 截图[00:23] 或 截图-00:23
        pattern = r"(?:\*?Screenshot-\[?(\d{1,2}):(\d{2})\]?\*?|截图-?\[?(\d{1,2}):(\d{2})\]?)"
        results: List[Tuple[str, int]] = []
        for match in re.finditer(pattern, markdown):
            # 英文格式用 group(1)(2)，中文格式用 group(3)(4)
            mm = match.group(1) or match.group(3)
            ss = match.group(2) or match.group(4)
            total_seconds = int(mm) * 60 + int(ss)
            results.append((match.group(0), total_seconds))
        return results

    def _save_metadata(self, video_id: str, platform: str, task_id: str) -> None:
        """
        将生成的笔记任务记录插入数据库

        :param video_id: 视频 ID
        :param platform: 平台标识
        :param task_id: 任务 ID
        """
        try:
            insert_video_task(video_id=video_id, platform=platform, task_id=task_id)
            logger.info(f"已保存任务记录到数据库 (video_id={video_id}, platform={platform}, task_id={task_id})")
        except Exception as e:
            logger.error(f"保存任务记录失败：{e}")