"""
WordPress 发布 API 路由
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
import logging
import re

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/wordpress", tags=["WordPress发布"])

processing_status = {}


class VideoTask(BaseModel):
    url: str
    platform: str = "youtube"
    priority: int = 0


class BatchPublishRequest(BaseModel):
    videos: List[VideoTask]
    auto_publish: bool = False
    screenshot: bool = True
    style: str = "normal"
    provider_id: str = None
    model_name: str = None


@router.post("/publish/batch")
async def publish_batch_videos(request: BatchPublishRequest):
    from app.services.wordpress_publisher import quick_publish_videos
    
    video_urls = [v.url for v in sorted(request.videos, key=lambda x: x.priority)]
    platform = request.videos[0].platform if request.videos else "youtube"
    
    result = quick_publish_videos(
        video_urls=video_urls,
        platform=platform,
        auto_publish=request.auto_publish,
        provider_id=request.provider_id,
        model_name=request.model_name
    )
    return result


class SinglePublishRequest(BaseModel):
    title: str
    content: str
    status: str = "publish"
    provider_id: Optional[str] = None
    model_name: Optional[str] = None
    backend_url: Optional[str] = None


def extract_seo_metadata(content: str) -> tuple:
    """从内容中提取SEO元数据并移除"""
    seo_data = {
        'seo_title': '',
        'seo_description': '',
        'focus_keyword': '',
        'keywords': ''
    }
    
    logger.info(f"开始提取SEO元数据，内容长度: {len(content)}")
    
    # 检查内容末尾是否包含SEO块
    if '---SEO-METADATA---' in content:
        logger.info("检测到SEO-METADATA标记")
    else:
        logger.info("未检测到SEO-METADATA标记")
    
    # 匹配SEO块 - 精确匹配实际格式
    # 实际格式: ---SEO-METADATA---\n内容\n---END-SEO---
    seo_pattern = r'---SEO-METADATA---\s*\n(.*?)\n---END-SEO---'
    
    match = re.search(seo_pattern, content, re.DOTALL)
    
    if match:
        seo_block = match.group(1)
        logger.info(f"找到SEO块内容: {seo_block}")
        
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
        
        # 移除整个SEO块（包括前面的分隔线 ---）
        # 实际内容格式: ...\n\n---\n\n---SEO-METADATA---\n...\n---END-SEO---
        clean_patterns = [
            r'\n*---\s*\n+---SEO-METADATA---\s*\n.*?\n---END-SEO---\s*$',  # 带前导分隔线
            r'\n*---SEO-METADATA---\s*\n.*?\n---END-SEO---\s*$',  # 不带前导分隔线
        ]
        
        clean_content = content
        for pattern in clean_patterns:
            new_content = re.sub(pattern, '', clean_content, flags=re.DOTALL)
            if new_content != clean_content:
                clean_content = new_content
                logger.info(f"使用模式 {pattern} 成功移除SEO块")
                break
        
        clean_content = clean_content.rstrip()
        logger.info(f"SEO数据提取成功: {seo_data}")
        logger.info(f"清理后内容长度: {len(clean_content)}")
    else:
        clean_content = content
        logger.info("未找到SEO元数据块")
    
    return clean_content, seo_data


def convert_image_urls(content: str, backend_url: str = None) -> str:
    if not backend_url:
        backend_url = "http://localhost:8483"
    backend_url = backend_url.rstrip('/')
    
    def replace_md_img(match):
        alt = match.group(1)
        path = match.group(2)
        if path.startswith('/static/') or path.startswith('static/'):
            path = path.lstrip('/')
            return f'![{alt}]({backend_url}/{path})'
        return match.group(0)
    
    content = re.sub(r'!\[([^\]]*)\]\((/static/[^)]+)\)', replace_md_img, content)
    content = re.sub(r'!\[([^\]]*)\]\((static/[^)]+)\)', replace_md_img, content)
    return content


def remove_screenshot_placeholders(content: str) -> str:
    content = re.sub(r'\*Screenshot-\[\d+:\d+\]\*\s*', '', content)
    return content


@router.post("/publish/single")
async def publish_single_article(request: SinglePublishRequest):
    from app.services.wordpress_publisher import create_publisher_from_env, ArticleCategory
    from app.gpt.gpt_factory import GPTFactory
    from app.services.provider import ProviderService
    from app.models.model_config import ModelConfig
    import markdown
    
    logger.info(f"收到发布请求: title={request.title}, status={request.status}")
    
    llm_client = None
    if request.provider_id and request.model_name:
        try:
            provider = ProviderService.get_provider_by_id(request.provider_id)
            if provider and isinstance(provider, dict):
                config = ModelConfig(
                    api_key=provider.get('api_key', ''),
                    base_url=provider.get('base_url', ''),
                    model_name=request.model_name
                )
                gpt = GPTFactory.from_config(config)
                
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
                llm_client = LLMWrapper(gpt, request.model_name)
        except Exception as e:
            logger.error(f"创建LLM客户端失败: {e}")
    
    publisher = create_publisher_from_env(llm_client=llm_client)
    
    content = request.content
    content = re.sub(r'^```(?:markdown)?\s*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'\n```\s*$', '', content, flags=re.MULTILINE)
    
    # 提取SEO元数据
    content, seo_data = extract_seo_metadata(content)
    logger.info(f"提取的SEO数据: {seo_data}")
    
    # 转换图片URL
    backend_url = request.backend_url or "http://localhost:8483"
    content = convert_image_urls(content, backend_url)
    
    # 移除截图占位符
    content = remove_screenshot_placeholders(content)
    
    # 分类判断
    try:
        category = publisher.classify_article(request.title, content)
        logger.info(f"文章分类结果: {category}")
    except Exception as e:
        logger.error(f"分类判断失败: {e}")
        category = ArticleCategory.TUTORIAL
    
    # 使用SEO标题或优化标题
    if seo_data.get('seo_title'):
        optimized_title = seo_data['seo_title']
    else:
        try:
            optimized_title = publisher.optimize_title(request.title, content)
        except Exception as e:
            logger.error(f"标题优化失败: {e}")
            optimized_title = request.title
    
    # 上传本地图片到WordPress媒体库并替换URL
    logger.info("处理本地图片...")
    content = publisher.process_local_images(content)
    
    # 转换为HTML
    html_content = markdown.markdown(
        content,
        extensions=[
            'markdown.extensions.tables',
            'markdown.extensions.fenced_code',
            'markdown.extensions.nl2br',
        ]
    )
    
    # 发布文章
    try:
        logger.info(f"开始发布文章: {optimized_title}")
        result = publisher.publish_to_wordpress(
            title=optimized_title,
            content=html_content,
            category=category,
            status=request.status,
            seo_data=seo_data
        )
        logger.info(f"发布结果: {result}")
    except Exception as e:
        logger.error(f"发布过程异常: {e}")
        import traceback
        logger.error(traceback.format_exc())
        result = {"success": False, "error": str(e)}
    
    if not isinstance(result, dict):
        result = {"success": False, "error": "发布结果格式错误"}
    
    return {
        "success": result.get("success", False),
        "post_id": result.get("post_id"),
        "post_url": result.get("post_url"),
        "title": optimized_title,
        "original_title": request.title,
        "category": category.value if hasattr(category, 'value') else str(category),
        "seo_data": seo_data,
        "error": result.get("error")
    }


@router.get("/categories")
async def get_categories():
    from app.services.wordpress_publisher import create_publisher_from_env
    import requests
    
    publisher = create_publisher_from_env()
    session = requests.Session()
    session.trust_env = False
    
    response = session.get(
        f"{publisher.config.site_url}/wp-json/wp/v2/categories",
        auth=publisher.auth,
        timeout=10
    )
    return response.json()
