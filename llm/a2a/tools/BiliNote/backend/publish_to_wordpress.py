#!/usr/bin/env python
"""
WordPress 独立发布脚本
不需要启动前后端，直接命令行运行即可发布视频笔记到 WordPress

使用方法:
    python publish_to_wordpress.py "视频链接"
    python publish_to_wordpress.py "视频链接1" "视频链接2" "视频链接3"
    python publish_to_wordpress.py --file urls.txt
    python publish_to_wordpress.py --gui  (可视化界面)
"""

import os
import sys
import re
import argparse
import requests
from requests.auth import HTTPBasicAuth
import markdown
from typing import List, Optional
from dotenv import load_dotenv
from openai import OpenAI

# 加载环境变量
load_dotenv()

# WordPress 配置
WP_CONFIG = {
    "site_url": os.getenv("WORDPRESS_URL", "https://xasia.cc"),
    "username": os.getenv("WORDPRESS_USER", "67859543"),
    "app_password": os.getenv("WORDPRESS_APP_PASSWORD", "XqXt bHFX rwL3 M5kc rDqd HXD2"),
    "tutorial_category_id": int(os.getenv("WP_TUTORIAL_CATEGORY_ID", "8")),
    "ai_news_category_id": int(os.getenv("WP_AI_NEWS_CATEGORY_ID", "7"))
}

# MiniMax 模型配置
LLM_CONFIG = {
    "api_key": "sk-irtebxecbiptpnrdpjdzgbldliinwouubevsnmlcflvsjeen",
    "base_url": "https://api.siliconflow.cn/v1",
    "model": "MiniMaxAI/MiniMax-M1-80k"
}


