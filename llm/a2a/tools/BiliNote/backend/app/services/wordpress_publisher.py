"""
WordPress 自动发布模块
功能：
1. 批量处理视频链接
2. 生成文章后由大模型判断分类（使用指南/AI资讯）
3. 自动发布到 WordPress
"""

import os
import re
import json
import logging
import requests
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# AI品牌标签映射 - slug -> WordPress标签ID
BRAND_TAG_IDS = {
    'gemini': 43,
    'gpt': 44,
    'claude': 45,
    'grok': 46
}


class ArticleCategory(Enum):
    """文章分类枚举"""
    TUTORIAL = "tutorial"      # 使用指南 (ID: 8)
    AI_NEWS = "ai_news"        # 热点资讯 (ID: 7)
    HOT_TOPIC = "hot_topic"    # 热门专题 (ID: 34)
    FAQ = "faq"                # 常见问题 (ID: 1)
    UNKNOWN = "unknown"


@dataclass
class WordPressConfig:
    """WordPress 配置"""
    site_url: str              # WordPress 站点地址
    username: str              # 用户名
    app_password: str          # 应用密码（非登录密码）
    tutorial_category_id: int  # 使用指南分类ID (8)
    ai_news_category_id: int   # 热点资讯分类ID (7)
    hot_topic_category_id: int = 34  # 热门专题分类ID (34)
    faq_category_id: int = 1   # 常见问题分类ID (1)


@dataclass
class ArticleTask:
    """文章任务"""
    video_url: str
    platform: str = "youtube"  # youtube/bilibili/douyin
    priority: int = 0          # 优先级，数字越小越先处理


@dataclass
class PublishResult:
    """发布结果"""
    success: bool
    video_url: str
    title: str
    category: str
    post_id: Optional[int] = None
    post_url: Optional[str] = None
    error: Optional[str] = None


