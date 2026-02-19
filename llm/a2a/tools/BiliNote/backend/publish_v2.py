#!/usr/bin/env python
"""
WordPress 独立发布脚本 (增强版 - 使用 yt-dlp)
功能：批量下载抖音/B站/YouTube视频，生成AI笔记，发布到 WordPress。
修复：解决了原版抖音下载器因反爬虫失效的问题，改用 yt-dlp。

使用方法:
    python publish_v2.py --file urls.txt
"""

import os
import sys
import re
import argparse
import requests
import markdown
import subprocess
import json
import uuid
from typing import List, Optional
from dotenv import load_dotenv
from openai import OpenAI

# 添加项目路径以便导入 app 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.downloaders.base import Downloader
from app.models.audio_model import AudioDownloadResult
from app.services.note import NoteGenerator
from app.db.init_db import init_db
from app.db.provider_dao import seed_default_providers
from app.utils.path_helper import get_data_dir

# 加载环境变量
load_dotenv()

# WordPress 配置
WP_CONFIG = {
    "site_url": os.getenv("WORDPRESS_URL", "https://xasia.cc"),
    "username": os.getenv("WORDPRESS_USER", "67859543"),
    "app_password": os.getenv("WORDPRESS_APP_PASSWORD", "XqXt bHFX rwL3 M5kc rDqd HXD2"),
    # 分类配置 (实际WordPress分类ID)
    "categories": {
        "tutorial": 8,       # 使用指南 - AI工具和智能体使用教程
        "ai_news": 7,        # 热点资讯 - AI行业最新资讯
        "special": 34,       # 热门专题 - 智能体使用指南、大模型测评
        "claude": 45,        # Claude专栏
        "gemini": 43,        # Gemini专栏
        "gpt": 44,           # GPT专栏
        "grok": 46,          # Grok专栏
        "faq": 1,            # 常见问题
    }
}

# MiniMax 模型配置
LLM_CONFIG = {
    "api_key": "sk-irtebxecbiptpnrdpjdzgbldliinwouubevsnmlcflvsjeen",
    "base_url": "https://api.siliconflow.cn/v1",
    "model": "MiniMaxAI/MiniMax-M1-80k"
}