def auto_detect_platform(url: str) -> str:
    """自动识别视频平台"""
    url = url.lower()
    if "bilibili.com" in url or "b23.tv" in url:
        return "bilibili"
    elif "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    elif "douyin.com" in url or "tiktok.com" in url:
        return "douyin"
    elif "kuaishou.com" in url:
        return "kuaishou"
    elif os.path.exists(url):
        return "local"
    else:
        # 默认尝试 bilibili
        return "bilibili"


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
        # 检查缓存
        if tag_name in self._tag_cache:
            return self._tag_cache[tag_name]
        
        try:
            # 先搜索是否存在
            response = requests.get(
                f"{self.api_base}/tags",
                params={"search": tag_name, "per_page": 100},
                auth=self.auth,
                timeout=10
            )
            response.raise_for_status()
            tags = response.json()
            
            # 精确匹配
            for tag in tags:
                if tag.get("name") == tag_name:
                    self._tag_cache[tag_name] = tag["id"]
                    return tag["id"]
            
            # 不存在则创建
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
            # 解析返回的标签
            tags = [t.strip() for t in response.replace("，", ",").split(",") if t.strip()]
            # 过滤掉太长或太短的
            tags = [t for t in tags if 2 <= len(t) <= 10]
            return tags[:5]  # 最多5个
        except Exception as e:
            print(f"  ⚠ 智能标签生成失败: {e}")
            return []
    
    def classify_article(self, title: str, content: str) -> str:
        """使用 LLM 分类文章"""
        if not self.llm:
            return self._keyword_classify(title, content)
        
        prompt = f"""请判断以下文章应该归类到哪个分类：

分类选项：
1. tutorial（使用指南）- 教程、操作指南、配置说明、工具使用方法等
2. ai_news（AI资讯）- AI新闻、技术动态、产品发布、行业趋势等

文章标题：{title}

文章内容摘要（前500字）：
{content[:500]}

请只返回分类名称（tutorial 或 ai_news），不要返回其他内容。"""

        try:
            response = self.llm.chat(prompt)
            if "tutorial" in response.lower():
                return "tutorial"
            return "ai_news"
        except Exception as e:
            print(f"LLM分类失败: {e}")
            return self._keyword_classify(title, content)
    
    def _keyword_classify(self, title: str, content: str) -> str:
        """关键词分类"""
        text = (title + content).lower()
        tutorial_kw = ["教程", "指南", "如何", "怎么", "配置", "安装", "设置", "使用", "tutorial", "guide", "how to"]
        news_kw = ["发布", "更新", "新版", "动态", "资讯", "新闻", "release", "update", "news"]
        
        t_score = sum(1 for kw in tutorial_kw if kw in text)
        n_score = sum(1 for kw in news_kw if kw in text)
        
        return "tutorial" if t_score >= n_score else "ai_news"
    
    def optimize_title(self, title: str, content: str) -> str:
        """使用 LLM 优化标题"""
        if not self.llm:
            return title
        
        prompt = f"""请为以下文章生成一个全新的中文标题，要求：
1. 简洁明了，20字以内
2. 能准确反映文章核心内容
3. 适合博客/自媒体发布
4. 必须完全重新创作，不能与原标题雷同
5. 去除所有原作者/UP主/频道相关的信息

原标题（仅供参考内容方向）：{title}

文章内容摘要：
{content[:300]}

请只返回全新创作的标题，不要返回其他内容。"""

        try:
            new_title = self.llm.chat(prompt).strip().strip('"').strip("'")
            return new_title if new_title else title
        except Exception as e:
            print(f"标题优化失败: {e}")
            return title
    
    def upload_image_to_wordpress(self, image_path: str) -> Optional[str]:
        """
        上传本地图片到 WordPress 媒体库
        
        Args:
            image_path: 本地图片路径
            
        Returns:
            WordPress 上的图片 URL，失败返回 None
        """
        if not os.path.exists(image_path):
            print(f"图片不存在: {image_path}")
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
            with open(image_path, 'rb') as f:
                image_data = f.read()
            
            headers = {
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': mime_type,
            }
            
            response = requests.post(
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
            print(f"  ✓ 图片已上传: {filename} → {wp_url}")
            return wp_url
            
        except Exception as e:
            print(f"  ✗ 图片上传失败 ({filename}): {e}")
            return None
    
    def process_local_images(self, content: str) -> str:
        """
        扫描内容中的本地图片，上传到 WordPress 并替换 URL
        
        支持格式：
        - Markdown: ![alt](http://localhost:xxx/static/screenshots/xxx.jpg)
        - HTML: <img src="http://localhost:xxx/static/screenshots/xxx.jpg">
        """
        # 匹配本地服务器图片 URL
        # 格式: http://localhost:端口/static/screenshots/文件名
        local_pattern = r'(http://(?:localhost|127\.0\.0\.1):\d+)?/static/screenshots/([^"\'\)\s]+)'
        
        matches = re.findall(local_pattern, content)
        
        if not matches:
            return content
        
        print(f"  → 发现 {len(matches)} 张本地图片，正在上传到 WordPress...")
        
        # 本地截图目录
        static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "screenshots")
        
        for base_url, filename in matches:
            local_path = os.path.join(static_dir, filename)
            
            # 构建完整的本地 URL（用于替换）
            if base_url:
                old_url = f"{base_url}/static/screenshots/{filename}"
            else:
                old_url = f"/static/screenshots/{filename}"
            
            # 上传到 WordPress
            wp_url = self.upload_image_to_wordpress(local_path)
            
            if wp_url:
                # 替换内容中的 URL
                content = content.replace(old_url, wp_url)
                # 也替换不带域名的路径
                content = content.replace(f"/static/screenshots/{filename}", wp_url)
        
        return content
    
    def clean_and_convert_content(self, content: str, video_url: str = None) -> str:
        """清理内容并转换为 HTML"""
        # 1. 去除代码块包裹 (```markdown ... ``` 或 ``` ... ```)
        content = re.sub(r'^```(?:markdown)?\s*\n', '', content, flags=re.MULTILINE)
        content = re.sub(r'\n```\s*$', '', content, flags=re.MULTILINE)
        content = re.sub(r'^```\s*$', '', content, flags=re.MULTILINE)
        
        # 2. 清理多余的空行
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        # 3. 修复常见的 Markdown 格式问题
        # 修复破折号列表 (– 改为 -)
        content = content.replace('–', '-')
        # 修复中文标点
        content = content.replace('——', '—')
        
        # 4. 清理时间戳链接标记（WordPress 不需要跳转功能）
        # 清理 *Content-[mm:ss] 或 Content-[mm:ss] 或 *Content-mm:ss*
        content = re.sub(r'\*?Content-\[?\d{2}:\d{2}\]?\*?', '', content)
        # 清理残留的 [原片 @ mm:ss](url) 链接
        content = re.sub(r'\[原片\s*@\s*\d{2}:\d{2}\]\([^)]+\)', '', content)
        # 清理裸露的 bilibili 链接
        content = re.sub(r'https?://www\.bilibili\.com/video/[^\s\)]+', '', content)
        
        # 5. 上传本地图片到 WordPress 并替换 URL
        content = self.process_local_images(content)
        
        # 5. 转换 Markdown 为 HTML
        html_content = markdown.markdown(
            content,
            extensions=[
                'markdown.extensions.tables',      # 表格支持
                'markdown.extensions.fenced_code', # 代码块
                'markdown.extensions.codehilite', # 代码高亮
                'markdown.extensions.toc',         # 目录
                'markdown.extensions.nl2br',       # 换行转 <br>
            ]
        )
        
        return html_content
    
    def publish(self, title: str, content: str, status: str = "draft", 
                video_url: str = None, author: str = None,
                extra_tags: List[str] = None, smart_tags: bool = True) -> dict:
        """
        发布文章到 WordPress
        
        Args:
            title: 文章标题
            content: 文章内容 (Markdown)
            status: 发布状态 (draft/publish)
            video_url: 原视频链接
            author: 原作者
            extra_tags: 额外标签列表
            smart_tags: 是否使用 LLM 智能生成标签
        """
        # 分类
        category = self.classify_article(title, content)
        category_id = self.config["tutorial_category_id"] if category == "tutorial" else self.config["ai_news_category_id"]
        
        # 优化标题
        optimized_title = self.optimize_title(title, content)
        
        # 清理并转换内容为 HTML
        html_content = self.clean_and_convert_content(content, video_url)
        
        # 收集所有标签
        all_tags = list(self.DEFAULT_TAGS)  # 默认标签：黑盒智能体
        
        # 添加额外标签
        if extra_tags:
            all_tags.extend(extra_tags)
        
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
            "categories": [category_id],
            "tags": tag_ids,  # 添加标签
        }
        
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
                "original_title": title,
                "category": category,
                "status": status,
                "tags": all_tags
            }
        except Exception as e:
            return {"success": False, "error": str(e), "title": title}