class WordPressPublisher:
    """WordPress 发布器"""
    
    def __init__(self, config: WordPressConfig, llm_client: Any = None):
        """
        初始化发布器
        
        Args:
            config: WordPress 配置
            llm_client: 大模型客户端（用于分类判断）
        """
        self.config = config
        self.llm_client = llm_client
        self.api_base = f"{config.site_url}/wp-json/wp/v2"
        self.auth = (config.username, config.app_password)
        
    def classify_article(self, title: str, content: str) -> ArticleCategory:
        """
        使用大模型判断文章分类
        
        Args:
            title: 文章标题
            content: 文章内容
            
        Returns:
            ArticleCategory: 分类结果
        """
        if not self.llm_client:
            # 简单关键词匹配作为后备
            return self._keyword_classify(title, content)
        
        prompt = f"""请判断以下文章应该归类到哪个分类：
        
分类选项：
1. tutorial（使用指南）- 教程、操作指南、配置说明、工具使用方法等
2. ai_news（热点资讯）- AI新闻、技术动态、产品发布、行业趋势等
3. hot_topic（热门专题）- 深度分析、专题报道、系列文章、综合评测等
4. faq（常见问题）- 问答、故障排除、常见错误解决等

文章标题：{title}

文章内容摘要（前500字）：
{content[:500]}

请只返回分类名称（tutorial/ai_news/hot_topic/faq），不要返回其他内容。"""

        try:
            response = self.llm_client.chat(prompt)
            category_str = response.strip().lower()
            
            if "tutorial" in category_str:
                return ArticleCategory.TUTORIAL
            elif "ai_news" in category_str or "news" in category_str:
                return ArticleCategory.AI_NEWS
            elif "hot_topic" in category_str or "hot" in category_str:
                return ArticleCategory.HOT_TOPIC
            elif "faq" in category_str:
                return ArticleCategory.FAQ
            else:
                return self._keyword_classify(title, content)
        except Exception as e:
            logger.error(f"LLM分类失败: {e}")
            return self._keyword_classify(title, content)
    
    def _keyword_classify(self, title: str, content: str) -> ArticleCategory:
        """关键词分类（后备方案）"""
        text = (title + content).lower()
        
        tutorial_keywords = [
            "教程", "指南", "如何", "怎么", "配置", "安装", "设置", "使用",
            "tutorial", "guide", "how to", "setup", "install", "configure"
        ]
        
        news_keywords = [
            "发布", "更新", "新版", "动态", "资讯", "新闻", "宣布", "推出",
            "release", "update", "news", "announce", "launch", "new"
        ]
        
        hot_topic_keywords = [
            "深度", "专题", "分析", "评测", "对比", "盘点", "系列", "全面",
            "deep", "analysis", "review", "comparison", "series"
        ]
        
        faq_keywords = [
            "问题", "解决", "错误", "故障", "为什么", "怎么办", "无法",
            "faq", "error", "problem", "issue", "fix", "solve"
        ]
        
        tutorial_score = sum(1 for kw in tutorial_keywords if kw in text)
        news_score = sum(1 for kw in news_keywords if kw in text)
        hot_topic_score = sum(1 for kw in hot_topic_keywords if kw in text)
        faq_score = sum(1 for kw in faq_keywords if kw in text)
        
        scores = {
            ArticleCategory.TUTORIAL: tutorial_score,
            ArticleCategory.AI_NEWS: news_score,
            ArticleCategory.HOT_TOPIC: hot_topic_score,
            ArticleCategory.FAQ: faq_score,
        }
        
        best_category = max(scores, key=scores.get)
        if scores[best_category] > 0:
            return best_category
        return ArticleCategory.TUTORIAL  # 默认归类为使用指南
    
    def optimize_title(self, original_title: str, content: str) -> str:
        """
        使用大模型优化标题 - 生成吸引眼球的爆款标题
        
        Args:
            original_title: 原始标题
            content: 文章内容
            
        Returns:
            str: 优化后的标题
        """
        if not self.llm_client:
            return original_title
        
        prompt = f"""你是一个专业的自媒体标题优化专家。请为以下文章生成一个极具吸引力的中文标题。

【标题创作技巧】选择以下一种或组合使用：
1. 🔥 情绪钩子：加入好奇、惊讶、紧迫感（如"震惊！"、"终于！"、"原来..."）
2. ❌ 常见错误：指出读者可能犯的错误（如"90%的人都不知道..."、"别再这样做了！"）
3. 💡 核心洞见：提炼文章最有价值的观点作为标题
4. 🎯 数字吸引：使用具体数字增加可信度（如"3个技巧"、"5分钟学会"）
5. ❓ 悬念疑问：用问句引发好奇（如"为什么...？"、"如何才能...？"）
6. 🆚 对比冲突：制造反差（如"从小白到大神"、"免费vs付费"）

【要求】
- 15-25字，简洁有力
- 必须与文章内容高度相关
- 去除所有原作者/UP主/频道信息
- 适合中文博客/公众号发布
- 让人看到就想点击

【原标题参考】{original_title}

【文章内容摘要】
{content[:500]}

【输出格式】
只返回一个优化后的标题，不要任何解释或标点符号包裹。"""

        try:
            response = self.llm_client.chat(prompt)
            new_title = response.strip().strip('"').strip("'").strip('《').strip('》')
            # 清理可能的前缀
            for prefix in ['标题：', '标题:', '优化标题：', '优化标题:']:
                if new_title.startswith(prefix):
                    new_title = new_title[len(prefix):].strip()
            return new_title if new_title else original_title
        except Exception as e:
            logger.error(f"标题优化失败: {e}")
            return original_title
    
    def publish_to_wordpress(
        self, 
        title: str, 
        content: str, 
        category: ArticleCategory,
        featured_image_url: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status: str = "publish",  # draft/publish，默认直接发布
        seo_data: Optional[Dict[str, str]] = None  # SEO元数据
    ) -> Dict[str, Any]:
        """
        发布文章到 WordPress
        
        Args:
            title: 文章标题
            content: 文章内容（HTML或Markdown）
            category: 文章分类
            featured_image_url: 特色图片URL
            tags: 标签列表
            status: 发布状态 (draft=草稿, publish=发布)
            seo_data: SEO元数据 (seo_title, seo_description, focus_keyword, keywords)
            
        Returns:
            Dict: 发布结果
        """
        # 确定分类ID
        category_map = {
            ArticleCategory.TUTORIAL: self.config.tutorial_category_id,      # 使用指南 (8)
            ArticleCategory.AI_NEWS: self.config.ai_news_category_id,        # 热点资讯 (7)
            ArticleCategory.HOT_TOPIC: self.config.hot_topic_category_id,    # 热门专题 (34)
            ArticleCategory.FAQ: self.config.faq_category_id,                # 常见问题 (1)
        }
        category_id = category_map.get(category, self.config.tutorial_category_id)
        
        # 解析品牌标签（从内容中提取 ---BRAND-TAGS--- 块）
        cleaned_content, brand_tag_ids = self._parse_brand_tags(content)
        if brand_tag_ids:
            logger.info(f"从内容中提取到品牌标签ID: {brand_tag_ids}")
        
        # 构建文章数据
        post_data = {
            "title": title,
            "content": cleaned_content,  # 使用清理后的内容（移除了标签块）
            "status": status,
            "categories": [category_id],
        }
        
        # 添加SEO元数据（支持Yoast SEO和Rank Math）
        if seo_data:
            # Yoast SEO 字段
            if seo_data.get('seo_title'):
                post_data['yoast_head_json'] = {
                    'title': seo_data['seo_title']
                }
                # Yoast SEO meta字段
                post_data['meta'] = post_data.get('meta', {})
                post_data['meta']['_yoast_wpseo_title'] = seo_data['seo_title']
            
            if seo_data.get('seo_description'):
                post_data['meta'] = post_data.get('meta', {})
                post_data['meta']['_yoast_wpseo_metadesc'] = seo_data['seo_description']
            
            if seo_data.get('focus_keyword'):
                post_data['meta'] = post_data.get('meta', {})
                post_data['meta']['_yoast_wpseo_focuskw'] = seo_data['focus_keyword']
            
            # Rank Math SEO 字段
            if seo_data.get('seo_title'):
                post_data['meta'] = post_data.get('meta', {})
                post_data['meta']['rank_math_title'] = seo_data['seo_title']
            
            if seo_data.get('seo_description'):
                post_data['meta'] = post_data.get('meta', {})
                post_data['meta']['rank_math_description'] = seo_data['seo_description']
            
            if seo_data.get('focus_keyword'):
                post_data['meta'] = post_data.get('meta', {})
                post_data['meta']['rank_math_focus_keyword'] = seo_data['focus_keyword']
            
            logger.info(f"添加SEO数据: {seo_data}")
        
        # 收集所有标签ID
        all_tag_ids = list(brand_tag_ids)  # 先添加品牌标签
        
        if tags:
            # 获取或创建用户指定的标签
            user_tag_ids = self._get_or_create_tags(tags)
            for tid in user_tag_ids:
                if tid not in all_tag_ids:
                    all_tag_ids.append(tid)
        
        # 从keywords提取标签
        if seo_data and seo_data.get('keywords') and not tags:
            keywords = [k.strip() for k in seo_data['keywords'].split(',') if k.strip()]
            if keywords:
                keyword_tag_ids = self._get_or_create_tags(keywords[:5])  # 最多5个标签
                for tid in keyword_tag_ids:
                    if tid not in all_tag_ids:
                        all_tag_ids.append(tid)
        
        # 设置标签
        if all_tag_ids:
            post_data["tags"] = all_tag_ids
            logger.info(f"文章标签ID: {all_tag_ids}")
        
        # 如果有特色图片，先上传
        if featured_image_url:
            media_id = self._upload_featured_image(featured_image_url)
            if media_id:
                post_data["featured_media"] = media_id
        
        try:
            # 禁用代理，直连WordPress
            session = requests.Session()
            session.trust_env = False  # 忽略环境变量中的代理
            session.proxies = {'http': '', 'https': '', 'http://': '', 'https://': ''}
            
            logger.info(f"发布数据: {post_data}")
            logger.info(f"API地址: {self.api_base}/posts")
            logger.info(f"认证信息: 用户名={self.auth[0]}, 密码长度={len(self.auth[1])}")
            
            # 检查WordPress REST API是否启用
            try:
                api_check = session.get(f"{self.config.site_url}/wp-json/", timeout=10)
                logger.info(f"WordPress REST API检查: {api_check.status_code}")
                if api_check.status_code != 200:
                    return {
                        "success": False,
                        "error": f"WordPress REST API未启用或不可访问: {api_check.status_code}",
                        "title": title,
                        "category": category.value
                    }
            except Exception as e:
                logger.error(f"API检查失败: {e}")
                return {
                    "success": False,
                    "error": f"无法访问WordPress REST API: {str(e)}",
                    "title": title,
                    "category": category.value
                }
            
            # 使用正确的请求头和数据格式
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "BiliNote-Publisher/1.0"
            }
            
            # 发布文章 - 使用正确的HTTP方法
            logger.info(f"开始发布文章到: {self.api_base}/posts")
            response = session.post(
                f"{self.api_base}/posts",
                json=post_data,
                auth=self.auth,
                headers=headers,
                timeout=30
            )
            
            logger.info(f"发布响应状态码: {response.status_code}")
            logger.info(f"发布响应头: {dict(response.headers)}")
            logger.info(f"发布响应内容: {response.text[:1000]}")
            
            # 检查响应状态码
            if response.status_code == 201:
                # 201 Created - 成功创建
                try:
                    result = response.json()
                    if isinstance(result, dict) and "id" in result:
                        logger.info(f"文章发布成功! ID: {result.get('id')}")
                        return {
                            "success": True,
                            "post_id": result.get("id"),
                            "post_url": result.get("link"),
                            "title": title,
                            "category": category.value
                        }
                    else:
                        logger.error(f"响应格式异常: {type(result)} - {result}")
                        return {
                            "success": False,
                            "error": f"响应格式异常: 期望字典但得到 {type(result)}",
                            "title": title,
                            "category": category.value
                        }
                except Exception as json_error:
                    logger.error(f"JSON解析失败: {json_error}")
                    return {
                        "success": False,
                        "error": f"响应JSON解析失败: {str(json_error)}",
                        "title": title,
                        "category": category.value
                    }
            elif response.status_code == 200:
                # 某些WordPress配置可能返回200而不是201
                try:
                    result = response.json()
                    if isinstance(result, dict) and "id" in result:
                        logger.info(f"文章发布成功! ID: {result.get('id')}")
                        return {
                            "success": True,
                            "post_id": result.get("id"),
                            "post_url": result.get("link"),
                            "title": title,
                            "category": category.value
                        }
                    elif isinstance(result, list):
                        # 如果返回列表，可能是权限问题或API配置问题
                        logger.error("API返回了文章列表而不是新创建的文章，可能是权限或配置问题")
                        return {
                            "success": False,
                            "error": "API返回了文章列表而不是新创建的文章，请检查用户权限和API配置",
                            "title": title,
                            "category": category.value
                        }
                    else:
                        logger.error(f"意外的响应格式: {type(result)}")
                        return {
                            "success": False,
                            "error": f"意外的响应格式: {type(result)}",
                            "title": title,
                            "category": category.value
                        }
                except Exception as json_error:
                    logger.error(f"JSON解析失败: {json_error}")
                    return {
                        "success": False,
                        "error": f"响应JSON解析失败: {str(json_error)}",
                        "title": title,
                        "category": category.value
                    }
            elif response.status_code == 401:
                return {
                    "success": False,
                    "error": "认证失败，请检查用户名和应用密码",
                    "title": title,
                    "category": category.value
                }
            elif response.status_code == 403:
                return {
                    "success": False,
                    "error": "权限不足，用户没有发布文章的权限",
                    "title": title,
                    "category": category.value
                }
            else:
                return {
                    "success": False,
                    "error": f"发布失败: HTTP {response.status_code} - {response.text[:200]}",
                    "title": title,
                    "category": category.value
                }
        except Exception as e:
            logger.error(f"发布失败: {e}")
            import traceback
            logger.error(f"完整错误信息: {traceback.format_exc()}")
            return {
                "success": False,
                "error": str(e),
                "title": title,
                "category": category.value
            }
    
    def _parse_brand_tags(self, content: str) -> Tuple[str, List[int]]:
        """
        从文章内容中解析AI品牌标签
        
        Args:
            content: 文章内容（可能包含 ---BRAND-TAGS--- 块）
            
        Returns:
            Tuple[str, List[int]]: (清理后的内容, 品牌标签ID列表)
        """
        brand_tag_ids = []
        cleaned_content = content
        
        # 匹配 ---BRAND-TAGS--- ... ---END-BRAND-TAGS--- 块
        pattern = r'---BRAND-TAGS---\s*([\w,\s]+)\s*---END-BRAND-TAGS---'
        match = re.search(pattern, content, re.IGNORECASE)
        
        if match:
            # 提取标签字符串
            tags_str = match.group(1).strip()
            logger.info(f"发现品牌标签块: {tags_str}")
            
            # 解析标签
            for tag in tags_str.split(','):
                tag = tag.strip().lower()
                if tag in BRAND_TAG_IDS:
                    tag_id = BRAND_TAG_IDS[tag]
                    if tag_id not in brand_tag_ids:
                        brand_tag_ids.append(tag_id)
                        logger.info(f"添加品牌标签: {tag} (ID: {tag_id})")
            
            # 从内容中移除标签块
            cleaned_content = re.sub(pattern, '', content, flags=re.IGNORECASE).strip()
        
        return cleaned_content, brand_tag_ids
    
    def _get_or_create_tags(self, tags: List[str]) -> List[int]:
        """获取或创建标签"""
        tag_ids = []
        # 禁用代理，直连WordPress
        session = requests.Session()
        session.trust_env = False
        session.proxies = {'http': '', 'https': '', 'http://': '', 'https://': ''}
        
        for tag_name in tags:
            try:
                # 先搜索是否存在
                response = session.get(
                    f"{self.api_base}/tags",
                    params={"search": tag_name},
                    auth=self.auth
                )
                existing = response.json()
                
                if existing:
                    tag_ids.append(existing[0]["id"])
                else:
                    # 创建新标签
                    response = session.post(
                        f"{self.api_base}/tags",
                        json={"name": tag_name},
                        auth=self.auth
                    )
                    tag_ids.append(response.json()["id"])
            except Exception as e:
                logger.error(f"处理标签 {tag_name} 失败: {e}")
        
        return tag_ids
    
    def _upload_featured_image(self, image_url: str) -> Optional[int]:
        """上传特色图片"""
        try:
            # 禁用代理，直连WordPress
            session = requests.Session()
            session.trust_env = False
            session.proxies = {'http': '', 'https': '', 'http://': '', 'https://': ''}
            
            # 下载图片
            img_response = session.get(image_url, timeout=30)
            img_response.raise_for_status()
            
            # 获取文件名
            filename = image_url.split("/")[-1]
            if "?" in filename:
                filename = filename.split("?")[0]
            if not filename.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                filename += ".jpg"
            
            # 上传到 WordPress
            headers = {
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": img_response.headers.get("Content-Type", "image/jpeg")
            }
            
            response = session.post(
                f"{self.api_base}/media",
                headers=headers,
                data=img_response.content,
                auth=self.auth,
                timeout=60
            )
            response.raise_for_status()
            return response.json().get("id")
        except Exception as e:
            logger.error(f"上传图片失败: {e}")
            return None

    def upload_local_image(self, image_path: str) -> Optional[str]:
        """
        上传本地图片到 WordPress 媒体库
        
        Args:
            image_path: 本地图片路径
            
        Returns:
            WordPress 上的图片 URL，失败返回 None
        """
        if not os.path.exists(image_path):
            logger.error(f"图片不存在: {image_path}")
            return None
        
        filename = os.path.basename(image_path)
        
        # 确定 MIME 类型
        ext = filename.lower().split('.')[-1]
        mime_types = {
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'webp': 'image/webp'
        }
        mime_type = mime_types.get(ext, 'image/jpeg')
        
        try:
            session = requests.Session()
            session.trust_env = False
            session.proxies = {'http': '', 'https': '', 'http://': '', 'https://': ''}
            
            with open(image_path, 'rb') as f:
                image_data = f.read()
            
            headers = {
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': mime_type,
            }
            
            response = session.post(
                f"{self.api_base}/media",
                headers=headers,
                data=image_data,
                auth=self.auth,
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            
            # 返回图片 URL
            wp_url = result.get('source_url') or result.get('guid', {}).get('rendered')
            logger.info(f"图片已上传: {filename} → {wp_url}")
            return wp_url
            
        except Exception as e:
            logger.error(f"图片上传失败 ({filename}): {e}")
            return None

    def process_local_images(self, content: str, static_dir: str = None) -> str:
        """
        扫描内容中的本地图片，上传到 WordPress 并替换 URL
        
        Args:
            content: 文章内容
            static_dir: 静态文件目录路径
            
        Returns:
            替换后的内容
        """
        # 本地截图目录 - backend/static/screenshots
        if not static_dir:
            # 从 app/services/wordpress_publisher.py 向上找到 backend 目录
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            static_dir = os.path.join(backend_dir, "static", "screenshots")
            logger.info(f"截图目录: {static_dir}")
        
        # 匹配多种格式的本地图片路径:
        # 1. Markdown格式: ![alt](/static/screenshots/xxx.jpg) 或 ![](static/screenshots/xxx.jpg)
        # 2. 带域名: http://localhost:8483/static/screenshots/xxx.jpg
        # 3. 纯路径: /static/screenshots/xxx.jpg
        
        # 先提取所有图片文件名
        patterns = [
            r'!\[[^\]]*\]\((?:http://(?:localhost|127\.0\.0\.1):\d+)?/?static/screenshots/([^"\'\)\s]+)\)',  # Markdown格式
            r'(?:http://(?:localhost|127\.0\.0\.1):\d+)?/static/screenshots/([^"\'\)\s]+)',  # URL格式
            r'src=["\'](?:http://(?:localhost|127\.0\.0\.1):\d+)?/?static/screenshots/([^"\'\s]+)["\']',  # HTML img src
        ]
        
        all_filenames = set()
        for pattern in patterns:
            matches = re.findall(pattern, content)
            all_filenames.update(matches)
        
        if not all_filenames:
            logger.info("未发现本地图片")
            return content
        
        logger.info(f"发现 {len(all_filenames)} 张本地图片，正在上传到 WordPress...")
        
        # 上传每张图片并替换
        for filename in all_filenames:
            local_path = os.path.join(static_dir, filename)
            logger.info(f"处理图片: {filename}, 本地路径: {local_path}")
            
            if not os.path.exists(local_path):
                logger.warning(f"图片文件不存在: {local_path}")
                continue
            
            # 上传到 WordPress
            wp_url = self.upload_local_image(local_path)
            
            if wp_url:
                logger.info(f"图片上传成功: {filename} -> {wp_url}")
                escaped_filename = re.escape(filename)
                
                # 替换所有可能的格式 - 注意顺序很重要，先替换最长的匹配
                # 1. Markdown格式带localhost: ![xxx](http://localhost:8483/static/screenshots/xxx.jpg)
                content = re.sub(
                    rf'(!\[[^\]]*\]\()http://(?:localhost|127\.0\.0\.1):\d+/static/screenshots/{escaped_filename}(\))',
                    rf'\1{wp_url}\2',
                    content
                )
                # 2. 纯URL带localhost: http://localhost:8483/static/screenshots/xxx.jpg
                content = re.sub(
                    rf'http://(?:localhost|127\.0\.0\.1):\d+/static/screenshots/{escaped_filename}',
                    wp_url,
                    content
                )
                # 3. Markdown格式不带域名: ![xxx](/static/screenshots/xxx.jpg)
                content = re.sub(
                    rf'(!\[[^\]]*\]\()/static/screenshots/{escaped_filename}(\))',
                    rf'\1{wp_url}\2',
                    content
                )
                # 4. /static/screenshots/filename
                content = content.replace(f"/static/screenshots/{filename}", wp_url)
                # 5. static/screenshots/filename (不带前导斜杠)
                content = content.replace(f"static/screenshots/{filename}", wp_url)
            else:
                logger.error(f"图片上传失败: {filename}")
        
        return content


class BatchVideoProcessor:
    """批量视频处理器"""
    
    def __init__(
        self, 
        note_generator: Any,  # BiliNote 的 NoteGenerator
        publisher: WordPressPublisher
    ):
        """
        初始化批量处理器
        
        Args:
            note_generator: BiliNote 的笔记生成器
            publisher: WordPress 发布器
        """
        self.note_generator = note_generator
        self.publisher = publisher
        self.results: List[PublishResult] = []
    
    def process_videos(
        self,
        tasks: List[ArticleTask],
        auto_publish: bool = False,
        screenshot: bool = True,
        link: bool = True,
        style: str = "normal"
    ) -> List[PublishResult]:
        """
        批量处理视频并发布
        
        Args:
            tasks: 视频任务列表
            auto_publish: 是否自动发布（False则保存为草稿）
            screenshot: 是否包含截图
            link: 是否包含时间链接
            style: 笔记风格
            
        Returns:
            List[PublishResult]: 处理结果列表
        """
        # 按优先级排序
        sorted_tasks = sorted(tasks, key=lambda x: x.priority)
        
        results = []
        for i, task in enumerate(sorted_tasks):
            logger.info(f"处理任务 {i+1}/{len(sorted_tasks)}: {task.video_url}")
            
            try:
                result = self._process_single_video(
                    task=task,
                    auto_publish=auto_publish,
                    screenshot=screenshot,
                    link=link,
                    style=style
                )
                results.append(result)
                
            except Exception as e:
                logger.error(f"处理视频失败 {task.video_url}: {e}")
                results.append(PublishResult(
                    success=False,
                    video_url=task.video_url,
                    title="",
                    category="",
                    error=str(e)
                ))
        
        self.results = results
        return results
    
    def _process_single_video(
        self,
        task: ArticleTask,
        auto_publish: bool,
        screenshot: bool,
        link: bool,
        style: str
    ) -> PublishResult:
        """处理单个视频"""
        
        # 1. 使用 BiliNote 生成笔记
        note_result = self.note_generator.generate(
            video_url=task.video_url,
            platform=task.platform,
            screenshot=screenshot,
            link=link,
            style=style
        )
        
        if not note_result:
            raise Exception("笔记生成失败")
        
        # 2. 获取生成的内容
        title = note_result.title or "未命名文章"
        content = note_result.markdown_content or ""
        
        # 3. 优化标题
        optimized_title = self.publisher.optimize_title(title, content)
        
        # 4. 分类判断
        category = self.publisher.classify_article(optimized_title, content)
        
        # 5. 提取标签（从内容中提取关键词）
        tags = self._extract_tags(content)
        
        # 6. 获取封面图
        featured_image = None
        if hasattr(note_result, 'thumbnail') and note_result.thumbnail:
            featured_image = note_result.thumbnail
        
        # 7. 发布到 WordPress
        publish_status = "publish" if auto_publish else "draft"
        result = self.publisher.publish_to_wordpress(
            title=optimized_title,
            content=content,
            category=category,
            featured_image_url=featured_image,
            tags=tags,
            status=publish_status
        )
        
        return PublishResult(
            success=result.get("success", False),
            video_url=task.video_url,
            title=optimized_title,
            category=category.value,
            post_id=result.get("post_id"),
            post_url=result.get("post_url"),
            error=result.get("error")
        )
    
    def _extract_tags(self, content: str, max_tags: int = 5) -> List[str]:
        """从内容中提取标签"""
        # 简单实现：提取常见技术关键词
        tech_keywords = [
            "AI", "GPT", "ChatGPT", "Claude", "OpenAI", "Google", "Gemini",
            "Python", "JavaScript", "Docker", "Kubernetes", "API",
            "机器学习", "深度学习", "自然语言处理", "计算机视觉",
            "视频", "音频", "图片", "文本", "生成式AI"
        ]
        
        found_tags = []
        content_lower = content.lower()
        
        for kw in tech_keywords:
            if kw.lower() in content_lower:
                found_tags.append(kw)
                if len(found_tags) >= max_tags:
                    break
        
        return found_tags
    
    def get_summary(self) -> Dict[str, Any]:
        """获取处理摘要"""
        total = len(self.results)
        success = sum(1 for r in self.results if r.success)
        failed = total - success
        
        return {
            "total": total,
            "success": success,
            "failed": failed,
            "results": [
                {
                    "video_url": r.video_url,
                    "title": r.title,
                    "category": r.category,
                    "success": r.success,
                    "post_url": r.post_url,
                    "error": r.error
                }
                for r in self.results
            ]
        }


# ============== 便捷函数 ==============

def create_publisher_from_env(llm_client: Any = None) -> WordPressPublisher:
    """从环境变量创建发布器"""
    config = WordPressConfig(
        site_url=os.getenv("WORDPRESS_URL", "https://www.xasia.cc"),  # 使用www子域名
        username=os.getenv("WORDPRESS_USER", "67859543"),
        app_password=os.getenv("WORDPRESS_APP_PASSWORD", "XqXt bHFX rwL3 M5kc rDqd HXD2"),
        tutorial_category_id=int(os.getenv("WP_TUTORIAL_CATEGORY_ID", "8")),      # 使用指南
        ai_news_category_id=int(os.getenv("WP_AI_NEWS_CATEGORY_ID", "7")),        # 热点资讯
        hot_topic_category_id=int(os.getenv("WP_HOT_TOPIC_CATEGORY_ID", "34")),   # 热门专题
        faq_category_id=int(os.getenv("WP_FAQ_CATEGORY_ID", "1"))                 # 常见问题
    )
    return WordPressPublisher(config, llm_client=llm_client)


def quick_publish_videos(
    video_urls: List[str],
    platform: str = "youtube",
    auto_publish: bool = False,
    provider_id: str = None,
    model_name: str = None
) -> Dict[str, Any]:
    """
    快速批量发布视频
    
    Args:
        video_urls: 视频链接列表
        platform: 平台 (youtube/bilibili/douyin)
        auto_publish: 是否自动发布
        provider_id: 模型供应商ID（用于分类和标题优化）
        model_name: 模型名称
        
    Returns:
        Dict: 处理结果摘要
    """
    from app.services.note import NoteGenerator
    from app.gpt.gpt_factory import GPTFactory
    from app.services.provider import ProviderService
    from app.models.model_config import ModelConfig
    
    # 创建 LLM 客户端（用于分类和标题优化）
    llm_client = None
    if provider_id and model_name:
        try:
            provider = ProviderService.get_provider_by_id(provider_id)
            if provider:
                config = ModelConfig(
                    api_key=provider.get('api_key', ''),
                    base_url=provider.get('base_url', ''),
                    model_name=model_name
                )
                gpt = GPTFactory.from_config(config)
                # 包装成简单的 chat 接口
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
    
    # 创建组件
    note_gen = NoteGenerator()
    publisher = create_publisher_from_env(llm_client=llm_client)
    processor = BatchVideoProcessor(note_gen, publisher)
    
    # 创建任务
    tasks = [
        ArticleTask(video_url=url, platform=platform, priority=i)
        for i, url in enumerate(video_urls)
    ]
    
    # 处理
    processor.process_videos(tasks, auto_publish=auto_publish)
    
    return processor.get_summary()
