# app/routers/note.py
import json
import os
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel, validator, field_validator
from dataclasses import asdict

from app.db.video_task_dao import get_task_by_video
from app.enmus.exception import NoteErrorEnum
from app.enmus.note_enums import DownloadQuality
from app.exceptions.note import NoteError
from app.services.note import NoteGenerator, logger
from app.utils.response import ResponseWrapper as R
from app.utils.url_parser import extract_video_id
from app.validators.video_url_validator import is_supported_video_url
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
import httpx
from app.enmus.task_status_enums import TaskStatus

# from app.services.downloader import download_raw_audio
# from app.services.whisperer import transcribe_audio

router = APIRouter()


class RecordRequest(BaseModel):
    video_id: str
    platform: str


class VideoRequest(BaseModel):
    video_url: str
    platform: str
    quality: DownloadQuality
    screenshot: Optional[bool] = False
    link: Optional[bool] = False
    model_name: str
    provider_id: str
    vision_model_name: Optional[str] = None  # 视觉模型名称（可选）
    vision_provider_id: Optional[str] = None  # 视觉模型供应商ID（可选）
    task_id: Optional[str] = None
    format: Optional[list] = []
    style: str = None
    extras: Optional[str]=None
    video_understanding: Optional[bool] = False
    video_interval: Optional[int] = 0
    grid_size: Optional[list] = []

    @field_validator("video_url")
    def validate_supported_url(cls, v):
        url = str(v)
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https"):
            # 是网络链接，继续用原有平台校验
            if not is_supported_video_url(url):
                raise NoteError(code=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.code,
                                message=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.message)

        return v


NOTE_OUTPUT_DIR = os.getenv("NOTE_OUTPUT_DIR", "note_results")
UPLOAD_DIR = "uploads"