def generate_note_from_video(video_url: str, platform: str) -> dict:
    """从视频生成笔记（简化版，直接调用 BiliNote 核心功能）"""
    # 添加项目路径
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    from app.services.note import NoteGenerator
    from app.db.init_db import init_db
    from app.db.provider_dao import seed_default_providers
    
    # 初始化数据库
    init_db()
    seed_default_providers()
    
    # 生成笔记
    generator = NoteGenerator()
    import uuid
    task_id = str(uuid.uuid4())[:8]
    
    result = generator.generate(
        video_url=video_url,
        platform=platform,
        task_id=task_id,
        provider_id="minimax",
        model_name="MiniMaxAI/MiniMax-M1-80k",
        screenshot=True,              # 开启：根据 *Screenshot 标记截取真实图片
        link=True,
        style="detailed",
        video_understanding=False,    # MiniMax-M1 不支持图片，关闭网格图
        _format=["screenshot", "link", "summary"]  # 告诉 LLM 根据文字内容添加截图标记
    )
    
    if result:
        # 获取作者信息
        author = None
        if result.audio_meta and result.audio_meta.raw_info:
            author = result.audio_meta.raw_info.get("uploader") or result.audio_meta.raw_info.get("author")
        
        return {
            "success": True,
            "title": result.audio_meta.title if result.audio_meta else "未知标题",
            "content": result.markdown,
            "thumbnail": result.audio_meta.cover_url if result.audio_meta else None,
            "author": author
        }
    return {"success": False, "error": "笔记生成失败"}