class YtDlpDownloader(Downloader):
    """
    基于 yt-dlp 的通用下载器，专门解决抖音反爬问题
    """
    def __init__(self):
        super().__init__()
    
    def _run_ytdlp(self, args: List[str]) -> str:
        # 使用 Edge 浏览器的 Cookie (需要关闭 Edge 浏览器)
        cmd = ['yt-dlp', '--cookies-from-browser', 'edge'] + args
        try:
            # 在 Windows 上隐藏控制台窗口
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            result = subprocess.run(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                encoding='utf-8', 
                errors='ignore',
                check=True,
                startupinfo=startupinfo
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise ValueError(f"yt-dlp 执行失败: {e.stderr}")

    def download(self, video_url: str, output_dir: str = None, quality=None, need_video=False) -> AudioDownloadResult:
        print(f"  [yt-dlp] 正在解析: {video_url}")
        
        if output_dir is None:
            output_dir = get_data_dir()
        os.makedirs(output_dir, exist_ok=True)
        
        # 1. 获取元数据
        try:
            info_json = self._run_ytdlp(['--dump-json', '--no-playlist', video_url])
            info = json.loads(info_json)
        except Exception as e:
            raise ValueError(f"无法获取视频信息: {e}")

        title = info.get('title', '未命名视频')
        video_id = info.get('id', str(uuid.uuid4())[:8])
        duration = info.get('duration', 0)
        cover_url = info.get('thumbnail')
        description = info.get('description', '')
        uploader = info.get('uploader') or info.get('channel')
        
        # 2. 下载音频
        # 使用 video_id 作为文件名，避免特殊字符问题
        output_template = os.path.join(output_dir, f"{video_id}.%(ext)s")
        
        print(f"  [yt-dlp] 正在下载音频...")
        self._run_ytdlp([
            '-x', 
            '--audio-format', 'mp3', 
            '--audio-quality', '0', 
            '-o', output_template, 
            video_url
        ])
        
        file_path = os.path.join(output_dir, f"{video_id}.mp3")
        if not os.path.exists(file_path):
            raise ValueError(f"音频文件未生成: {file_path}")
            
        print(f"  [yt-dlp] 下载完成: {file_path}")

        return AudioDownloadResult(
            file_path=file_path,
            title=title,
            duration=duration,
            cover_url=cover_url,
            platform="douyin" if "douyin" in video_url else "other",
            video_id=video_id,
            raw_info={
                'author': uploader,
                'description': description,
                'webpage_url': info.get('webpage_url', video_url)
            },
            video_path=None
        )


class SimpleLLM:
    """简单的 LLM 客户端"""
    def __init__(self):
        self.client = OpenAI(
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["base_url"]
        )
        self.model = LLM_CONFIG["model"]
    
    def chat(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content.strip()


class WordPressPublisher:
    """WordPress 发布器"""
    
    # 默认标签 - 所有文章自动添加
    DEFAULT_TAGS = ["黑盒智能体"]
    
    def __init__(self, llm: Optional[SimpleLLM] = None):
        self.config = WP_CONFIG
        self.llm = llm
        self.api_base = f"{self.config['site_url']}/wp-json/wp/v2"
        self.auth = (self.config['username'], self.config['app_password'])
        self._tag_cache = {}  # 缓存标签 ID
    
    def get_or_create_tag(self, tag_name: str) -> Optional[int]:
        """获取标签 ID，如果不存在则创建"""
        if tag_name in self._tag_cache:
            return self._tag_cache[tag_name]
        
        try:
            response = requests.get(
                f"{self.api_base}/tags",
                params={"search": tag_name, "per_page": 100},
                auth=self.auth,
                timeout=10
            )
            response.raise_for_status()
            tags = response.json()
            
            for tag in tags:
                if tag.get("name") == tag_name:
                    self._tag_cache[tag_name] = tag["id"]
                    return tag["id"]
            
            response = requests.post(
                f"{self.api_base}/tags",
                json={"name": tag_name},
                auth=self.auth,
                timeout=10
            )
            response.raise_for_status()
            new_tag = response.json()
            tag_id = new_tag.get("id")
            self._tag_cache[tag_name] = tag_id
            print(f"  ✓ 创建标签: {tag_name} (ID: {tag_id})")
            return tag_id
            
        except Exception as e:
            print(f"  ⚠ 标签处理失败 ({tag_name}): {e}")
            return None
    
    def get_tag_ids(self, tag_names: List[str]) -> List[int]:
        """批量获取标签 ID"""
        tag_ids = []
        for name in tag_names:
            tag_id = self.get_or_create_tag(name)
            if tag_id:
                tag_ids.append(tag_id)
        return tag_ids
    
    def generate_smart_tags(self, title: str, content: str) -> List[str]:
        """使用 LLM 智能生成相关标签"""
        if not self.llm:
            return []
        
        prompt = f"""请为以下文章生成3-5个相关标签，要求：
1. 标签要简洁，2-6个字
2. 与文章内容高度相关
3. 适合 SEO 搜索
4. 不要包含"黑盒智能体"（已默认添加）

文章标题：{title}

文章内容摘要：
{content[:500]}

请只返回标签，用逗号分隔，例如：AI教程,ChatGPT,人工智能"""

        try:
            response = self.llm.chat(prompt)
            tags = [t.strip() for t in response.replace("，", ",").split(",") if t.strip()]
            tags = [t for t in tags if 2 <= len(t) <= 10]
            return tags[:5]
        except Exception as e:
            print(f"  ⚠ 智能标签生成失败: {e}")
            return []
    
    def classify_article(self, title: str, content: str) -> dict:
        """
        使用 LLM 智能分类文章
        返回: {"main": "主分类", "platform": "平台分类(可选)"}
        """
        if not self.llm:
            return self._keyword_classify(title, content)
        
        prompt = f'''请分析以下文章，判断应该归类到哪个分类。

## 分类规则：

### 主分类（必选一个）：
1. **tutorial**（使用指南）- 教程、操作指南、配置说明、工具使用方法、部署教程
2. **ai_news**（热点资讯）- AI行业新闻、产品发布、重大更新、热点事件、行业动态
3. **special**（热门专题）- 大模型测评对比、深度分析、专题报道、综合评测

### 平台分类（如果明确涉及以下平台，额外选择）：
- **claude** - 主要讲 Claude/Anthropic 的内容
- **gemini** - 主要讲 Google Gemini 的内容  
- **gpt** - 主要讲 OpenAI GPT/ChatGPT 的内容
- **grok** - 主要讲 xAI Grok 的内容

## 分类倾向：
- 涉及"发布"、"更新"、"上线"、"官宣"等新闻性质 → 优先 ai_news
- 涉及"教程"、"怎么用"、"配置"、"部署"、"安装" → 优先 tutorial
- 涉及"对比"、"测评"、"评测"、"哪个好" → 优先 special
- 如果内容80%以上围绕某个平台(Claude/GPT/Gemini/Grok) → 同时选择平台分类

## 文章信息：
标题：{title}

内容摘要（前800字）：
{content[:800]}

## 返回格式（JSON）：
{{"main": "主分类名", "platform": "平台分类名或null"}}

请只返回JSON，不要其他内容。'''

        try:
            response = self.llm.chat(prompt)
            # 解析JSON
            import json
            # 清理可能的markdown代码块
            response = response.strip()
            if response.startswith('```'):
                response = response.split('\n', 1)[1].rsplit('```', 1)[0]
            result = json.loads(response)
            
            main_cat = result.get("main", "tutorial")
            platform = result.get("platform")
            
            # 验证分类有效性
            valid_main = ["tutorial", "ai_news", "special"]
            valid_platform = ["claude", "gemini", "gpt", "grok", None]
            
            if main_cat not in valid_main:
                main_cat = "tutorial"
            if platform not in valid_platform:
                platform = None
                
            return {"main": main_cat, "platform": platform}
            
        except Exception as e:
            print(f"  ⚠ LLM分类失败: {e}")
            return self._keyword_classify(title, content)
    
    def _keyword_classify(self, title: str, content: str) -> dict:
        """关键词分类（备用）"""
        text = (title + content).lower()
        
        # 平台检测
        platform = None
        if any(kw in text for kw in ["claude", "anthropic"]):
            platform = "claude"
        elif any(kw in text for kw in ["gemini", "google ai", "bard"]):
            platform = "gemini"
        elif any(kw in text for kw in ["gpt", "chatgpt", "openai", "gpt-4", "gpt4"]):
            platform = "gpt"
        elif any(kw in text for kw in ["grok", "xai"]):
            platform = "grok"
        
        # 主分类检测
        news_kw = ["发布", "更新", "上线", "官宣", "新版", "动态", "资讯", "新闻", "宣布", "推出"]
        tutorial_kw = ["教程", "指南", "如何", "怎么", "配置", "安装", "设置", "使用", "部署", "搭建"]
        special_kw = ["对比", "测评", "评测", "哪个好", "vs", "比较", "深度", "分析"]
        
        news_score = sum(1 for kw in news_kw if kw in text)
        tutorial_score = sum(1 for kw in tutorial_kw if kw in text)
        special_score = sum(1 for kw in special_kw if kw in text)
        
        if special_score >= 2:
            main = "special"
        elif news_score > tutorial_score:
            main = "ai_news"
        else:
            main = "tutorial"
        
        return {"main": main, "platform": platform}
    
    def optimize_title(self, title: str, content: str) -> str:
        if not self.llm:
            return title
        
        prompt = f'''请为以下文章生成一个全新的中文标题，要求：
1. 简洁明了，20字以内
2. 能准确反映文章核心内容
3. 适合博客/自媒体发布，吸引点击
4. 去除所有原作者/UP主相关信息

原标题：{title}

文章内容摘要：
{content[:300]}

请只返回标题，不要引号。'''

        try:
            new_title = self.llm.chat(prompt).strip().strip('"').strip("'")
            return new_title if new_title else title
        except Exception as e:
            return title

    def clean_and_convert_content(self, content: str) -> str:
        # 1. 提取并移除品牌标签块
        brand_tags = []
        brand_pattern = r'---BRAND-TAGS---\s*\n?(.*?)\n?---END-BRAND-TAGS---'
        brand_match = re.search(brand_pattern, content, re.DOTALL | re.IGNORECASE)
        if brand_match:
            tags_str = brand_match.group(1).strip()
            brand_tags = [t.strip().lower() for t in tags_str.split(',') if t.strip()]
            content = re.sub(brand_pattern, '', content, flags=re.DOTALL | re.IGNORECASE)
            print(f"  → 检测到品牌标签: {brand_tags}")
        
        # 保存品牌标签供分类使用
        self._detected_brand_tags = brand_tags
        
        # 2. 提取并移除SEO元数据块
        seo_data = {}
        seo_pattern = r'---SEO-METADATA---\s*\n?(.*?)\n?---END-SEO---'
        seo_match = re.search(seo_pattern, content, re.DOTALL | re.IGNORECASE)
        if seo_match:
            seo_block = seo_match.group(1)
            for line in seo_block.strip().split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    seo_data[key.strip()] = value.strip()
            content = re.sub(seo_pattern, '', content, flags=re.DOTALL | re.IGNORECASE)
            print(f"  → 提取SEO: {seo_data.get('seo_title', 'N/A')[:30]}...")
        
        # 保存SEO数据
        self._seo_data = seo_data
        
        # 3. 清理markdown代码块包裹
        content = re.sub(r'^```(?:markdown)?\s*\n', '', content, flags=re.MULTILINE)
        content = re.sub(r'\n```\s*$', '', content, flags=re.MULTILINE)
        
        # 4. 清理时间戳标记
        content = re.sub(r'\*?Content-\[?\d{2}:\d{2}\]?\*?', '', content)
        content = re.sub(r'\[原片\s*@\s*\d{2}:\d{2}\]\([^)]+\)', '', content)
        
        # 5. 清理可能残留的标记
        content = re.sub(r'---\s*\n*$', '', content)  # 末尾的 ---
        content = content.strip()
        
        # 6. 转换为HTML
        html_content = markdown.markdown(
            content,
            extensions=[
                'markdown.extensions.tables',
                'markdown.extensions.fenced_code',
                'markdown.extensions.nl2br',
            ]
        )
        return html_content
    
    def publish(self, title: str, content: str, status: str = "draft", 
                video_url: str = None, author: str = None, 
                extra_tags: List[str] = None, smart_tags: bool = True) -> dict:
        """
        发布文章到 WordPress
        """
        # 先清理内容（会提取品牌标签和SEO数据）
        self._detected_brand_tags = []
        self._seo_data = {}
        html_content = self.clean_and_convert_content(content)
        
        # 智能分类
        classification = self.classify_article(title, content)
        main_cat = classification["main"]
        platform_cat = classification.get("platform")
        
        # 如果LLM分类没检测到平台，但内容中有品牌标签，使用品牌标签
        if not platform_cat and self._detected_brand_tags:
            valid_platforms = ["claude", "gemini", "gpt", "grok"]
            for tag in self._detected_brand_tags:
                if tag in valid_platforms:
                    platform_cat = tag
                    print(f"  → 从品牌标签检测到平台: {platform_cat}")
                    break
        
        # 获取分类ID
        categories = self.config["categories"]
        category_ids = [categories.get(main_cat, categories["tutorial"])]
        
        # 如果有平台分类，添加到分类列表
        if platform_cat and platform_cat in categories:
            category_ids.append(categories[platform_cat])
        
        optimized_title = self.optimize_title(title, content)
        
        # 收集所有标签
        all_tags = list(self.DEFAULT_TAGS)  # 默认标签：黑盒智能体
        
        # 添加额外标签
        if extra_tags:
            all_tags.extend(extra_tags)
        
        # 添加检测到的品牌标签
        if self._detected_brand_tags:
            all_tags.extend(self._detected_brand_tags)
        
        # 智能生成标签
        if smart_tags and self.llm:
            generated_tags = self.generate_smart_tags(title, content)
            if generated_tags:
                print(f"  → 智能标签: {', '.join(generated_tags)}")
                all_tags.extend(generated_tags)
        
        # 去重
        all_tags = list(dict.fromkeys(all_tags))
        
        # 获取标签 ID
        tag_ids = self.get_tag_ids(all_tags)
        
        post_data = {
            "title": optimized_title,
            "content": html_content,
            "status": status,
            "categories": category_ids,
            "tags": tag_ids,
        }
        
        # 分类名称（用于日志）
        cat_names = [main_cat]
        if platform_cat:
            cat_names.append(platform_cat)
        
        try:
            response = requests.post(
                f"{self.api_base}/posts",
                json=post_data,
                auth=self.auth,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            return {
                "success": True,
                "post_id": result.get("id"),
                "post_url": result.get("link"),
                "title": optimized_title,
                "category": " + ".join(cat_names),
                "tags": all_tags
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


def generate_note_with_ytdlp(video_url: str) -> dict:
    """使用 yt-dlp 下载并生成笔记"""
    init_db()
    seed_default_providers()
    
    # 使用自定义的 YtDlpDownloader
    ytdlp_downloader = YtDlpDownloader()
    
    # 实例化 NoteGenerator
    generator = NoteGenerator()
    
    # 1. 先用 ytdlp 下载音频
    try:
        audio_result = ytdlp_downloader.download(video_url)
    except Exception as e:
        return {"success": False, "error": f"下载失败: {e}"}
    
    # 2. 调用 generator.generate，但传入本地路径
    # platform='local' 告诉 NoteGenerator 这是本地文件
    task_id = str(uuid.uuid4())[:8]
    
    print(f"  → 音频已就绪: {audio_result.file_path}")
    print(f"  → 开始 AI 处理...")
    
    try:
        result = generator.generate(
            video_url=audio_result.file_path,
            platform="local",  # 使用本地模式
            task_id=task_id,
            provider_id="minimax",
            model_name="MiniMaxAI/MiniMax-M1-80k",
            screenshot=False,
            link=True,
            style="detailed",
            video_understanding=False
        )
        
        if result:
            # 修正标题和作者信息
            author = audio_result.raw_info.get('author')
            real_title = audio_result.title
            
            return {
                "success": True,
                "title": real_title,
                "content": result.markdown,
                "author": author
            }
    except Exception as e:
        return {"success": False, "error": f"AI生成失败: {e}"}
    
    return {"success": False, "error": "笔记生成失败(未知错误)"}


def main():
    parser = argparse.ArgumentParser(description="BiliNote WordPress 发布工具 (yt-dlp版)")
    parser.add_argument("--file", "-f", help="从文件读取链接")
    args = parser.parse_args()
    
    urls = []
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()]
    
    if not urls:
        print("请提供 --file 参数")
        return
        
    llm = SimpleLLM()
    publisher = WordPressPublisher(llm)
    
    print(f"开始处理 {len(urls)} 个视频 (使用 yt-dlp)...")
    
    for i, url in enumerate(urls, 1):
        print(f"\n[{i}/{len(urls)}] 处理: {url}")
        
        try:
            note = generate_note_with_ytdlp(url)
            
            if not note["success"]:
                print(f"  ✗ 生成失败: {note.get('error')}")
                continue
                
            print(f"  → 发布到 WordPress...")
            res = publisher.publish(
                title=note["title"],
                content=note["content"],
                status="publish", # 直接发布
                video_url=url,
                author=note.get("author")
            )
            
            if res["success"]:
                print(f"  ✓ 发布成功! ID: {res['post_id']}")
                print(f"    标题: {res['title']}")
                print(f"    分类: {res['category']}")
                print(f"    标签: {', '.join(res.get('tags', []))}")
                print(f"    链接: {res['post_url']}")
            else:
                print(f"  ✗ 发布失败: {res.get('error')}")
                
        except Exception as e:
            print(f"  ✗ 异常: {e}")

if __name__ == "__main__":
    main()