def save_note_to_file(task_id: str, note):
    os.makedirs(NOTE_OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.json"), "w", encoding="utf-8") as f:
        json.dump(asdict(note), f, ensure_ascii=False, indent=2)


def run_note_task(task_id: str, video_url: str, platform: str, quality: DownloadQuality,
                  link: bool = False, screenshot: bool = False, model_name: str = None, provider_id: str = None,
                  vision_model_name: str = None, vision_provider_id: str = None,
                  _format: list = None, style: str = None, extras: str = None, video_understanding: bool = False,
                  video_interval=0, grid_size=[]
                  ):

    if not model_name or not provider_id:
        raise HTTPException(status_code=400, detail="请选择模型和提供者")

    note = NoteGenerator().generate(
        video_url=video_url,
        platform=platform,
        quality=quality,
        task_id=task_id,
        model_name=model_name,
        provider_id=provider_id,
        vision_model_name=vision_model_name,
        vision_provider_id=vision_provider_id,
        link=link,
        _format=_format,
        style=style,
        extras=extras,
        screenshot=screenshot,
        video_understanding=video_understanding,
        video_interval=video_interval,
        grid_size=grid_size
    )
    logger.info(f"Note generated: {task_id}")
    if not note or not note.markdown:
        logger.warning(f"任务 {task_id} 执行失败，跳过保存")
        return
    save_note_to_file(task_id, note)



@router.post('/delete_task')
def delete_task(data: RecordRequest):
    try:
        # TODO: 待持久化完成
        # NoteGenerator().delete_note(video_id=data.video_id, platform=data.platform)
        return R.success(msg='删除成功')
    except Exception as e:
        return R.error(msg=e)


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_location = os.path.join(UPLOAD_DIR, file.filename)

    with open(file_location, "wb+") as f:
        f.write(await file.read())

    # 假设你静态目录挂载了 /uploads
    return R.success({"url": f"/uploads/{file.filename}"})


@router.post("/generate_note")
def generate_note(data: VideoRequest, background_tasks: BackgroundTasks):
    try:

        video_id = extract_video_id(data.video_url, data.platform)
        # if not video_id:
        #     raise HTTPException(status_code=400, detail="无法提取视频 ID")
        # existing = get_task_by_video(video_id, data.platform)
        # if existing:
        #     return R.error(
        #         msg='笔记已生成，请勿重复发起',
        #
        #     )
        if data.task_id:
            # 如果传了task_id，说明是重试！
            task_id = data.task_id
            # 更新之前的状态
            NoteGenerator()._update_status(task_id, TaskStatus.PENDING)
            logger.info(f"重试模式，复用已有 task_id={task_id}")
        else:
            # 正常新建任务
            task_id = str(uuid.uuid4())

        background_tasks.add_task(run_note_task, task_id, data.video_url, data.platform, data.quality, data.link,
                                  data.screenshot, data.model_name, data.provider_id, 
                                  data.vision_model_name, data.vision_provider_id,
                                  data.format, data.style,
                                  data.extras, data.video_understanding, data.video_interval, data.grid_size)
        return R.success({"task_id": task_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/task_status/{task_id}")
def get_task_status(task_id: str):
    status_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.status.json")
    result_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.json")

    # 优先读状态文件
    if os.path.exists(status_path):
        with open(status_path, "r", encoding="utf-8") as f:
            status_content = json.load(f)

        status = status_content.get("status")
        message = status_content.get("message", "")

        if status == TaskStatus.SUCCESS.value:
            # 成功状态的话，继续读取最终笔记内容
            if os.path.exists(result_path):
                with open(result_path, "r", encoding="utf-8") as rf:
                    result_content = json.load(rf)
                return R.success({
                    "status": status,
                    "result": result_content,
                    "message": message,
                    "task_id": task_id
                })
            else:
                # 理论上不会出现，保险处理
                return R.success({
                    "status": TaskStatus.PENDING.value,
                    "message": "任务完成，但结果文件未找到",
                    "task_id": task_id
                })

        if status == TaskStatus.FAILED.value:
            return R.error(message or "任务失败", code=500)

        # 处理中状态
        return R.success({
            "status": status,
            "message": message,
            "task_id": task_id
        })

    # 没有状态文件，但有结果
    if os.path.exists(result_path):
        with open(result_path, "r", encoding="utf-8") as f:
            result_content = json.load(f)
        return R.success({
            "status": TaskStatus.SUCCESS.value,
            "result": result_content,
            "task_id": task_id
        })

    # 什么都没有，默认PENDING
    return R.success({
        "status": TaskStatus.PENDING.value,
        "message": "任务排队中",
        "task_id": task_id
    })


@router.get("/image_proxy")
async def image_proxy(request: Request, url: str):
    headers = {
        "Referer": "https://www.bilibili.com/",
        "User-Agent": request.headers.get("User-Agent", ""),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)

            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail="图片获取失败")

            content_type = resp.headers.get("Content-Type", "image/jpeg")
            return StreamingResponse(
                resp.aiter_bytes(),
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",  #  缓存一天
                    "Content-Type": content_type,
                }
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== 批量处理 API ==============

# 批量任务状态存储
batch_tasks = {}


class BatchGenerateRequest(BaseModel):
    """批量生成+发布请求"""
    video_urls: list  # 多个视频链接
    platform: str
    quality: str = "medium"
    model_name: str
    provider_id: str
    format: list = []
    style: str = "minimal"
    extras: str = None
    auto_publish: bool = False  # True=直接发布，False=存草稿


def run_batch_task(batch_id: str, video_urls: list, platform: str, quality: str,
                   model_name: str, provider_id: str, _format: list, style: str,
                   extras: str, auto_publish: bool):
    """
    批量处理任务：逐个生成笔记并发布到 WordPress
    """
    from app.services.wordpress_publisher import create_publisher_from_env, ArticleCategory
    from app.gpt.gpt_factory import GPTFactory
    from app.services.provider import ProviderService
    from app.models.model_config import ModelConfig
    import markdown
    import re
    
    total = len(video_urls)
    results = []
    
    # 更新批量任务状态
    batch_tasks[batch_id] = {
        "status": "PROCESSING",
        "total": total,
        "completed": 0,
        "success": 0,
        "failed": 0,
        "results": []
    }
    
    # 创建 LLM 客户端（用于分类和标题优化）
    llm_client = None
    try:
        provider = ProviderService.get_provider_by_id(provider_id)
        if provider:
            config = ModelConfig(
                name=model_name,  # 展示名
                provider=provider_id,  # 提供商ID
                api_key=provider.get('api_key', ''),
                base_url=provider.get('base_url', ''),
                model_name=model_name
            )
            gpt = GPTFactory().from_config(config)
            
            class LLMWrapper:
                def __init__(self, gpt_client, model):
                    self.client = gpt_client.client
                    self.model = model
                def chat(self, prompt: str) -> str:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.7
                    )
                    return response.choices[0].message.content.strip()
            llm_client = LLMWrapper(gpt, model_name)
            logger.info(f"LLM客户端创建成功: {model_name}")
    except Exception as e:
        logger.error(f"创建LLM客户端失败: {e}")
    
    publisher = create_publisher_from_env(llm_client=llm_client)
    
    for i, video_url in enumerate(video_urls):
        video_url = video_url.strip()
        if not video_url:
            continue
            
        task_id = str(uuid.uuid4())
        logger.info(f"[批量 {batch_id}] 处理 {i+1}/{total}: {video_url}")
        
        try:
            # 1. 生成笔记
            screenshot = "screenshot" in _format
            link = "link" in _format
            
            note = NoteGenerator().generate(
                video_url=video_url,
                platform=platform,
                quality=DownloadQuality(quality),
                task_id=task_id,
                model_name=model_name,
                provider_id=provider_id,
                link=link,
                _format=_format,
                style=style,
                extras=extras,
                screenshot=screenshot,
            )
            
            if not note or not note.markdown:
                raise Exception("笔记生成失败")
            
            # 2. 发布到 WordPress
            title = note.audio_meta.title if note.audio_meta else "未命名文章"
            content = note.markdown
            
            # 清理 Markdown
            content = re.sub(r'^```(?:markdown)?\s*\n', '', content, flags=re.MULTILINE)
            content = re.sub(r'\n```\s*$', '', content, flags=re.MULTILINE)
            
            # 提取SEO元数据
            seo_data = {'seo_title': '', 'seo_description': '', 'focus_keyword': '', 'keywords': ''}
            seo_pattern = r'---SEO-METADATA---\s*\n(.*?)\n---END-SEO---'
            seo_match = re.search(seo_pattern, content, re.DOTALL)
            if seo_match:
                seo_block = seo_match.group(1)
                for line in seo_block.strip().split('\n'):
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
                content = re.sub(r'\n*---\s*\n+---SEO-METADATA---.*?---END-SEO---\s*$', '', content, flags=re.DOTALL)
                content = re.sub(r'\n*---SEO-METADATA---.*?---END-SEO---\s*$', '', content, flags=re.DOTALL)
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
            )
            
            results.append({
                "video_url": video_url,
                "success": result.get("success", False),
                "title": optimized_title,
                "post_url": result.get("post_url"),
                "error": result.get("error")
            })
            
            if result.get("success"):
                batch_tasks[batch_id]["success"] += 1
            else:
                batch_tasks[batch_id]["failed"] += 1
                
        except Exception as e:
            logger.error(f"[批量 {batch_id}] 处理失败 {video_url}: {e}")
            results.append({
                "video_url": video_url,
                "success": False,
                "title": "",
                "post_url": None,
                "error": str(e)
            })
            batch_tasks[batch_id]["failed"] += 1
        
        batch_tasks[batch_id]["completed"] += 1
        batch_tasks[batch_id]["results"] = results
    
    # 完成
    batch_tasks[batch_id]["status"] = "COMPLETED"
    logger.info(f"[批量 {batch_id}] 完成！成功 {batch_tasks[batch_id]['success']}/{total}")


@router.post("/batch_generate_publish")
def batch_generate_publish(data: BatchGenerateRequest, background_tasks: BackgroundTasks):
    """
    批量生成笔记并发布到 WordPress
    一键处理多个视频链接，全自动！
    """
    if not data.video_urls:
        raise HTTPException(status_code=400, detail="请提供视频链接")
    
    batch_id = str(uuid.uuid4())
    
    background_tasks.add_task(
        run_batch_task,
        batch_id,
        data.video_urls,
        data.platform,
        data.quality,
        data.model_name,
        data.provider_id,
        data.format,
        data.style,
        data.extras,
        data.auto_publish
    )
    
    return R.success({
        "batch_id": batch_id,
        "total": len(data.video_urls),
        "message": f"批量任务已提交，共 {len(data.video_urls)} 个视频"
    })


@router.get("/batch_status/{batch_id}")
def get_batch_status(batch_id: str):
    """获取批量任务状态"""
    if batch_id not in batch_tasks:
        return R.success({
            "status": "PENDING",
            "message": "任务排队中"
        })
    
    return R.success(batch_tasks[batch_id])