def run_gui():
    """运行可视化界面"""
    try:
        import tkinter as tk
        from tkinter import ttk, scrolledtext, messagebox, filedialog
    except ImportError:
        print("错误: 需要安装 tkinter")
        return
    
    class PublishGUI:
        def __init__(self):
            self.root = tk.Tk()
            self.root.title("BiliNote WordPress 批量发布工具")
            self.root.geometry("800x600")
            self.root.configure(bg="#f0f0f0")
            
            self.setup_ui()
            self.llm = SimpleLLM()
            self.publisher = WordPressPublisher(self.llm)
        
        def setup_ui(self):
            # 标题
            title = tk.Label(self.root, text="BiliNote → WordPress 批量发布", 
                           font=("微软雅黑", 16, "bold"), bg="#f0f0f0")
            title.pack(pady=10)
            
            # 输入区
            input_frame = tk.LabelFrame(self.root, text="视频链接（每行一个，自动识别平台）", 
                                       font=("微软雅黑", 10), bg="#f0f0f0")
            input_frame.pack(fill="x", padx=20, pady=5)
            
            self.url_text = scrolledtext.ScrolledText(input_frame, height=8, font=("Consolas", 10))
            self.url_text.pack(fill="x", padx=10, pady=10)
            
            # 按钮区
            btn_frame = tk.Frame(self.root, bg="#f0f0f0")
            btn_frame.pack(fill="x", padx=20, pady=5)
            
            tk.Button(btn_frame, text="从文件导入", command=self.load_file, 
                     font=("微软雅黑", 10)).pack(side="left", padx=5)
            tk.Button(btn_frame, text="清空", command=lambda: self.url_text.delete(1.0, tk.END),
                     font=("微软雅黑", 10)).pack(side="left", padx=5)
            
            self.draft_var = tk.BooleanVar(value=False)
            tk.Checkbutton(btn_frame, text="保存为草稿(不勾选=直接发布)", variable=self.draft_var,
                          font=("微软雅黑", 10), bg="#f0f0f0").pack(side="left", padx=20)
            
            tk.Button(btn_frame, text="🚀 开始发布", command=self.start_publish,
                     font=("微软雅黑", 12, "bold"), bg="#4CAF50", fg="white",
                     width=15, height=2).pack(side="right", padx=5)
            
            # 日志区
            log_frame = tk.LabelFrame(self.root, text="发布日志", 
                                     font=("微软雅黑", 10), bg="#f0f0f0")
            log_frame.pack(fill="both", expand=True, padx=20, pady=10)
            
            self.log_text = scrolledtext.ScrolledText(log_frame, height=15, font=("Consolas", 9))
            self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
            
            # 状态栏
            self.status_var = tk.StringVar(value="就绪 - 粘贴视频链接后点击发布")
            status = tk.Label(self.root, textvariable=self.status_var, 
                            font=("微软雅黑", 9), bg="#e0e0e0", anchor="w")
            status.pack(fill="x", side="bottom")
        
        def log(self, msg):
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
            self.root.update()
        
        def load_file(self):
            file = filedialog.askopenfilename(filetypes=[("文本文件", "*.txt")])
            if file:
                with open(file, "r", encoding="utf-8") as f:
                    self.url_text.insert(tk.END, f.read())
        
        def start_publish(self):
            urls = [u.strip() for u in self.url_text.get(1.0, tk.END).split("\n") if u.strip()]
            if not urls:
                messagebox.showwarning("提示", "请输入视频链接")
                return
            
            status = "draft" if self.draft_var.get() else "publish"
            self.log(f"\n{'='*50}")
            self.log(f"开始处理 {len(urls)} 个视频...")
            self.log(f"发布状态: {'草稿' if status == 'draft' else '直接发布'}")
            self.log(f"{'='*50}\n")
            
            success = 0
            for i, url in enumerate(urls, 1):
                platform = auto_detect_platform(url)
                self.status_var.set(f"处理中 [{i}/{len(urls)}]: {url[:50]}...")
                self.log(f"[{i}/{len(urls)}] {url}")
                self.log(f"  平台: {platform}")
                
                try:
                    self.log("  → 生成笔记中...")
                    note = generate_note_from_video(url, platform)
                    
                    if not note["success"]:
                        self.log(f"  ✗ 笔记生成失败: {note.get('error')}")
                        continue
                    
                    self.log(f"  → 原标题: {note['title']}")
                    self.log("  → 发布到 WordPress...")
                    
                    result = self.publisher.publish(note["title"], note["content"], status)
                    
                    if result["success"]:
                        self.log(f"  ✓ 成功!")
                        self.log(f"    优化标题: {result['title']}")
                        self.log(f"    分类: {result['category']}")
                        self.log(f"    标签: {', '.join(result.get('tags', []))}")
                        self.log(f"    链接: {result['post_url']}")
                        success += 1
                    else:
                        self.log(f"  ✗ 发布失败: {result.get('error')}")
                except Exception as e:
                    self.log(f"  ✗ 错误: {str(e)}")
                
                self.log("")
            
            self.log(f"{'='*50}")
            self.log(f"完成! 成功: {success}/{len(urls)}")
            self.log(f"{'='*50}")
            self.status_var.set(f"完成 - 成功: {success}/{len(urls)}")
            messagebox.showinfo("完成", f"处理完成!\n成功: {success}/{len(urls)}")
        
        def run(self):
            self.root.mainloop()
    
    app = PublishGUI()
    app.run()


def main():
    parser = argparse.ArgumentParser(description="BiliNote WordPress 发布工具")
    parser.add_argument("urls", nargs="*", help="视频链接（支持多个，自动识别平台）")
    parser.add_argument("--file", "-f", help="从文件读取链接（每行一个）")
    parser.add_argument("--gui", "-g", action="store_true", help="打开可视化界面")
    parser.add_argument("--draft", "-d", action="store_true", help="保存为草稿（默认直接发布）")
    parser.add_argument("--no-llm", action="store_true", help="不使用 LLM 优化标题和分类")
    
    args = parser.parse_args()
    
    # 可视化界面
    if args.gui or (not args.urls and not args.file):
        run_gui()
        return
    
    # 收集所有链接
    urls = list(args.urls) if args.urls else []
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            urls.extend([line.strip() for line in f if line.strip()])
    
    if not urls:
        print("没有视频链接，启动可视化界面...")
        run_gui()
        return
    
    # 初始化 - 默认使用 LLM，默认直接发布
    llm = None if args.no_llm else SimpleLLM()
    publisher = WordPressPublisher(llm)
    status = "draft" if args.draft else "publish"
    
    print(f"\n{'='*50}")
    print(f"BiliNote WordPress 发布工具")
    print(f"{'='*50}")
    print(f"视频数量: {len(urls)}")
    print(f"发布状态: {'草稿' if args.draft else '直接发布'}")
    print(f"LLM优化: {'关闭' if args.no_llm else '开启 (MiniMax)'}")
    print(f"平台识别: 自动")
    print(f"{'='*50}\n")
    
    results = []
    for i, url in enumerate(urls, 1):
        platform = auto_detect_platform(url)
        print(f"[{i}/{len(urls)}] 处理: {url}")
        print(f"  平台: {platform}")
        
        # YouTube 提示
        if platform == "youtube":
            print("  ⚠️ YouTube 需要能访问 YouTube（VPN 或代理）")
        
        # 生成笔记
        print("  → 正在生成笔记...")
        note = generate_note_from_video(url, platform)
        
        if not note["success"]:
            print(f"  ✗ 失败: {note.get('error')}")
            results.append({"url": url, "success": False, "error": note.get("error")})
            continue
        
        print(f"  → 原标题: {note['title']}")
        
        # 发布到 WordPress
        print("  → 正在发布到 WordPress (LLM优化标题+分类)...")
        result = publisher.publish(
            title=note["title"], 
            content=note["content"], 
            status=status,
            video_url=url,  # 添加原视频链接
            author=note.get("author")  # 添加原作者（如果有）
        )
        
        if result["success"]:
            print(f"  ✓ 成功! ID: {result['post_id']}")
            print(f"    优化标题: {result['title']}")
            print(f"    分类: {result['category']}")
            print(f"    标签: {', '.join(result.get('tags', []))}")
            print(f"    链接: {result['post_url']}")
        else:
            print(f"  ✗ 发布失败: {result.get('error')}")
        
        results.append(result)
        print()
    
    # 汇总
    success = sum(1 for r in results if r.get("success"))
    print(f"\n{'='*50}")
    print(f"完成! 成功: {success}/{len(results)}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
